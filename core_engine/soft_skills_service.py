"""
soft_skills_service.py — Soft Skills Analysis & Grammar Correction

Reuses the existing Groq client pattern from core_engine/logic/*.
Does NOT create a new LLM client — imports the same setup used by
alignment_engine.py, curriculum_generator.py, and capstone_generator.py.
"""

import json
import re
from groq import Groq
from django.conf import settings


def _get_client() -> Groq:
    """
    Returns the shared Groq client using the same API key and pattern
    as alignment_engine.py, curriculum_generator.py, and capstone_generator.py.
    """
    return Groq(api_key=settings.GROQ_API_KEY)


# ── Soft Skills Extraction ────────────────────────────────────────────────────

SOFT_SKILLS_SYSTEM_PROMPT = """
You are an expert career coach and behavioral skills analyst.

Analyze the provided text (resume, bio, or job description) and extract all
soft skills and interpersonal competencies mentioned or implied.

For each soft skill found, assess:
- The skill name (universal, not jargon)
- Confidence level: how strongly it is evidenced (0.0 to 1.0)
- Evidence: the specific phrase or sentence that indicates this skill
- Development tip: one actionable sentence to strengthen this skill

Return ONLY a valid JSON object with exactly these keys:
{
  "soft_skills": [
    {
      "skill":           string,
      "confidence":      float (0.0 to 1.0),
      "evidence":        string,
      "development_tip": string
    }
  ],
  "top_strengths":   array of 3 skill name strings (highest confidence),
  "areas_to_develop": array of up to 3 skill name strings (lowest confidence or missing),
  "overall_profile": string (2 sentences summarizing the person's soft skill profile)
}

Return ONLY the JSON object. No markdown, no explanation.
"""


def analyze_soft_skills(text: str) -> dict:
    """
    Extract and analyze soft skills from any text input.
    Uses the same Groq client as the rest of the logic/ engine.

    Args:
        text: Resume text, bio, or any professional description

    Returns:
        {
            soft_skills:      [{skill, confidence, evidence, development_tip}],
            top_strengths:    [str, str, str],
            areas_to_develop: [str, ...],
            overall_profile:  str
        }
    """
    client = _get_client()

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SOFT_SKILLS_SYSTEM_PROMPT},
            {"role": "user",   "content": f"Analyze this text for soft skills:\n\n{text[:4000]}"},
        ],
        temperature=0.2,
        max_tokens=1500,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*\]", "]", raw)

    try:
        result = json.loads(raw)
        if isinstance(result, dict) and "soft_skills" in result:
            return result
    except json.JSONDecodeError:
        pass

    # Fallback: try to extract JSON object
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError("AI returned an invalid response for soft skills analysis.")


# ── Grammar Correction ────────────────────────────────────────────────────────

GRAMMAR_SYSTEM_PROMPT = """
You are a professional editor specializing in career documents (resumes, cover letters, bios).

Your job is to:
1. Correct all grammar, spelling, and punctuation errors
2. Improve sentence clarity and professional tone
3. Strengthen weak action verbs (e.g. "did" → "executed", "helped" → "facilitated")
4. Remove filler words and redundancy
5. Ensure consistent tense (past tense for past roles, present for current)

Return ONLY a valid JSON object with exactly these keys:
{
  "corrected_text": string (the full corrected version),
  "changes": [
    {
      "original":    string (the original phrase),
      "corrected":   string (the corrected phrase),
      "reason":      string (brief explanation)
    }
  ],
  "improvement_score": integer (0-100, how much the text improved),
  "readability_level": "entry" | "mid" | "senior" | "executive"
}

Return ONLY the JSON object. No markdown, no explanation.
"""


def correct_grammar(text: str) -> dict:
    """
    Correct grammar and improve professional tone of career text.
    Uses the same Groq client as the rest of the logic/ engine.

    Args:
        text: Resume bullet points, bio, or cover letter text

    Returns:
        {
            corrected_text:    str,
            changes:           [{original, corrected, reason}],
            improvement_score: int,
            readability_level: str
        }
    """
    client = _get_client()

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": GRAMMAR_SYSTEM_PROMPT},
            {"role": "user",   "content": f"Correct and improve this career text:\n\n{text[:3000]}"},
        ],
        temperature=0.1,
        max_tokens=2000,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*\]", "]", raw)

    try:
        result = json.loads(raw)
        if isinstance(result, dict) and "corrected_text" in result:
            return result
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError("AI returned an invalid response for grammar correction.")
