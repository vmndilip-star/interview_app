"""Prompt templates for the interview practice app.

Two jobs, kept separate on purpose:
  - INTERVIEWER runs once per turn and asks ONE question.
  - EVALUATOR runs once at the end and scores the whole transcript.
"""

# Phases run in this fixed order. The app (not the model) tracks which
# phase is active, which is what keeps the sequence reliable.
PHASES = ["introduction", "experience", "projects", "technical", "situational"]

PHASE_GUIDANCE = {
    "introduction": 'Start with "Tell me about yourself." Keep it open.',
    "experience": "Their work history and career trajectory from the resume.",
    "projects": ("Drill into REAL projects from the resume: their specific role, "
                 "the decisions they made, trade-offs, what broke and why."),
    "technical": "Pointed technical questions tied to the job description's required skills.",
    "situational": "A realistic on-the-job scenario for this role; ask how they'd handle it.",
}


def _format_history(history: list[dict]) -> str:
    """Render prior turns so the interviewer knows what's already been covered."""
    if not history:
        return "(no questions asked yet - this is the very first question)"
    lines = []
    for h in history:
        lines.append(f"Q: {h['question']}\nA: {h['answer']}")
    return "\n\n".join(lines)


def build_interviewer_prompt(job_description: str, resume: str, current_phase: str,
                             history: list[dict] | None = None) -> str:
    history = history or []
    already_asked = "\n".join(f"- {h['question']}" for h in history) or "(none yet)"

    return f"""You are an experienced technical interviewer conducting a LIVE interview.
Interview the candidate the way a real, sharp interviewer would.

=== JOB DESCRIPTION ===
{job_description}

=== CANDIDATE RESUME ===
{resume}

=== CONVERSATION SO FAR ===
{_format_history(history)}

=== QUESTIONS YOU HAVE ALREADY ASKED (do NOT repeat or rephrase these) ===
{already_asked}

=== HOW A REAL INTERVIEWER BEHAVES ===
- Ask ONE question at a time. Never ask the next until the candidate answers.
- Your next question MUST be new. Never repeat or lightly reword anything in the
  "already asked" list above. If the intro is done, do NOT say "tell me about
  yourself" again - move forward.
- Build on what they just said. If their last answer opened a thread worth pulling,
  follow it. Otherwise move to a fresh area of the resume or job description.
- Sound like a person, not a form. Natural phrasing, contractions, transitions
  that react to their last answer ("okay, interesting - so...").
- Never answer for them, never coach, never reveal scoring.
- If an answer is vague or buzzword-heavy, ask ONE probing follow-up before moving on.
- Pull questions straight from the resume and job description. Make them defend
  specific claims they made.

=== CURRENT PHASE: {current_phase} ===
{PHASE_GUIDANCE[current_phase]}

Respond ONLY as JSON, no other text:
{{
  "phase": "{current_phase}",
  "question": "<the single NEW question to ask now>",
  "phase_complete": <true if this phase has been covered enough, else false>
}}"""


def build_evaluator_prompt(job_description: str, transcript: str) -> str:
    return f"""You are an interview evaluator. Given the job description and the full
interview transcript, evaluate the candidate objectively.

=== JOB DESCRIPTION ===
{job_description}

=== TRANSCRIPT ===
{transcript}

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