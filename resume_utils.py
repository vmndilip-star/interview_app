"""resume_utils.py — resume ingestion (PDF/text) and validation.

Sits next to app.py, bot.py, prompts.py, llm.py, db.py.

app.py  uses:  extract_resume_text (Streamlit upload), looks_like_resume
bot.py  uses:  extract_resume_from_bytes (Telegram file bytes), looks_like_resume
"""

import re
from io import BytesIO


def extract_resume_text(uploaded_file) -> str:
    """Extract text from a Streamlit-uploaded PDF or text file.

    `uploaded_file` is the object returned by st.file_uploader (has .name/.read()).
    """
    name = (getattr(uploaded_file, "name", "") or "").lower()
    data = uploaded_file.read()  # bytes; read once per rerun

    if name.endswith(".pdf"):
        from pypdf import PdfReader  # lazy import so text-only setups don't need it
        reader = PdfReader(BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()

    # anything else: treat as plain text
    return data.decode("utf-8", errors="ignore").strip()


def extract_resume_from_bytes(data: bytes, filename: str = "") -> str:
    """Extract text from downloaded file bytes (used by the Telegram bot).

    Telegram gives raw bytes + a filename, not a Streamlit upload object.
    """
    name = (filename or "").lower()

    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()

    return data.decode("utf-8", errors="ignore").strip()


# --- validation: cheap heuristic gate --------------------------------------

# Words a real resume almost always carries.
_SECTION_WORDS = [
    "experience", "education", "skills", "projects", "work", "employment",
    "certification", "summary", "objective", "responsibilities",
    "university", "bachelor", "master", "achievements", "professional",
]
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")


def looks_like_resume(text: str, min_chars: int = 200) -> tuple[bool, str]:
    """Cheap heuristic. Returns (is_resume, reason).

    Blocks obvious junk (short text, random paragraphs) without an API call.
    """
    t = (text or "").strip()
    if len(t) < min_chars:
        return False, "That content is too short to be a resume."

    low = t.lower()
    hits = sum(1 for w in _SECTION_WORDS if w in low)
    has_contact = bool(_EMAIL.search(t) or _PHONE.search(t))

    # A couple of section words, OR one section word plus contact details.
    if hits >= 3 or (hits >= 1 and has_contact):
        return True, "ok"
    return False, (
        "This doesn't look like a resume — no recognizable resume sections "
        "(experience, education, skills…) or contact details were found."
    )


# --- optional stricter check via the LLM (use only for borderline cases) ----

def llm_is_resume(text: str, client, model: str = "gpt-4o-mini") -> bool:
    """Optional LLM classifier. Pass your existing OpenAI `client` from llm.py.

    Returns True if the text reads as a resume/CV. Costs one cheap call, so
    call this only when looks_like_resume() is ambiguous, not on every run.
    """
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": (
                "Reply with exactly YES or NO. Is the following text a person's "
                "resume/CV (work history, skills, education)? It is NOT a resume "
                "if it's a job description, an article, or random text."
            )},
            {"role": "user", "content": text[:3000]},
        ],
    )
    return resp.choices[0].message.content.strip().upper().startswith("YES")