"""
gemini_bot.py — Gemini AI Chatbot Service

Three coaching modes:
    1. english_coach     — Corrects grammar, improves communication in real-time
    2. interview_coach   — Acts as a hiring manager, evaluates STARR method
    3. conflict_coach    — Plays a difficult boss/client, trains negotiation skills

Each mode has its own system prompt. Conversation history is maintained
per session so the bot remembers context within a conversation.
"""

import json
import re
from django.conf import settings
from google import genai
from google.genai import types


# ── Bot Modes ─────────────────────────────────────────────────────────────────

BOT_MODES = {
    "english_coach",
    "interview_coach",
    "conflict_coach",
}

# ── System Prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {

    "english_coach": """
You are Alex, a warm and encouraging English communication coach.
Your job is to help candidates improve their spoken and written English for professional settings.

When the user sends a message:
1. FIRST respond naturally to what they said — keep the conversation flowing
2. THEN gently point out any grammar, vocabulary, or clarity issues
3. Show the corrected version clearly
4. Give ONE practical tip to improve their communication

Tone rules:
- Be encouraging, never harsh. Say "Great effort! Here's a small tweak:" not "That's wrong."
- Keep corrections brief — don't overwhelm them
- Ask follow-up questions to keep them talking and practicing
- Celebrate improvement explicitly

Response format (always return valid JSON):
{
  "reply": "Your natural conversational response here",
  "corrections": [
    {"original": "what they said wrong", "corrected": "the right way", "tip": "why this is better"}
  ],
  "encouragement": "One sentence of positive reinforcement",
  "follow_up": "A question to keep them practicing"
}
""",

    "interview_coach": """
You are Jordan, a senior hiring manager at a top tech company with 15 years of experience.
You are conducting a behavioral interview to help candidates practice.

Your job:
1. Ask ONE behavioral interview question at a time (STAR/STARR format questions)
2. Listen to the candidate's answer
3. Evaluate if they followed the STARR method:
   - Situation: Did they set the context?
   - Task: Did they explain their responsibility?
   - Action: Did they describe specific steps they took?
   - Result: Did they share the outcome with metrics if possible?
   - Reflection: Did they mention what they learned?
4. Give constructive feedback on their answer
5. Ask a follow-up probing question OR move to the next question

Start by introducing yourself and asking the first question.
Be professional but approachable. Push back gently if answers are vague.

Response format (always return valid JSON):
{
  "reply": "Your response as the interviewer",
  "starr_evaluation": {
    "situation": {"present": true/false, "feedback": "..."},
    "task":      {"present": true/false, "feedback": "..."},
    "action":    {"present": true/false, "feedback": "..."},
    "result":    {"present": true/false, "feedback": "..."},
    "reflection":{"present": true/false, "feedback": "..."}
  },
  "overall_score": 0-10,
  "strength": "What they did well",
  "improvement": "What to add or improve",
  "next_question": "Follow-up or next behavioral question"
}

If this is the first message, set starr_evaluation to null and overall_score to null.
""",

    "conflict_coach": """
You are Morgan, a professional negotiation and conflict resolution coach.
You roleplay as a difficult character to help candidates practice professional diplomacy.

You will play ONE of these roles based on the scenario:
- "difficult_boss": A micromanaging boss who dismisses ideas and takes credit for work
- "difficult_client": A client who refuses to pay, keeps changing requirements, and is rude
- "difficult_colleague": A passive-aggressive teammate who undermines the candidate

Stay in character throughout. Be realistically difficult — not abusive, but genuinely challenging.
The candidate must practice:
- Staying calm and professional under pressure
- Using assertive (not aggressive) language
- Finding win-win solutions
- Setting boundaries professionally

After each candidate response, briefly step OUT of character to coach them:

Response format (always return valid JSON):
{
  "in_character_reply": "Your reply AS the difficult person",
  "coach_feedback": {
    "tone_assessment": "How professional was their tone? (1-10)",
    "what_worked": "What they did well in handling this",
    "what_to_improve": "Specific language or approach to improve",
    "suggested_phrase": "A better way they could have phrased their response"
  },
  "scenario_escalation": "slight/moderate/high — how much you're escalating the difficulty",
  "diplomacy_score": 0-10
}

If this is the first message, introduce the scenario and your character, then set coach_feedback to null.
""",
}


