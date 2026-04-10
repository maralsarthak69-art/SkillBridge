import json
import re
from groq import Groq
from django.conf import settings


# ── Prompts ───────────────────────────────────────────────────────────────────

CAPSTONE_BRIEF_PROMPT = """
You are a senior engineering mentor who designs unique, practical capstone projects.
Given a list of skill gaps and a target role, generate ONE unique mini-capstone project.

Return ONLY a valid JSON object with exactly these keys:
- "title": string (creative, specific project name)
- "description": string (2-3 sentences explaining what the project does and its real-world value)
- "tech_stack": array of strings (specific technologies to use)
- "deliverables": array of strings (4-6 concrete, measurable things to build/submit)
- "evaluation_rubric": array of objects, each with:
    - "criterion": string (what is being evaluated)
    - "weight": integer (percentage, all weights must sum to 100)
    - "description": string (what good looks like for this criterion)
- "difficulty": "beginner" | "intermediate" | "advanced"

Make the project realistic, buildable in 2-4 weeks, and directly relevant to the target role.
Return ONLY the JSON object, no other text.
"""

CAPSTONE_REVIEW_PROMPT = """
You are a senior engineering mentor reviewing a capstone project submission.
You will be given the project brief, evaluation rubric, and a GitHub repository description.

Review the submission and return ONLY a valid JSON object with exactly these keys:
- "score": integer (0-100, based on rubric weights)
- "review_summary": string (2-3 sentences overall assessment)
- "strengths": array of strings (3-5 specific things done well)
- "improvements": array of strings (3-5 specific, actionable improvements)

Be honest, constructive, and specific. Base the score strictly on the rubric criteria.
Return ONLY the JSON object, no other text.
"""


# ── JSON Parser ───────────────────────────────────────────────────────────────

def _parse_json_object(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r",\s*}", "}", raw)   # trailing commas in objects
    raw = re.sub(r",\s*\]", "]", raw)  # trailing commas in arrays
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    # Try extracting JSON object with regex
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse LLM response as JSON object.\nRaw:\n{raw[:300]}")


# ── Capstone Generator ────────────────────────────────────────────────────────

def generate_capstone_brief(gap_report, target_role: str = "") -> dict:
    """
    Generate a unique capstone project brief from a gap report.
    Returns a structured dict with title, description, tech_stack, deliverables, rubric.
    """
    missing_gaps = gap_report.gaps.filter(user_has_it=False).order_by("priority")
    skill_lines = [f"- {g.skill_name} ({g.priority} priority)" for g in missing_gaps]
    skills_text = "\n".join(skill_lines) if skill_lines else "- General backend development"
    role = target_role or gap_report.target_role or "Backend Engineer"

    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": CAPSTONE_BRIEF_PROMPT},
            {"role": "user", "content": f"Target role: {role}\n\nSkill gaps to address:\n{skills_text}"},
        ],
        temperature=0.4,
        max_tokens=1500,
    )

    raw = response.choices[0].message.content.strip()
    return _parse_json_object(raw)


def create_capstone(user_profile, gap_report_id: int):
    """
    Orchestrate capstone generation and save to DB.
    Returns the saved Capstone instance.
    """
    from core_engine.models import GapReport, Capstone

    try:
        gap_report = GapReport.objects.get(id=gap_report_id, user_profile=user_profile)
    except GapReport.DoesNotExist:
        raise ValueError("Gap report not found or does not belong to this user.")

    brief = generate_capstone_brief(gap_report)

    difficulty = brief.get("difficulty", "intermediate")
    if difficulty not in ("beginner", "intermediate", "advanced"):
        difficulty = "intermediate"

    capstone = Capstone.objects.create(
        user_profile=user_profile,
        gap_report=gap_report,
        title=brief.get("title", "Capstone Project"),
        description=brief.get("description", ""),
        tech_stack=brief.get("tech_stack", []),
        deliverables=brief.get("deliverables", []),
        evaluation_rubric=brief.get("evaluation_rubric", []),
        difficulty=difficulty,
        target_role=gap_report.target_role,
    )

    return capstone


# ── Capstone Reviewer ─────────────────────────────────────────────────────────

def review_capstone_submission(capstone, github_url: str):
    """
    Review a capstone submission against its rubric using Groq.
    Returns the saved CapstoneReview instance.
    """
    from core_engine.models import CapstoneReview

    rubric_text = json.dumps(capstone.evaluation_rubric, indent=2)
    deliverables_text = "\n".join(f"- {d}" for d in capstone.deliverables)

    user_content = (
        f"Project Title: {capstone.title}\n"
        f"Description: {capstone.description}\n\n"
        f"Expected Deliverables:\n{deliverables_text}\n\n"
        f"Evaluation Rubric:\n{rubric_text}\n\n"
        f"GitHub Repository URL: {github_url}\n\n"
        "Review this submission based on the rubric. "
        "Infer what was likely built from the repo URL and project context."
    )

    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": CAPSTONE_REVIEW_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        max_tokens=1000,
    )

    raw = response.choices[0].message.content.strip()
    result = _parse_json_object(raw)

    score = int(result.get("score", 0))
    score = max(0, min(100, score))

    # Delete existing review if re-submitting
    CapstoneReview.objects.filter(capstone=capstone).delete()

    review = CapstoneReview.objects.create(
        capstone=capstone,
        github_url=github_url,
        review_summary=result.get("review_summary", ""),
        score=score,
        strengths=result.get("strengths", []),
        improvements=result.get("improvements", []),
    )

    return review
