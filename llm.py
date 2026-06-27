"""OpenAI wrapper. Both calls force JSON output and parse defensively.

Reads OPENAI_API_KEY from the environment. Set it before running:
    export OPENAI_API_KEY="sk-..."
"""
import json
import os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Pick whatever model your key has access to. gpt-4o-mini is cheap and fine
# for a prototype; bump to a stronger model for the evaluator if scoring
# quality matters.
INTERVIEWER_MODEL = "gpt-4o-mini"
EVALUATOR_MODEL = "gpt-4o-mini"


def _call_json(model: str, prompt: str, temperature: float) -> dict:
    """Call the model, force JSON, parse defensively."""
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.choices[0].message.content
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Strip stray fences / prose if the model misbehaves, then retry parse.
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start:end + 1])
        raise


def ask_question(prompt: str) -> dict:
    # Moderate temperature -> natural variation in phrasing.
    return _call_json(INTERVIEWER_MODEL, prompt, temperature=0.7)


def evaluate(prompt: str) -> dict:
    # Low temperature -> consistent scoring across candidates.
    return _call_json(EVALUATOR_MODEL, prompt, temperature=0.2)


def transcribe(audio_file) -> str:
    """Transcribe recorded audio (from st.audio_input) to text via Whisper.

    audio_file is the object returned by st.audio_input - .getvalue() gives bytes.
    """
    audio_bytes = audio_file.getvalue()
    resp = client.audio.transcriptions.create(
        model="whisper-1",
        file=("answer.wav", audio_bytes),
    )
    return resp.text.strip()