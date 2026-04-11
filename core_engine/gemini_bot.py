"""
gemini_bot.py — Gemini AI Chatbot Service

Three coaching modes:
    1. english_coach     — Corrects grammar, improves communication in real-time
    2. interview_coach   — Acts as a hiring manager, evaluates STARR method
    3. conflict_coach    — Plays a difficult boss/client, trains negotiation skills
"""

import json
import logging
import re
from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

BOT_MODES         = {"english_coach", "interview_coach", "conflict_coach"}
MAX_HISTORY_TURNS = 20
MAX_MESSAGE_CHARS = 3000
GEMINI_MODEL      = "gemini-2.5-flash"

# Process-level flag — bootstrap table only once
_bot_table_ready = False

# ── System Prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {

    "english_coach": """
You are Alex, a warm and encouraging English communication coach.
Help candidates improve their spoken and written English for professional settings.

When the user sends a message:
1. Respond naturally to what they said — keep the conversation flowing
2. Gently point out grammar, vocabulary, or clarity issues
3. Show the corrected version clearly
4. Give ONE practical tip

Tone: encouraging, never harsh. Ask follow-up questions to keep them practicing.

IMPORTANT: Always return ONLY a valid JSON object. No markdown, no extra text.
{
  "reply": "Your natural conversational response",
  "corrections": [
    {"original": "wrong phrase", "corrected": "correct phrase", "tip": "why this is better"}
  ],
  "encouragement": "One sentence of positive reinforcement",
  "follow_up": "A question to keep them practicing"
}
If there are no corrections, return "corrections": [].
""",

    "interview_coach": """
You are Jordan, a senior hiring manager at a top tech company with 15 years of experience.
Conduct a behavioral interview to help candidates practice.

Your job:
1. Ask ONE behavioral question at a time (STARR format)
2. Evaluate answers against the STARR method:
   - Situation: context set?
   - Task: responsibility explained?
   - Action: specific steps described?
   - Result: outcome shared with metrics?
   - Reflection: what was learned?
3. Give constructive feedback and ask a follow-up or next question

IMPORTANT: Always return ONLY a valid JSON object. No markdown, no extra text.
{
  "reply": "Your response as the interviewer",
  "starr_evaluation": {
    "situation":  {"present": true, "feedback": "one sentence"},
    "task":       {"present": false, "feedback": "one sentence"},
    "action":     {"present": true, "feedback": "one sentence"},
    "result":     {"present": false, "feedback": "one sentence"},
    "reflection": {"present": false, "feedback": "one sentence"}
  },
  "overall_score": 5,
  "strength": "What they did well",
  "improvement": "What to add or improve",
  "next_question": "Your follow-up or next question"
}
On the FIRST message only: set starr_evaluation to null, overall_score to 0,
strength to "", improvement to "", next_question to "".
""",

    "conflict_coach": """
You are Morgan, a professional negotiation and conflict resolution coach.
Roleplay as a difficult character to help candidates practice professional diplomacy.

Play ONE of these roles:
- difficult_boss: micromanaging, dismisses ideas, takes credit
- difficult_client: refuses to pay, keeps changing requirements, rude
- difficult_colleague: passive-aggressive, undermines the candidate

Stay in character. Be realistically difficult — not abusive, but genuinely challenging.
After each candidate response, step OUT of character briefly to coach them.

IMPORTANT: Always return ONLY a valid JSON object. No markdown, no extra text.
tone_assessment MUST be a descriptive string, never a number.
{
  "in_character_reply": "Your reply AS the difficult person",
  "coach_feedback": {
    "tone_assessment": "Descriptive string e.g. Professional and calm under pressure",
    "what_worked": "What they did well",
    "what_to_improve": "Specific language or approach to improve",
    "suggested_phrase": "A better way they could have phrased their response"
  },
  "scenario_escalation": "slight",
  "diplomacy_score": 7
}
On the FIRST message only: introduce the scenario and character, set coach_feedback to null,
diplomacy_score to 0, scenario_escalation to "slight".
""",
}

# ── Default fallback responses per mode ──────────────────────────────────────

DEFAULT_RESPONSES = {
    "english_coach": {
        "reply": "I'm here to help you practice your English. Please go ahead and say something!",
        "corrections": [],
        "encouragement": "Keep going — every conversation is practice!",
        "follow_up": "What would you like to talk about today?",
    },
    "interview_coach": {
        "reply": "Hi! I'm Jordan. Let's start your behavioral interview practice. Tell me about yourself.",
        "starr_evaluation": None,
        "overall_score": 0,
        "strength": "",
        "improvement": "",
        "next_question": "",
    },
    "conflict_coach": {
        "in_character_reply": "Let's begin the scenario. I'll play your difficult boss today.",
        "coach_feedback": None,
        "scenario_escalation": "slight",
        "diplomacy_score": 0,
    },
}


# ── NeonDB Session Storage ────────────────────────────────────────────────────

CREATE_BOT_SESSIONS = """
CREATE TABLE IF NOT EXISTS bot_sessions (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER     NOT NULL,
    mode       VARCHAR(30) NOT NULL,
    history    JSONB       NOT NULL DEFAULT '[]',
    created_at TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP   NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_sessions_user_mode ON bot_sessions(user_id, mode);
"""


def _ensure_bot_table():
    """Bootstrap bot_sessions table once per process lifetime."""
    global _bot_table_ready
    if _bot_table_ready:
        return
    try:
        from .logic.neon_client import get_neon_conn
        with get_neon_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_BOT_SESSIONS)
            conn.commit()
        _bot_table_ready = True
    except Exception as e:
        logger.error(f"[BotSession] Table bootstrap failed: {e}")
        raise