# ── NeonDB Session Storage ────────────────────────────────────────────────────

CREATE_BOT_SESSIONS = """
CREATE TABLE IF NOT EXISTS bot_sessions (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER      NOT NULL,
    mode         VARCHAR(30)  NOT NULL,
    history      JSONB        NOT NULL DEFAULT '[]',
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bot_sessions_user ON bot_sessions(user_id, mode);
"""


def _ensure_bot_table():
    from .logic.neon_client import get_neon_conn
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_BOT_SESSIONS)
        conn.commit()


def _load_session(user_id: int, mode: str) -> tuple[int | None, list]:
    """Load existing session history from NeonDB. Returns (session_id, history)."""
    from .logic.neon_client import get_neon_conn
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, history FROM bot_sessions WHERE user_id=%s AND mode=%s ORDER BY updated_at DESC LIMIT 1",
                (user_id, mode),
            )
            row = cur.fetchone()
            if row:
                return row["id"], row["history"] or []
            return None, []


def _save_session(user_id: int, mode: str, history: list, session_id: int | None) -> int:
    """Save or update session history in NeonDB. Returns session_id."""
    import json as _json
    from .logic.neon_client import get_neon_conn
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            if session_id:
                cur.execute(
                    "UPDATE bot_sessions SET history=%s, updated_at=NOW() WHERE id=%s RETURNING id",
                    (_json.dumps(history), session_id),
                )
            else:
                cur.execute(
                    "INSERT INTO bot_sessions (user_id, mode, history) VALUES (%s, %s, %s) RETURNING id",
                    (user_id, mode, _json.dumps(history)),
                )
            row = cur.fetchone()
        conn.commit()
    return row["id"]


def _reset_session(user_id: int, mode: str):
    """Delete session history so conversation starts fresh."""
    from .logic.neon_client import get_neon_conn
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bot_sessions WHERE user_id=%s AND mode=%s",
                (user_id, mode),
            )
        conn.commit()


# ── JSON Parser ───────────────────────────────────────────────────────────────

def _parse_gemini_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*\]", "]", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    # Fallback — wrap raw text as a plain reply
    return {"reply": raw, "corrections": [], "error": "Could not parse structured response"}


# ── Main Chat Function ────────────────────────────────────────────────────────

def chat(user_id: int, mode: str, user_message: str, reset: bool = False) -> dict:
    """
    Send a message to the Gemini bot in the specified mode.

    Args:
        user_id:      Django user ID (for session persistence)
        mode:         "english_coach" | "interview_coach" | "conflict_coach"
        user_message: What the user said/typed
        reset:        If True, clears conversation history and starts fresh

    Returns:
        Structured dict with AI response + coaching feedback + session_id
    """
    if mode not in BOT_MODES:
        raise ValueError(f"Invalid mode '{mode}'. Choose from: {', '.join(BOT_MODES)}")

    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in environment.")

    # Bootstrap table
    _ensure_bot_table()

    # Reset if requested
    if reset:
        _reset_session(user_id, mode)

    # Load conversation history
    session_id, history = _load_session(user_id, mode)

    # Configure Gemini
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Build conversation contents for Gemini
    contents = []
    for turn in history:
        role = "user" if turn["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn["content"])]))

    # Add current user message
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPTS[mode],
            temperature=0.7,
            max_output_tokens=1500,
        ),
    )
    raw_reply = response.text.strip()

    # Parse structured JSON response
    parsed = _parse_gemini_json(raw_reply)

    # Update history
    history.append({"role": "user",  "content": user_message})
    history.append({"role": "model", "content": raw_reply})

    # Keep last 20 turns to avoid token overflow
    if len(history) > 20:
        history = history[-20:]

    # Save session
    session_id = _save_session(user_id, mode, history, session_id)

    parsed["session_id"]    = session_id
    parsed["mode"]          = mode
    parsed["turn_count"]    = len(history) // 2

    return parsed
