# Interview Practice App — Setup & Execution Guide

A Streamlit app that runs a mock interview. It reads a resume and job
description, plays the interviewer (asking one fresh question at a time),
lets the candidate answer by **typing or by voice** (recorded, then
transcribed with Whisper), logs every question/answer pair to a database,
and scores the full transcript at the end.

---

## 1. Prerequisites

- **Python 3.9+** installed.
- An **OpenAI API key** with billing enabled (the app uses it for both the
  interview questions and the voice transcription).
- A microphone (only needed if you want to use the voice-answer feature).

---

## 2. Project structure

```
interview_app/
├── app.py            # Streamlit UI + interview loop (run this)
├── prompts.py        # Interviewer and evaluator prompt templates
├── llm.py            # OpenAI calls (questions, evaluation, transcription)
├── db.py             # SQLite storage (sessions + qa_pairs tables)
├── requirements.txt  # Python packages
├── .env              # YOUR secret key (you create this — see step 4)
└── interviews.db     # Created automatically on first run
```

---

## 3. Install the packages

Open a terminal **in the project folder** (the one containing `app.py`) and run:

```bash
pip install -r requirements.txt
```

This installs `streamlit`, `openai`, and `python-dotenv`.

> **Important — use ONE Python.** If you have both Anaconda/conda and a
> separate system Python, make sure the `pip` you run here matches the
> `python`/`streamlit` you launch with in step 5. A mismatch causes
> `No module named streamlit` even though it "installed fine". The simplest
> rule: run `pip` and `streamlit` from the **same** terminal/environment.

---

## 4. Add your API key

Create a file named exactly **`.env`** in the project folder (same place as
`app.py`). Put your OpenAI key in it, one line, no extra keys needed:

```
OPENAI_API_KEY=sk-proj-your-actual-key-here
```

Rules that save headaches:
- One key per line.
- No spaces around the `=`.
- Quotes are optional (`OPENAI_API_KEY="sk-..."` also works).

**Verify the key loads** (run from the project folder):

```bash
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('KEY FOUND' if os.environ.get('OPENAI_API_KEY') else 'KEY MISSING')"
```

You want it to print `KEY FOUND`.

---

## 5. Run the app

From the project folder:

```bash
streamlit run app.py
```

If `streamlit` is "not recognized", use:

```bash
python -m streamlit run app.py
```

The app opens in your browser (usually at http://localhost:8501).

> After editing `.env` or any `.py` file, do a **full restart**: stop with
> `Ctrl+C` in the terminal, then run the command again. A browser refresh is
> not enough — the key and imports only load on a fresh start.

---

## 6. Using the app

1. **Setup screen** — paste a resume and a job description, click *Start interview*.
2. **Interview screen** — for each question:
   - **Type** your answer in the box, **or**
   - Click the **mic** to record, stop, and let it transcribe into the box.
   - Edit the text if the transcription misheard anything (names especially).
   - Click **Submit answer**. A new question appears with a fresh, empty box
     and mic.
   - Questions move through phases in order: introduction → experience →
     projects → technical → situational.
3. Click **End interview & evaluate** whenever you're done.
4. **Results screen** — see scores, a per-question breakdown, and a button to
   **download all Q&A pairs as JSON**.

---

## 7. Where the data goes

Every answer is written immediately to `interviews.db` (SQLite), so nothing
is lost even if a session ends early. Two tables:

- `sessions` — one row per interview (resume, job description, final scores).
- `qa_pairs` — one row per question/answer (this is your data for preprocessing).

Inspect it any time:

```bash
sqlite3 interviews.db "SELECT phase, question, answer FROM qa_pairs;"
```

Or use the **Download all Q&A (JSON)** button on the results screen.

---

## 8. Troubleshooting

| What you see | What it means | Fix |
|---|---|---|
| `No module named streamlit` | streamlit is installed under a different Python than the one you launched | Run `pip install -r requirements.txt` in the **same** terminal/env, or use `python -m streamlit run app.py` |
| `api_key client option must be set` | The `.env` isn't being read | Confirm `.env` sits next to `app.py`; confirm `llm.py` calls `load_dotenv()` at the top; restart fully |
| `name 'Path' is not defined` | `from pathlib import Path` missing in `llm.py` | Add the import, or change the load line to plain `load_dotenv()` |
| `429 insufficient_quota` | Key works, but the OpenAI account has no credit | Add credit at platform.openai.com → Billing. (ChatGPT Plus does **not** fund the API.) |
| Mic shows the old recording | Older Streamlit caching the audio widget | Make sure `app.py` keys the mic per turn (`key=f"audio_{ss.turn}"`); use Streamlit ≥ 1.39 |
| Transcription is slightly wrong | Whisper mishears proper nouns | Expected — edit the text box before submitting |

---

## 9. Configuration knobs

- **Model** — in `llm.py`, change `INTERVIEWER_MODEL` / `EVALUATOR_MODEL`
  (default `gpt-4o-mini`, cheap and fine for a prototype).
- **Questions per phase** — in `app.py`, the `turns_in_phase >= 4` cap controls
  how long each phase runs before moving on.
- **Phases** — edit the `PHASES` list and `PHASE_GUIDANCE` in `prompts.py`.
