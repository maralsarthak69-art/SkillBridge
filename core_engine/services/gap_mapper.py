import json
import re
from groq import Groq
from django.conf import settings


# ── Groq Prompt ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are a technical skills extractor. Extract required skills from a Job Description.

Return ONLY a valid JSON array. Each object must have exactly these keys:
- "skill": string
- "priority": "high", "medium", or "low"  
- "reason": string

CRITICAL: Every object must be properly closed with }. The array must end with ]
Do not add any text before or after the JSON array.

Example format:
[{"skill": "Python", "priority": "high", "reason": "Core language for the role."}]
"""


# ── JD Skill Extractor ────────────────────────────────────────────────────────

def extract_required_skills(jd_text: str) -> list:
    """
    Send a Job Description to Groq and extract required micro-skills.
    Returns a list of dicts: [{ skill, priority, reason }, ...]
    """
    client = Groq(api_key=settings.GROQ_API_KEY)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract required skills from this Job Description:\n\n{jd_text}"},
        ],
        temperature=0.0,
        max_tokens=1500,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # Fix the most common LLM artifact: last item missing closing } before ]
    # Pattern: "some text"]\n] or "some text"]\n  ]
    raw = re.sub(r'("(?:[^"\\]|\\.)*")\s*\]\s*\n?\s*\]?\s*$', r'\1}]', raw.strip())
    raw = re.sub(r',\s*\]', ']', raw)  # trailing commas

    try:
        skills = json.loads(raw)
        if not isinstance(skills, list):
            raise ValueError("Expected a JSON array")
        return skills
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}\nRaw:\n{raw[:300]}")


# ── Gap Differ ────────────────────────────────────────────────────────────────

def map_gaps(user_skills: list, required_skills: list) -> list:
    """
    Diff user's skills against JD requirements.
    user_skills: list of skill name strings (from ParsedCV.extracted_skills)
    required_skills: list of dicts from extract_required_skills()
    Returns: required_skills list with 'user_has_it' bool added to each item.
    """
    user_skill_names = {s.lower().strip() for s in user_skills}

    result = []
    for req in required_skills:
        skill_name = req.get("skill", "")
        skill_lower = skill_name.lower().strip()

        # Check exact or partial match
        has_it = (
            skill_lower in user_skill_names
            or any(skill_lower in u or u in skill_lower for u in user_skill_names)
        )

        result.append({
            "skill_name": skill_name,
            "priority": req.get("priority", "medium"),
            "reason": req.get("reason", ""),
            "user_has_it": has_it,
        })

    return result


# ── Orchestrator ──────────────────────────────────────────────────────────────

def analyze_gap(user_profile, jd_text: str, target_role: str = "") -> object:
    """
    Full pipeline: extract JD skills → diff against user CV → save to DB.
    Returns the saved GapReport instance.
    """
    from core_engine.models import GapReport, SkillGap, ParsedCV

    # Get user's latest parsed CV skills
    latest_cv = ParsedCV.objects.filter(user_profile=user_profile).first()
    user_skills = []
    if latest_cv:
        tech = latest_cv.extracted_skills.get("technical_skills", [])
        user_skills = [s.get("skill", "") for s in tech if s.get("skill")]

    # Extract required skills from JD
    required_skills = extract_required_skills(jd_text)

    # Diff
    gap_items = map_gaps(user_skills, required_skills)

    # Save GapReport
    report = GapReport.objects.create(
        user_profile=user_profile,
        jd_text=jd_text,
        target_role=target_role,
    )

    # Save individual SkillGap records
    SkillGap.objects.bulk_create([
        SkillGap(
            report=report,
            skill_name=item["skill_name"],
            priority=item["priority"],
            reason=item["reason"],
            user_has_it=item["user_has_it"],
        )
        for item in gap_items
    ])

    return report
