"""Telegram bot front end for the interview practice app.

Run with:  python bot.py

Reuses your existing db.py, prompts.py, llm.py UNCHANGED (except the small
transcribe_bytes addition in llm.py) - this file is just a different UI
layer on top of the same interview logic that powers app.py.

State machine mirrors app.py's ss.screen / ss.phase_idx / ss.turn / ss.history,
just stored in context.user_data (per-chat) instead of st.session_state.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters,
)

import db
from prompts import PHASES, build_interviewer_prompt, build_evaluator_prompt
from llm import ask_question, evaluate, transcribe_bytes, compress_profile
from resume_utils import extract_resume_from_bytes, looks_like_resume

load_dotenv(Path(__file__).parent / ".env")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

db.init_db()

# Conversation states
ASK_RESUME, ASK_JD, INTERVIEWING = range(3)


def current_phase(ud: dict) -> str:
    return PHASES[ud["phase_idx"]]


def generate_question(ud: dict):
    """Same call app.py makes - compact profile + last few turns + asked-list."""
    prompt = build_interviewer_prompt(
        ud["profile"], current_phase(ud), ud["history"][-3:], ud["asked_questions"]
    )
    result = ask_question(prompt)
    ud["pending_question"] = result.get("question", "Tell me about yourself.")
    ud["phase_complete"] = result.get("phase_complete", False)
    if ud["pending_question"]:
        ud["asked_questions"].append(ud["pending_question"])


# ===================== SETUP: /start -> resume -> job description =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Let's set up your mock interview.\n\n"
        "First, send your resume — paste it as text, or send it as a PDF file."
    )
    return ASK_RESUME


async def receive_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle a resume pasted as text."""
    text = (update.message.text or "").strip()
    ok, reason = looks_like_resume(text)
    if not ok:
        await update.message.reply_text(reason + "\n\nPaste your full resume, or send it as a PDF.")
        return ASK_RESUME
    context.user_data["resume"] = text
    await update.message.reply_text("Got it. Now paste the job description.")
    return ASK_JD


async def receive_resume_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle a resume sent as a PDF (or text) document."""
    doc = update.message.document
    try:
        tg_file = await doc.get_file()
        data = bytes(await tg_file.download_as_bytearray())
        text = extract_resume_from_bytes(data, doc.file_name)
    except Exception as e:
        await update.message.reply_text(
            f"Couldn't read that file ({e}). Send a PDF with selectable text, or paste your resume."
        )
        return ASK_RESUME

    if not text.strip():
        await update.message.reply_text(
            "That PDF has no readable text — it may be a scan or an image. "
            "Send a text-based PDF, or paste your resume instead."
        )
        return ASK_RESUME

    ok, reason = looks_like_resume(text)
    if not ok:
        await update.message.reply_text(reason + "\n\nSend a PDF resume, or paste it as text.")
        return ASK_RESUME

    context.user_data["resume"] = text
    await update.message.reply_text("Got it. Now paste the job description.")
    return ASK_JD


async def receive_jd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    jd = (update.message.text or "").strip()
    if not jd:
        await update.message.reply_text("Please paste the job description.")
        return ASK_JD

    ud["job_description"] = jd
    ud["session_id"] = db.create_session(ud["resume"], ud["job_description"])

    # one-time compression: raw resume+JD -> compact profile reused every turn
    await update.message.reply_text("Analyzing resume and job description...")
    ud["profile"] = compress_profile(ud["resume"], ud["job_description"])

    ud["phase_idx"] = 0
    ud["turn"] = 0
    ud["history"] = []
    ud["asked_questions"] = []

    generate_question(ud)
    await update.message.reply_text(
        f"Interview starting.\nPhase: {current_phase(ud)}\n\n{ud['pending_question']}\n\n"
        "Type your answer, or send a voice message. Use /end to finish early."
    )
    return INTERVIEWING


# ===================== INTERVIEW LOOP =====================

async def receive_text_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_answer(update, context, update.message.text)
    return INTERVIEWING


async def receive_voice_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_file = await update.message.voice.get_file()
    audio_bytes = await tg_file.download_as_bytearray()

    await update.message.reply_text("Transcribing...")
    try:
        answer = transcribe_bytes(bytes(audio_bytes), filename="answer.ogg")
    except Exception as e:
        await update.message.reply_text(f"Transcription failed: {e}")
        return INTERVIEWING

    await update.message.reply_text(f'Heard: "{answer}"\n(edit by typing a correction, or it counts as-is)')
    await _handle_answer(update, context, answer)
    return INTERVIEWING


async def _handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, answer: str):
    ud = context.user_data

    # never store a blank answer (empty text, or a voice note that transcribed to nothing)
    answer = (answer or "").strip()
    if not answer:
        await update.message.reply_text(
            "I didn't get an answer — please type your response or send a voice message."
        )
        return

    ud["turn"] += 1
    db.log_qa(ud["session_id"], ud["turn"], current_phase(ud), ud["pending_question"], answer)
    ud["history"].append({"phase": current_phase(ud), "question": ud["pending_question"], "answer": answer})

    # same phase-advance logic as app.py: model says done, OR 4-turn cap
    turns_in_phase = sum(1 for h in ud["history"] if h["phase"] == current_phase(ud))
    if ud.get("phase_complete") or turns_in_phase >= 4:
        if ud["phase_idx"] < len(PHASES) - 1:
            ud["phase_idx"] += 1
        else:
            await update.message.reply_text("That was the last phase. Evaluating now...")
            await _finish_interview(update, context)
            return

    generate_question(ud)
    await update.message.reply_text(f"[{current_phase(ud)}] {ud['pending_question']}")


# ===================== END / RESULTS =====================

async def end_interview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Evaluating your interview...")
    await _finish_interview(update, context)
    return ConversationHandler.END


async def _finish_interview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    transcript = "\n\n".join(
        f"[{h['phase']}] Q: {h['question']}\nA: {h['answer']}" for h in ud["history"]
    )
    evaluation = evaluate(build_evaluator_prompt(ud["job_description"], transcript))
    db.save_evaluation(ud["session_id"], evaluation)

    msg = (
        f"Overall: {evaluation.get('overall_score', '-')}/100\n"
        f"Technical: {evaluation.get('technical', {}).get('score', '-')}/10\n"
        f"Intro: {evaluation.get('introduction_rating', {}).get('score', '-')}/10\n\n"
        f"Recommendation: {evaluation.get('recommendation', '-')}\n\n"
        f"{evaluation.get('summary', '')}"
    )
    await update.message.reply_text(msg)
    await update.message.reply_text("Send /start to run another interview.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN not found - add it to your .env file")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_RESUME: [
                MessageHandler(filters.Document.ALL, receive_resume_file),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_resume),
            ],
            ASK_JD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_jd)],
            INTERVIEWING: [
                CommandHandler("end", end_interview),
                MessageHandler(filters.VOICE, receive_voice_answer),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text_answer),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    print("Bot running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()