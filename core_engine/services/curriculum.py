import json
import re
from groq import Groq
from django.conf import settings

# ── System Prompts ────────────────────────────────────────────────────────────

HACKER_PROMPT = """
You are a self-taught engineer mentor who builds learning paths using FREE resources.
Given a list of skill gaps, create an ordered learning path using only:
- Official documentation
- Free YouTube tutorials (reference by channel/topic, not specific URLs)
- GitHub repositories and open source projects
- Free tiers of platforms (freeCodeCamp, The Odin Project, roadmap.sh, etc.)
- Hands-on build projects

Return ONLY a valid JSON array. Each object must have exactly these keys:
- "skill_name": string
- "step_order": integer (starting from 1)
- "title": string (concise action-oriented title)
- "description": string (what to do and why, 1-2 sentences)
- "resource_url": string (best free URL, use https://roadmap.sh or https://docs.python.org style links)
- "resource_type": one of "video", "article", "project", "docs"
- "estimated_hours": number (realistic hours to complete)

Order steps from foundational to advanced. High priority gaps come first.
Return ONLY the JSON array, no other text.
"""

CERTIFIED_PROMPT = """
You are a career coach who builds structured certification-based learning paths.
Given a list of skill gaps, create an ordered learning path using:
- Udemy courses (reference by topic)
- Coursera specializations
- Official vendor certifications (AWS, GCP, Azure, etc.)
- LinkedIn Learning
- Pluralsight

Return ONLY a valid JSON array. Each object must have exactly these keys:
- "skill_name": string
- "step_order": integer (starting from 1)
- "title": string (concise action-oriented title)
- "description": string (what to study and the certification goal, 1-2 sentences)
- "resource_url": string (use https://www.udemy.com, https://www.coursera.org, https://aws.amazon.com/certification style links)
- "resource_type": one of "course", "cert", "video"
- "estimated_hours": number (realistic hours including study + exam prep)

Order steps from foundational to advanced. High priority gaps come first.
Return ONLY the JSON array, no other text.
"""


# ── JSON Parser ───────────────────────────────────────────────────────────────

def _parse_json_array(raw: str) -> list:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r",\s*\]", "]", raw)  # trailing commas
    # Fix missing closing brace on last item
    raw = re.sub(r'("(?:[^"\\]|\\.)*")\s*\]\s*$', r'\1}]', raw)
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    raise ValueError(f"Could not parse LLM response as JSON array.\nRaw:\n{raw[:300]}")


# ── Curriculum Generator ──────────────────────────────────────────────────────

def generate_curriculum(gap_report, path_type: str) -> list:
    """
    Send gap report's missing skills to Groq and get back ordered learning steps.
    path_type: "hacker" or "certified"
    Returns list of step dicts.
    """
    missing_gaps = gap_report.gaps.filter(user_has_it=False).order_by("priority", "skill_name")

    if not missing_gaps.exists():
        return []

    # Build a concise skill list for the prompt
    skill_lines = []
    for gap in missing_gaps:
        skill_lines.append(f"- {gap.skill_name} (priority: {gap.priority}) — {gap.reason}")
    skills_text = "\n".join(skill_lines)

    system_prompt = HACKER_PROMPT if path_type == "hacker" else CERTIFIED_PROMPT

    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Create a learning path for these skill gaps:\n\n{skills_text}"},
        ],
        temperature=0.2,
        max_tokens=2000,
    )

    raw = response.choices[0].message.content.strip()
    return _parse_json_array(raw)


# ── Orchestrator ──────────────────────────────────────────────────────────────

def build_learning_path(user_profile, gap_report_id: int, path_type: str):
    """
    Full pipeline: fetch gap report → generate curriculum → save to DB.
    Returns the saved LearningPath instance.
    """
    from core_engine.models import GapReport, LearningPath, LearningStep

    try:
        gap_report = GapReport.objects.get(id=gap_report_id, user_profile=user_profile)
    except GapReport.DoesNotExist:
        raise ValueError("Gap report not found or does not belong to this user.")

    steps_data = generate_curriculum(gap_report, path_type)

    learning_path = LearningPath.objects.create(
        user_profile=user_profile,
        gap_report=gap_report,
        path_type=path_type,
        target_role=gap_report.target_role,
    )

    valid_resource_types = {"video", "article", "project", "course", "cert", "docs"}

    LearningStep.objects.bulk_create([
        LearningStep(
            learning_path=learning_path,
            skill_name=step.get("skill_name", ""),
            step_order=step.get("step_order", i + 1),
            title=step.get("title", ""),
            description=step.get("description", ""),
            resource_url=step.get("resource_url", "")[:200],
            resource_type=step.get("resource_type", "article") if step.get("resource_type") in valid_resource_types else "article",
            estimated_hours=float(step.get("estimated_hours", 0)),
        )
        for i, step in enumerate(steps_data)
    ])

    return learning_path
