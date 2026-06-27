"""Interview practice app - Streamlit front end.

Run with:  streamlit run app.py

Three screens, driven by st.session_state["screen"]:
    setup    -> resume + job description input
    interview-> the Q&A loop
    results  -> scores + export
"""
import json
import streamlit as st

import db
from prompts import PHASES, build_interviewer_prompt, build_evaluator_prompt
from llm import ask_question, evaluate, transcribe

db.init_db()
st.set_page_config(page_title="Interview Practice", layout="centered")

# ---- session state defaults ----
ss = st.session_state
ss.setdefault("screen", "setup")
ss.setdefault("session_id", None)
ss.setdefault("phase_idx", 0)
ss.setdefault("turn", 0)
ss.setdefault("history", [])          # list of {"phase","question","answer"}
ss.setdefault("pending_question", None)
ss.setdefault("evaluation", None)


def current_phase() -> str:
    return PHASES[ss.phase_idx]


def generate_question():
    prompt = build_interviewer_prompt(ss.job_description, ss.resume, current_phase(), ss.history)
    result = ask_question(prompt)
    ss.pending_question = result.get("question", "Tell me about yourself.")
    ss.phase_complete = result.get("phase_complete", False)


# ===================== SETUP SCREEN =====================
if ss.screen == "setup":
    st.title("Interview practice")
    st.caption("Paste a resume and job description to start a mock interview.")

    ss.resume = st.text_area("Resume", height=200, key="resume_input")
    ss.job_description = st.text_area("Job description", height=150, key="jd_input")

    if st.button("Start interview", type="primary", disabled=not (ss.resume and ss.job_description)):
        ss.session_id = db.create_session(ss.resume, ss.job_description)
        ss.phase_idx = 0
        ss.turn = 0
        ss.history = []
        generate_question()
        ss.screen = "interview"
        st.rerun()

# ===================== INTERVIEW SCREEN =====================
elif ss.screen == "interview":
    st.title("Interview in progress")
    st.caption(f"Phase: **{current_phase()}**  ·  Question {ss.turn + 1}")

    # show history
    for item in ss.history:
        with st.chat_message("assistant"):
            st.write(item["question"])
        with st.chat_message("user"):
            st.write(item["answer"])

    # show current question
    with st.chat_message("assistant"):
        st.write(ss.pending_question)

    # clear the answer box on the run AFTER a submit (avoids Streamlit's
    # "can't modify widget value after instantiation" error)
    if ss.pop("_reset_answer", False):
        ss["answer_box"] = ""

    st.markdown("**Your answer** — record with the mic or type below:")

    # 1) mic: record -> transcribe -> drop text into the answer box.
    #    The key is tied to the turn number, so each new question gets a
    #    brand-new (empty) recorder instead of showing the old recording.
    audio = st.audio_input("Record your answer", key=f"audio_{ss.turn}")
    if audio is not None:
        sig = (audio.name, audio.size)
        if ss.get("_audio_sig") != sig:        # only transcribe a NEW recording
            ss["_audio_sig"] = sig
            with st.spinner("Transcribing..."):
                try:
                    ss["answer_box"] = transcribe(audio)
                except Exception as e:
                    st.error(f"Transcription failed: {e}")
            st.rerun()

    # 2) editable text box - holds typed OR transcribed text
    answer = st.text_area("Answer text", key="answer_box", height=150,
                          label_visibility="collapsed")

    # 3) submit
    if st.button("Submit answer", type="primary", disabled=not str(answer).strip()):
        ss.turn += 1
        db.log_qa(ss.session_id, ss.turn, current_phase(), ss.pending_question, answer)
        ss.history.append({"phase": current_phase(), "question": ss.pending_question, "answer": answer})

        # advance phase if the model says this one is done (cap turns per phase as a safety net)
        turns_in_phase = sum(1 for h in ss.history if h["phase"] == current_phase())
        if ss.get("phase_complete") or turns_in_phase >= 4:
            if ss.phase_idx < len(PHASES) - 1:
                ss.phase_idx += 1

        generate_question()
        ss["_reset_answer"] = True    # clear box on next run
        ss["_audio_sig"] = None       # allow a fresh recording next question
        st.rerun()

    if st.button("End interview & evaluate"):
        transcript = "\n\n".join(
            f"[{h['phase']}] Q: {h['question']}\nA: {h['answer']}" for h in ss.history
        )
        with st.spinner("Evaluating..."):
            ss.evaluation = evaluate(build_evaluator_prompt(ss.job_description, transcript))
            db.save_evaluation(ss.session_id, ss.evaluation)
        ss.screen = "results"
        st.rerun()

# ===================== RESULTS SCREEN =====================
elif ss.screen == "results":
    st.title("Results")
    ev = ss.evaluation or {}

    c1, c2, c3 = st.columns(3)
    c1.metric("Overall", f"{ev.get('overall_score', '-')}/100")
    c2.metric("Technical", f"{ev.get('technical', {}).get('score', '-')}/10")
    c3.metric("Intro", f"{ev.get('introduction_rating', {}).get('score', '-')}/10")

    st.subheader("Recommendation")
    st.write(ev.get("recommendation", "-"))
    st.write(ev.get("summary", ""))

    st.subheader("Per-question breakdown")
    for q in ev.get("per_question", []):
        st.markdown(f"**{q.get('correct', '?').upper()}** — {q.get('question', '')}")
        st.caption(q.get("comment", ""))

    st.subheader("Export")
    all_qa = db.export_all_qa()
    st.download_button(
        "Download all Q&A (JSON)",
        data=json.dumps(all_qa, indent=2),
        file_name="qa_pairs.json",
        mime="application/json",
    )

    if st.button("New interview"):
        for k in ["screen", "session_id", "phase_idx", "turn", "history",
                  "pending_question", "evaluation"]:
            ss.pop(k, None)
        st.rerun()