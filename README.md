# Interview Practice App — Setup & Execution Guide
 
A mock-interview app with **two front ends** that share the same interview
engine. It reads a resume and job description, plays the interviewer (asking
one fresh question at a time), lets the candidate answer by **typing or by
voice** (recorded, then transcribed with Whisper), logs every question/answer
pair to a database, and scores the full transcript at the end.
 
- **`app.py`** — Streamlit web UI.
- **`bot.py`** — Telegram bot (same logic, chat interface).
**What's new**
- **PDF resumes** — upload a PDF or `.txt` (or still paste text). Job
  description stays text/paste.
- **Resume validation** — obvious non-resume input (random text, too short) is
  rejected before the interview starts.
- **Empty-answer guard** — blank answers are never scored or written to the DB.
- **Token optimization** — the raw resume + JD are compressed **once** at
  session start into a compact profile, which the interviewer reuses every
  turn instead of re-sending the full text. History is trimmed to the last few
  turns, with a running "already asked" list preventing repeats. Cuts per-turn
  input tokens ~5–6× on a full interview.
---
 
## 1. Prerequisites
 
- **Python 3.9+** installed.
- An **OpenAI API key** with billing enabled (used for interview questions,
  profile compression, and voice transcription).
- A microphone (only for the voice-answer feature).
- **(Telegram bot only)** A **bot token** from @BotFather.
---
 
## 2. Project structure
 
```
interview_app/
├── app.py            # Streamlit UI + interview loop (run this for web)
├── bot.py            # Telegram bot UI (run this for chat)
├── prompts.py        # Interviewer + evaluator prompt templates
├── llm.py            # OpenAI calls (questions, evaluation, profile, transcription)
├── resume_utils.py   # PDF/text resume extraction + resume validation
├── db.py             # SQLite storage (sessions + qa_pairs tables)
├── requirements.txt  # Python packages
├── .env              # YOUR secrets (you create this — see step 4)
└── interviews.db     # Created automatically on first run
```
 
---
 
## 3. Install the packages
 
Open a terminal **in the project folder** (the one containing `app.py`) and run:
 
```bash
pip install -r requirements.txt
```
 
This installs `streamlit`, `openai`, `python-dotenv`, `python-telegram-bot`,
and `pypdf`.
 
> **Important — use ONE Python.** If you have both Anaconda/conda and a
> separate system Python, make sure the `pip` you run here matches the
> `python`/`streamlit` you launch with. A mismatch causes
> `No module named streamlit` even though it "installed fine". Run `pip` and
> `streamlit` from the **same** terminal/environment. On conda, prefer
> `python -m pip install ...` so packages land in the active environment.
 
---
 
## 4. Add your secrets
 
Create a file named exactly **`.env`** in the project folder (same place as
`app.py`):
 
```
OPENAI_API_KEY=sk-proj-your-actual-key-here
TELEGRAM_BOT_TOKEN=your-telegram-bot-token-here
```
 
`TELEGRAM_BOT_TOKEN` is only needed if you run `bot.py`; the Streamlit app
ignores it.
 
Rules that save headaches:
- One key per line.
- No spaces around the `=`.
- Quotes are optional.
**Verify the OpenAI key loads** (run from the project folder):
 
```bash
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('KEY FOUND' if os.environ.get('OPENAI_API_KEY') else 'KEY MISSING')"
```
 
You want it to print `KEY FOUND`.
 
---
 
## 5. Run it
 
### Web app (Streamlit)
 
```bash
streamlit run app.py
```
 
If `streamlit` is "not recognized", use:
 
```bash
python -m streamlit run app.py
```
 
