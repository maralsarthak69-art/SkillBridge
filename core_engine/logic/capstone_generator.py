"""
capstone_generator.py — Mini-Capstone Generator

Prompt Engineering Strategy:
    The prompt is structured in 3 layers:
    1. PERSONA    — sets the LLM as a senior engineering mentor
    2. CONSTRAINT — forces uniqueness by seeding with user's specific gap combo
    3. FORMAT     — strict JSON schema for reliable parsing

    Uniqueness is achieved by combining:
        - The user's specific gap list (not generic)
        - Their target role
        - Their existing skills (so we don't ask them to use what they don't have)
        - A "challenge mode": coding | strategy | architecture

    This means two users with different gaps always get different capstones.
"""

import json
import re
from groq import Groq
from django.conf import settings


# ── Prompt Templates ──────────────────────────────────────────────────────────

CAPSTONE_SYSTEM_PROMPT = """
You are a senior engineering mentor at a top tech company.
Your job is to design a unique, practical mini-capstone project for a developer.

The project must:
1. Directly address the developer's specific skill gaps (not generic tutorials)
2. Be completable in 1–2 weeks as a solo project
3. Produce a tangible, demonstrable artifact (GitHub repo, deployed app, etc.)
4. Be specific enough that two different developers get completely different projects

Return ONLY a valid JSON object with exactly these keys:
{
  "title": string (creative, specific — not generic like "Build a REST API"),
  "challenge_type": "coding" | "strategy" | "architecture",
  "problem_statement": string (2-3 sentences — the real-world problem being solved),
  "tech_stack": array of strings (only from the gap skills + existing skills),
  "core_tasks": array of 4-6 strings (specific, measurable implementation tasks),
  "stretch_goal": string (one advanced extension for extra challenge),
  "evaluation_rubric": array of objects [{
    "criterion": string,
    "weight": integer,
    "what_good_looks_like": string
  }] (weights must sum to 100),
  "estimated_days": integer (realistic solo estimate),
  "difficulty": "intermediate" | "advanced"
}

Return ONLY the JSON object. No markdown, no explanation.
"""


def _build_user_prompt(gap_skills: list[str], existing_skills: list[str],
                       target_role: str, challenge_type: str) -> str:
    gaps_text     = ", ".join(gap_skills[:8])   # cap at 8 to keep prompt focused
    existing_text = ", ".join(existing_skills[:6])
    return (
        f"Target Role: {target_role}\n"
        f"Challenge Type: {challenge_type}\n\n"
        f"Skills to LEARN (must be central to the project):\n{gaps_text}\n\n"
        f"Skills already known (can be used as supporting tools):\n{existing_text}\n\n"
        "Design a unique mini-capstone project that forces the developer to "
        "deeply use the skills they need to learn."
    )


# ── JSON Parser ───────────────────────────────────────────────────────────────

def _parse_capstone_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*\]", "]", raw)

    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Fallback: extract JSON object
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse capstone JSON.\nRaw:\n{raw[:400]}")


# ── Rubric Validator ──────────────────────────────────────────────────────────

def _normalize_rubric(rubric: list) -> list:
    """Ensure rubric weights sum to 100."""
    if not rubric:
        return rubric
    total = sum(r.get("weight", 0) for r in rubric)
    if total == 0:
        return rubric
    if total != 100:
        # Normalize proportionally
        for r in rubric:
            r["weight"] = round(r.get("weight", 0) / total * 100)
        # Fix rounding drift on last item
        diff = 100 - sum(r["weight"] for r in rubric)
        rubric[-1]["weight"] += diff
    return rubric


# ── Main Generator ────────────────────────────────────────────────────────────

def generate_mini_capstone(
    gap_skills:      list[str],
    existing_skills: list[str],
    target_role:     str = "Software Engineer",
    challenge_type:  str = "coding",
) -> dict:
    """
    Generate a unique mini-capstone project tailored to a user's specific skill gaps.

    Args:
        gap_skills:      Skills the user needs to learn (from gap analysis)
        existing_skills: Skills the user already has (from parsed CV)
        target_role:     The job role they're targeting
        challenge_type:  "coding" | "strategy" | "architecture"

    Returns:
        Structured capstone dict with title, tasks, rubric, etc.
    """
    if not gap_skills:
        raise ValueError("Cannot generate a capstone without skill gaps.")

    valid_types = {"coding", "strategy", "architecture"}
    if challenge_type not in valid_types:
        challenge_type = "coding"

    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": CAPSTONE_SYSTEM_PROMPT},
            {"role": "user",   "content": _build_user_prompt(
                gap_skills, existing_skills, target_role, challenge_type
            )},
        ],
        temperature=0.5,   # higher temp = more creative/unique projects
        max_tokens=1500,
    )

    raw    = response.choices[0].message.content.strip()
    result = _parse_capstone_json(raw)

    # Validate and normalize
    result["challenge_type"] = challenge_type
    result["evaluation_rubric"] = _normalize_rubric(result.get("evaluation_rubric", []))

    difficulty = result.get("difficulty", "intermediate")
    if difficulty not in ("intermediate", "advanced"):
        result["difficulty"] = "intermediate"

    return result


def generate_capstone_from_gap_report(gap_report, challenge_type: str = "coding") -> dict:
    """
    Convenience wrapper — takes a GapReport model instance directly.
    Extracts gap skills and user's existing skills automatically.
    """
    # Get missing skills from gap report
    gap_skills = [
        g.skill_name for g in gap_report.gaps.filter(user_has_it=False)
                                              .order_by("priority")
    ]

    # Get user's existing skills from their latest CV
    existing_skills = []
    latest_cv = gap_report.user_profile.cvs.first()
    if latest_cv:
        tech = latest_cv.extracted_skills.get("technical_skills", [])
        existing_skills = [s.get("skill", "") for s in tech if s.get("skill")]

    return generate_mini_capstone(
        gap_skills=gap_skills,
        existing_skills=existing_skills,
        target_role=gap_report.target_role or "Software Engineer",
        challenge_type=challenge_type,
    )
