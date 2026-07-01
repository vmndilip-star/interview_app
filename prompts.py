"""Prompt templates for the interview practice app.

Two jobs, kept separate on purpose:
  - INTERVIEWER runs once per turn and asks ONE question.
  - EVALUATOR runs once at the end and scores the whole transcript.

Token notes:
  - The interviewer no longer gets the raw resume + job description every turn.
    It gets a COMPACT profile (built once per session by llm.compress_profile)
    plus only the last few turns of history and the running list of
    already-asked questions. That cuts repeated input tokens ~5-6x over a full
    interview while keeping repeat-prevention intact.
  - The static instruction block + the session-stable profile are placed FIRST
    so they form a stable prefix (friendlier to prompt caching); the volatile
    per-turn content (phase, recent history, asked list) comes after.
"""

# Phases run in this fixed order. The app (not the model) tracks which
# phase is active, which is what keeps the sequence reliable.
PHASES = ["introduction", "experience", "projects", "technical", "situational"]

PHASE_GUIDANCE = {
    "introduction": 'Start with "Tell me about yourself." Keep it open.',
    "experience": "Their work history and career trajectory from the profile.",
    "projects": ("Drill into REAL projects from the profile: their specific role, "
                 "the decisions they made, trade-offs, what broke and why."),
    "technical": "Pointed technical questions tied to the role's required skills.",
    "situational": "A realistic on-the-job scenario for this role; ask how they'd handle it.",
}


def _format_recent(recent_history: list[dict]) -> str:
    """Render only the most recent turns (caller passes a trimmed slice)."""
    if not recent_history:
        return "(no answers yet - this is the very first question)"
    return "\n\n".join(f"Q: {h['question']}\nA: {h['answer']}" for h in recent_history)


def _format_asked(asked_questions: list[str]) -> str:
    """The full list of question texts asked so far - cheap, one line each.

    This is kept even when older Q&A is trimmed from history, so the model can
    still avoid repeating questions across the whole interview.
    """
    if not asked_questions:
        return "(none yet)"
    return "\n".join(f"- {q}" for q in asked_questions)


def build_interviewer_prompt(profile: str, current_phase: str,
                             recent_history: list[dict] | None = None,
                             asked_questions: list[str] | None = None) -> str:
    """Build the per-turn interviewer prompt.

    profile         - compact candidate+role summary from llm.compress_profile
    current_phase   - one of PHASES
    recent_history  - the last ~3 turns only (caller trims: history[-3:])
    asked_questions - ALL question texts asked so far, to prevent repeats
    """
    recent_history = recent_history or []
    asked_questions = asked_questions or []

    # ---- stable prefix: identical instructions + session-stable profile ----
    return f"""You are an experienced technical interviewer conducting a LIVE interview.
Interview the candidate the way a real, sharp interviewer would.

=== HOW A REAL INTERVIEWER BEHAVES ===
- Ask ONE question at a time. Never ask the next until the candidate answers.
- Your next question MUST be new. Never repeat or lightly reword anything in the
  "already asked" list. If the intro is done, do NOT say "tell me about yourself"
  again - move forward.
- Build on what they just said. If their last answer opened a thread worth pulling,
  follow it. Otherwise move to a fresh area of the profile.
- Sound like a person, not a form. Natural phrasing, contractions, transitions
  that react to their last answer ("okay, interesting - so...").
- Never answer for them, never coach, never reveal scoring.
- If an answer is vague or buzzword-heavy, ask ONE probing follow-up before moving on.
- If an answer is empty, off-topic, or a clear non-answer ("I don't know", random
  text), don't pretend it was fine: briefly acknowledge it and either re-ask the
  same thing more simply ONCE, or move on. Do not reward it.
- Pull questions straight from the profile. Make the candidate defend specific
  claims they made.

=== CANDIDATE PROFILE (resume + role requirements, condensed) ===
{profile}

=== CURRENT PHASE: {current_phase} ===
{PHASE_GUIDANCE[current_phase]}

=== RECENT CONVERSATION (most recent turns only) ===
{_format_recent(recent_history)}

=== QUESTIONS ALREADY ASKED (do NOT repeat or reword any of these) ===
{_format_asked(asked_questions)}

Respond ONLY as JSON, no other text:
{{
  "phase": "{current_phase}",
  "question": "<the single NEW question to ask now>",
  "phase_complete": <true if this phase has been covered enough, else false>
}}"""


def build_evaluator_prompt(job_description: str, transcript: str) -> str:
    """Build the end-of-interview evaluator prompt.

    Uses the raw job description here (one call, at the end - cost is negligible)
    for maximum grounding. Explicitly instructed to penalize junk answers.
    """
    return f"""You are an interview evaluator. Given the job description and the full
interview transcript, evaluate the candidate objectively and honestly.

=== JOB DESCRIPTION ===
{job_description}

=== TRANSCRIPT ===
{transcript}

=== SCORING RULES ===
- Judge each answer on substance, not length. A short, correct answer can score well.
- An answer that is empty, off-topic, evasive, or a non-answer ("I don't know",
  filler, or random/irrelevant text) is a WEAK answer. Score it low, mark it
  "no" in per_question, and say plainly in the comment that it did not address
  the question. Do NOT invent merit that isn't in the transcript.
- Do not penalize minor transcription slips of technical terms (e.g. "pine cone"
  for "Pinecone") if the meaning is clearly correct.

Return ONLY valid JSON, no other text:
{{
  "introduction_rating": {{"score": <0-10>, "feedback": "<structure, clarity, relevance>"}},
  "technical": {{"score": <0-10>, "strengths": [], "weaknesses": [], "feedback": ""}},
  "non_technical": {{"score": <0-10>, "communication": <0-10>, "problem_solving": <0-10>, "feedback": ""}},
  "per_question": [{{"question": "", "answer_summary": "", "correct": "yes|no|partial", "comment": ""}}],
  "overall_score": <0-100>,
  "recommendation": "strong hire | hire | borderline | no hire",
  "summary": ""
}}"""