def _load_session(user_id: int, mode: str) -> tuple:
    """Load session history from NeonDB. Returns (session_id, history)."""
    from .logic.neon_client import get_neon_conn
    try:
        with get_neon_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, history FROM bot_sessions WHERE user_id=%s AND mode=%s LIMIT 1",
                    (user_id, mode),
                )
                row = cur.fetchone()
                if row:
                    history = row["history"] or []
                    if not isinstance(history, list):
                        logger.warning(f"[BotSession] Corrupt history for user={user_id} mode={mode}, resetting.")
                        history = []
                    return row["id"], history
    except Exception as e:
        logger.error(f"[BotSession] Load failed: {e}")
    return None, []


def _save_session(user_id: int, mode: str, history: list, session_id) -> int:
    """
    Upsert session history in NeonDB using INSERT ... ON CONFLICT DO UPDATE.
    Eliminates race conditions. Returns session_id.
    """
    from .logic.neon_client import get_neon_conn
    try:
        with get_neon_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO bot_sessions (user_id, mode, history, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (user_id, mode)
                    DO UPDATE SET history = EXCLUDED.history, updated_at = NOW()
                    RETURNING id
                    """,
                    (user_id, mode, json.dumps(history)),
                )
                row = cur.fetchone()
            conn.commit()
        return int(row["id"])
    except Exception as e:
        logger.error(f"[BotSession] Save failed: {e}")
        return session_id or 0


def _reset_session(user_id: int, mode: str) -> bool:
    """Delete session history. Returns True if deleted, False otherwise."""
    from .logic.neon_client import get_neon_conn
    try:
        with get_neon_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM bot_sessions WHERE user_id=%s AND mode=%s",
                    (user_id, mode),
                )
                deleted = cur.rowcount
            conn.commit()
        return deleted > 0
    except Exception as e:
        logger.error(f"[BotSession] Reset failed: {e}")
        return False


# ── JSON Parser ───────────────────────────────────────────────────────────────

def _parse_gemini_json(raw: str, mode: str) -> dict:
    """
    Parse Gemini's response into a structured dict.
    Falls back to default response for the mode if parsing fails.
    """
    if not raw or not raw.strip():
        logger.warning(f"[GeminiBot] Empty response for mode={mode}")
        return DEFAULT_RESPONSES[mode].copy()

    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = re.sub(r",\s*}", "}", cleaned)
    cleaned = re.sub(r",\s*\]", "]", cleaned)

    # Direct parse
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Extract JSON object from mixed text
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    logger.warning(f"[GeminiBot] Could not parse JSON for mode={mode}, using fallback")
    fallback = DEFAULT_RESPONSES[mode].copy()
    fallback["reply"] = raw  # preserve raw text as reply
    return fallback


def _ensure_mode_fields(parsed: dict, mode: str) -> dict:
    """
    Ensure all required fields for a mode are present.
    Fills missing fields with safe defaults.
    """
    defaults = DEFAULT_RESPONSES[mode]
    for key, default_val in defaults.items():
        if key not in parsed or parsed[key] is None and default_val is not None:
            parsed.setdefault(key, default_val)

    # Normalize tone_assessment to string for conflict_coach
    if mode == "conflict_coach":
        feedback = parsed.get("coach_feedback")
        if isinstance(feedback, dict):
            ta = feedback.get("tone_assessment")
            if isinstance(ta, (int, float)):
                feedback["tone_assessment"] = str(ta)

    return parsed


# ── Main Chat Function ────────────────────────────────────────────────────────

def chat(user_id: int, mode: str, user_message: str, reset: bool = False) -> dict:
    """
    Send a message to the Gemini bot in the specified mode.

    Args:
        user_id:      Django user ID
        mode:         "english_coach" | "interview_coach" | "conflict_coach"
        user_message: What the user said/typed (max 3000 chars)
        reset:        Clear conversation history and start fresh

    Returns:
        Structured dict with AI response + coaching feedback + session_id + mode + turn_count
    """
    if mode not in BOT_MODES:
        raise ValueError(f"Invalid mode '{mode}'. Choose from: {', '.join(sorted(BOT_MODES))}")

    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    # Truncate oversized messages
    if len(user_message) > MAX_MESSAGE_CHARS:
        user_message = user_message[:MAX_MESSAGE_CHARS]
        logger.info(f"[GeminiBot] Message truncated to {MAX_MESSAGE_CHARS} chars for user={user_id}")

    # Bootstrap table once
    _ensure_bot_table()

    # Reset if requested
    if reset:
        _reset_session(user_id, mode)

    # Load history
    session_id, history = _load_session(user_id, mode)

    # Build Gemini conversation
    client   = genai.Client(api_key=settings.GEMINI_API_KEY)
    contents = [
        types.Content(
            role="user" if turn["role"] == "user" else "model",
            parts=[types.Part(text=turn["content"])]
        )
        for turn in history
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPTS[mode],
                temperature=0.7,
                max_output_tokens=1500,
            ),
        )
        raw_reply = response.text.strip()
    except Exception as e:
        logger.error(f"[GeminiBot] API call failed for user={user_id} mode={mode}: {e}")
        raise

    # Parse and validate response
    parsed = _parse_gemini_json(raw_reply, mode)
    parsed = _ensure_mode_fields(parsed, mode)

    # Update history
    history.append({"role": "user",  "content": user_message})
    history.append({"role": "model", "content": raw_reply})

    # Trim to max turns
    if len(history) >= MAX_HISTORY_TURNS * 2:
        history = history[-(MAX_HISTORY_TURNS * 2):]

    # Save session
    session_id = _save_session(user_id, mode, history, session_id)

    parsed["session_id"] = int(session_id)
    parsed["mode"]       = mode
    parsed["turn_count"] = len(history) // 2

    return parsed