The app opens in your browser (usually at http://localhost:8501).
 
### Telegram bot
 
```bash
python bot.py
```
 
You should see `Bot running. Press Ctrl+C to stop.` Find your bot by its
`@username` in Telegram and send `/start`.
 
> After editing `.env` or any `.py` file, do a **full restart**: stop with
> `Ctrl+C` in the terminal, then run the command again. A browser refresh is
> not enough.
 
---
 
## 6. Using the app
 
### Streamlit
1. **Setup screen** — **upload a resume (PDF or .txt) or paste it**, paste a job
   description, click *Start interview*. Non-resume input is rejected; a short
   "Analyzing…" pause builds the compact profile.
2. **Interview screen** — for each question:
   - **Type** your answer, **or** click the **mic** to record and transcribe it.
   - Edit the text if the transcription misheard anything (names especially).
   - Click **Submit answer** (blank answers are blocked). A fresh box and mic appear.
   - Phases run in order: introduction → experience → projects → technical → situational.
3. Click **End interview & evaluate** when done.
4. **Results screen** — scores, a per-question breakdown, and a **download all
   Q&A as JSON** button.
### Telegram bot
1. Send `/start`.
2. **Send your resume** — paste as text **or send a PDF file**. Non-resume or
   unreadable (scanned) input is rejected with a hint.
3. Paste the **job description**.
4. Answer each question by **typing or sending a voice message**. `/end`
   finishes early; `/cancel` aborts.
5. You get the same scored summary at the end.
---
 
## 7. Where the data goes
 
Every answer is written immediately to `interviews.db` (SQLite), so nothing is
lost even if a session ends early. Both front ends write to the **same**
database. Two tables:
 
- `sessions` — one row per interview (resume, job description, final scores).
- `qa_pairs` — one row per question/answer (your data for preprocessing).
Inspect it any time:
 
```bash
sqlite3 interviews.db "SELECT phase, question, answer FROM qa_pairs;"
```
 
---
 
## 8. Troubleshooting
 
| What you see | What it means | Fix |
|---|---|---|
| `No module named streamlit` | streamlit installed under a different Python | Run `pip install` in the **same** env, or use `python -m streamlit run app.py` |
| `api_key client option must be set` | The `.env` isn't being read | Confirm `.env` sits next to `app.py`; confirm `llm.py` calls `load_dotenv()`; restart fully |
| `name 'Path' is not defined` | `from pathlib import Path` missing in `llm.py` | Add the import, or use plain `load_dotenv()` |
| `429 insufficient_quota` | Key works, but the account has no credit | Add credit at platform.openai.com → Billing (ChatGPT Plus does **not** fund the API) |
| `TELEGRAM_BOT_TOKEN not found` | Bot token missing from `.env` | Add `TELEGRAM_BOT_TOKEN=...` from @BotFather |
| Bot ignores a sent PDF | Document handler not registered / order wrong | `filters.Document.ALL` must be listed **before** the text handler in `ASK_RESUME` |
| "This doesn't look like a resume" | Validation rejected the input | Send a real resume; for PDFs, make sure the text is **selectable**, not a scan/image |
| "That PDF has no readable text" | Scanned/image PDF — no extractable text | Send a text-based PDF, or paste the resume |
| Mic shows the old recording | Streamlit caching the audio widget | Key the mic per turn (`key=f"audio_{ss.turn}"`); use Streamlit ≥ 1.39 |
| Transcription slightly wrong | Whisper mishears proper nouns | Edit the text box before submitting (web); the evaluator also ignores minor term slips |
| Interviewer repeats a question | asked-questions list not being appended | Confirm `generate_question` appends `pending_question` to `asked_questions` |
 
---
 
## 9. Configuration knobs
 
- **Models** — in `llm.py`: `INTERVIEWER_MODEL`, `EVALUATOR_MODEL`, and
  `PROFILE_MODEL` (all default `gpt-4o-mini`). Bump the evaluator for stricter
  scoring.
- **Profile compression** — the `compress_profile()` prompt in `llm.py`
  controls what the interviewer sees. Loosen the ~250-word cap or add a section
  if questions feel too generic.
- **History window** — both `app.py` and `bot.py` pass `history[-3:]` to the
  interviewer. Increase the slice for more context per turn (more tokens).
- **Questions per phase** — the `turns_in_phase >= 4` cap in `app.py` / `bot.py`.
- **Phases** — edit the `PHASES` list and `PHASE_GUIDANCE` in `prompts.py`.
- **Resume validation strictness** — `min_chars` and the keyword/contact rules
  in `resume_utils.py` (`looks_like_resume`).