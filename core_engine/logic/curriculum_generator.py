"""
curriculum_generator.py — Dual-Path Curriculum Generator (Phase 3)

Design Philosophy:
    - SKILL-CENTRIC structure: each gap skill = one learning unit with both paths
    - MODULAR resource slots: hacker_path.resources and certified_path.resources
      are lists that Rutuja's YouTube/Udemy API can populate later
    - UNIQUE capstones: each mini-capstone is generated from the specific skill
      combination, making copy-paste impossible
    - AUTOMATED review: proof-of-work submissions are scored by Llama-3 against
      the capstone rubric

Curriculum JSON Schema (per skill unit):
    {
        "skill":          str,
        "gap_severity":   str,
        "hacker_path":    { resources: [...], estimated_hours: int, free: true },
        "certified_path": { resources: [...], estimated_hours: int, free: false },
        "mini_capstone":  { task, deliverable, proof_of_work_format, rubric, difficulty }
    }
"""

import json
import re
from groq import Groq
from django.conf import settings


# ── Resource Slot Structure ───────────────────────────────────────────────────
# These are the placeholder structures Rutuja's APIs will fill.
# Each resource has a `source_hook` field that tells the API fetcher what to query.

def _make_resource_slot(title: str, url: str, resource_type: str,
                        estimated_hours: float, source_hook: str = "") -> dict:
    """
    Standard resource slot. source_hook is the query string for Rutuja's API.
    e.g. source_hook="fastapi tutorial python" → YouTube API query
    """
    return {
        "title":           title,
        "url":             url,
        "type":            resource_type,   # "video" | "article" | "course" | "docs" | "project"
        "estimated_hours": estimated_hours,
        "source_hook":     source_hook,     # Rutuja's API will replace url using this
        "api_enriched":    False,           # flips to True when Rutuja's API fills it
    }


# ── Static Resource Library ───────────────────────────────────────────────────
# Curated fallback resources per skill. Rutuja's API enriches these at runtime.

HACKER_RESOURCES = {
    "fastapi":        [_make_resource_slot("FastAPI Official Docs",          "https://fastapi.tiangolo.com",                "docs",    4,  "fastapi python tutorial"),
                       _make_resource_slot("Build a REST API with FastAPI",  "https://github.com/tiangolo/fastapi",         "project", 6,  "fastapi project github")],
    "kubernetes":     [_make_resource_slot("Kubernetes Official Docs",       "https://kubernetes.io/docs/home/",            "docs",    6,  "kubernetes beginner tutorial"),
                       _make_resource_slot("Play with Kubernetes",           "https://labs.play-with-k8s.com",              "project", 4,  "kubernetes hands on lab")],
    "aws":            [_make_resource_slot("AWS Free Tier Hands-on",         "https://aws.amazon.com/free/",                "project", 8,  "aws free tier tutorial"),
                       _make_resource_slot("AWS Skill Builder (Free)",       "https://skillbuilder.aws",                    "course",  6,  "aws skill builder free")],
    "terraform":      [_make_resource_slot("Terraform Learn",                "https://developer.hashicorp.com/terraform/tutorials", "docs", 5, "terraform tutorial beginner"),
                       _make_resource_slot("Terraform on GitHub",            "https://github.com/hashicorp/terraform",      "project", 4,  "terraform examples github")],
    "langchain":      [_make_resource_slot("LangChain Docs",                 "https://python.langchain.com/docs/get_started/introduction", "docs", 4, "langchain python tutorial"),
                       _make_resource_slot("LangChain Cookbook",             "https://github.com/langchain-ai/langchain/tree/master/cookbook", "project", 6, "langchain project examples")],
    "redis":          [_make_resource_slot("Redis University (Free)",        "https://university.redis.com",                "course",  4,  "redis tutorial free"),
                       _make_resource_slot("Redis Docs",                     "https://redis.io/docs/",                      "docs",    3,  "redis getting started")],
    "docker":         [_make_resource_slot("Docker Official Docs",           "https://docs.docker.com/get-started/",        "docs",    4,  "docker tutorial beginner"),
                       _make_resource_slot("Play with Docker",               "https://labs.play-with-docker.com",           "project", 3,  "docker hands on lab")],
    "typescript":     [_make_resource_slot("TypeScript Handbook",            "https://www.typescriptlang.org/docs/handbook/intro.html", "docs", 5, "typescript tutorial"),
                       _make_resource_slot("TypeScript Exercises",           "https://typescript-exercises.github.io",      "project", 4,  "typescript exercises")],
    "graphql":        [_make_resource_slot("GraphQL Official Docs",          "https://graphql.org/learn/",                  "docs",    4,  "graphql tutorial"),
                       _make_resource_slot("GraphQL Playground",             "https://github.com/graphql/graphql-playground","project", 3,  "graphql project")],
    "ci/cd":          [_make_resource_slot("GitHub Actions Docs",            "https://docs.github.com/en/actions",          "docs",    4,  "github actions tutorial"),
                       _make_resource_slot("CI/CD with GitHub Actions",      "https://github.com/features/actions",         "project", 5,  "github actions ci cd project")],
    "go":             [_make_resource_slot("Go Tour (Official)",             "https://go.dev/tour/welcome/1",               "docs",    6,  "golang tutorial beginner"),
                       _make_resource_slot("Go by Example",                  "https://gobyexample.com",                     "article", 4,  "go by example")],
    "rust":           [_make_resource_slot("The Rust Book",                  "https://doc.rust-lang.org/book/",             "docs",    10, "rust programming tutorial"),
                       _make_resource_slot("Rustlings",                      "https://github.com/rust-lang/rustlings",      "project", 6,  "rustlings exercises")],
    "pytorch":        [_make_resource_slot("PyTorch Tutorials",              "https://pytorch.org/tutorials/",              "docs",    8,  "pytorch tutorial beginner"),
                       _make_resource_slot("Fast.ai (Free Course)",          "https://course.fast.ai",                      "course",  12, "fastai deep learning free")],
    "microservices":  [_make_resource_slot("Microservices.io Patterns",      "https://microservices.io/patterns/index.html","article", 4,  "microservices patterns tutorial"),
                       _make_resource_slot("Build Microservices with Docker","https://github.com/dockersamples/example-voting-app", "project", 6, "microservices docker example")],
}

CERTIFIED_RESOURCES = {
    "fastapi":        [_make_resource_slot("FastAPI - The Complete Course",  "https://www.udemy.com/course/fastapi-the-complete-course/", "course", 15, "fastapi udemy course"),
                       _make_resource_slot("Python REST APIs with FastAPI",  "https://www.linkedin.com/learning/",          "course",  8,  "fastapi linkedin learning")],
    "kubernetes":     [_make_resource_slot("CKA Certification Prep",         "https://www.udemy.com/course/certified-kubernetes-administrator-with-practice-tests/", "cert", 40, "kubernetes cka udemy"),
                       _make_resource_slot("Kubernetes for Developers (CKAD)","https://www.coursera.org/learn/google-kubernetes-engine", "cert", 30, "kubernetes ckad coursera")],
    "aws":            [_make_resource_slot("AWS Certified Solutions Architect","https://aws.amazon.com/certification/certified-solutions-architect-associate/", "cert", 40, "aws solutions architect certification"),
                       _make_resource_slot("AWS on Udemy (Stephane Maarek)", "https://www.udemy.com/course/aws-certified-solutions-architect-associate-saa-c03/", "course", 25, "aws udemy stephane maarek")],
    "terraform":      [_make_resource_slot("HashiCorp Terraform Associate",  "https://www.hashicorp.com/certification/terraform-associate", "cert", 20, "terraform certification hashicorp"),
                       _make_resource_slot("Terraform on Udemy",             "https://www.udemy.com/course/terraform-beginner-to-advanced/", "course", 15, "terraform udemy course")],
    "langchain":      [_make_resource_slot("LangChain on Coursera",          "https://www.coursera.org/learn/langchain-chat-with-your-data", "course", 10, "langchain coursera"),
                       _make_resource_slot("LangChain on Udemy",             "https://www.udemy.com/course/langchain/",      "course",  12, "langchain udemy")],
    "redis":          [_make_resource_slot("Redis Certified Developer",      "https://university.redis.com/certification/", "cert",    20, "redis certification"),
                       _make_resource_slot("Redis on Udemy",                 "https://www.udemy.com/course/redis-the-complete-developers-guide-p/", "course", 12, "redis udemy course")],
    "docker":         [_make_resource_slot("Docker & Kubernetes on Udemy",   "https://www.udemy.com/course/docker-and-kubernetes-the-complete-guide/", "course", 20, "docker kubernetes udemy"),
                       _make_resource_slot("Docker Certified Associate",     "https://training.mirantis.com/certification/dca-certification-exam/", "cert", 25, "docker certified associate")],
    "typescript":     [_make_resource_slot("TypeScript on Udemy",            "https://www.udemy.com/course/understanding-typescript/", "course", 15, "typescript udemy"),
                       _make_resource_slot("TypeScript on Pluralsight",      "https://www.pluralsight.com/paths/typescript-core-language", "course", 10, "typescript pluralsight")],
    "ci/cd":          [_make_resource_slot("DevOps CI/CD on Udemy",          "https://www.udemy.com/course/devops-with-docker-kubernetes-and-azure-devops/", "course", 20, "cicd devops udemy"),
                       _make_resource_slot("GitHub Actions on Coursera",     "https://www.coursera.org/learn/devops-and-software-engineering", "course", 15, "github actions coursera")],
    "go":             [_make_resource_slot("Go Programming on Udemy",        "https://www.udemy.com/course/go-the-complete-developers-guide/", "course", 15, "golang udemy"),
                       _make_resource_slot("Go on Pluralsight",              "https://www.pluralsight.com/paths/go-core-language", "course", 12, "golang pluralsight")],
    "pytorch":        [_make_resource_slot("Deep Learning with PyTorch",     "https://www.udemy.com/course/pytorch-for-deep-learning-and-computer-vision/", "course", 20, "pytorch udemy"),
                       _make_resource_slot("PyTorch on Coursera (DeepLearning.AI)", "https://www.coursera.org/specializations/deep-learning", "cert", 40, "pytorch coursera deeplearning")],
    "microservices":  [_make_resource_slot("Microservices on Udemy",         "https://www.udemy.com/course/microservices-with-node-js-and-react/", "course", 25, "microservices udemy"),
                       _make_resource_slot("Microservices on Coursera",      "https://www.coursera.org/learn/ibm-microservices", "course", 15, "microservices coursera ibm")],
}

DEFAULT_HACKER = [_make_resource_slot("Official Documentation",  "https://roadmap.sh", "docs",    4, "{skill} tutorial documentation"),
                  _make_resource_slot("GitHub Search",           "https://github.com/search", "project", 4, "{skill} project github")]
DEFAULT_CERTIFIED = [_make_resource_slot("Udemy Course",         "https://www.udemy.com/courses/search/?q={skill}", "course", 15, "{skill} udemy course"),
                     _make_resource_slot("Coursera Course",      "https://www.coursera.org/search?query={skill}",   "course", 12, "{skill} coursera")]


def _get_resources(skill_name: str, path_type: str) -> list:
    """Get resources for a skill, falling back to defaults."""
    key = skill_name.lower().strip()
    library = HACKER_RESOURCES if path_type == "hacker" else CERTIFIED_RESOURCES
    resources = library.get(key, [])
    if not resources:
        defaults = DEFAULT_HACKER if path_type == "hacker" else DEFAULT_CERTIFIED
        resources = [
            {**r, "title": r["title"].replace("{skill}", skill_name),
                  "url":   r["url"].replace("{skill}", skill_name),
                  "source_hook": r["source_hook"].replace("{skill}", skill_name.lower())}
            for r in defaults
        ]
    return resources


# ── Mini-Capstone Generator ───────────────────────────────────────────────────

CAPSTONE_SYSTEM_PROMPT = """
You are a senior engineering mentor designing unique, anti-copy-paste coding challenges.

Given a skill to learn and the learner's existing skills, design ONE mini-capstone task.

Rules for uniqueness (CRITICAL):
1. The task must combine the NEW skill with at least one EXISTING skill
2. Include a specific real-world constraint that makes generic solutions fail
   (e.g. "must handle 10k concurrent requests", "must work offline", "must cost <$5/month")
3. The proof-of-work must be a GitHub repo with specific, verifiable artifacts

Return ONLY a valid JSON object:
{
  "task_title": string (specific, not generic),
  "problem_statement": string (2-3 sentences, real-world scenario),
  "specific_constraint": string (the unique constraint that prevents copy-paste),
  "deliverable": string (exactly what to build),
  "proof_of_work_format": string (what the GitHub repo must contain),
  "rubric": [
    {"criterion": string, "weight": integer, "pass_condition": string}
  ],
  "estimated_days": integer,
  "difficulty": "intermediate" | "advanced"
}

Rubric weights must sum to 100. Return ONLY the JSON object.
"""


def _generate_mini_capstone(skill_name: str, existing_skills: list,
                             gap_severity: str) -> dict:
    """Generate a unique mini-capstone for a specific skill gap."""
    existing_text = ", ".join(existing_skills[:5]) if existing_skills else "general programming"
    difficulty    = "advanced" if gap_severity == "critical" else "intermediate"

    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": CAPSTONE_SYSTEM_PROMPT},
            {"role": "user",   "content":
                f"Skill to learn: {skill_name}\n"
                f"Learner already knows: {existing_text}\n"
                f"Difficulty level: {difficulty}\n"
                "Design a unique mini-capstone that forces deep use of this skill."
            },
        ],
        temperature=0.6,
        max_tokens=1000,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*\]", "]", raw)

    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            # Normalize rubric weights
            rubric = result.get("rubric", [])
            total  = sum(r.get("weight", 0) for r in rubric)
            if total and total != 100:
                for r in rubric:
                    r["weight"] = round(r.get("weight", 0) / total * 100)
                diff = 100 - sum(r["weight"] for r in rubric)
                if rubric:
                    rubric[-1]["weight"] += diff
            result["rubric"] = rubric
            return result
    except json.JSONDecodeError:
        pass

    # Fallback capstone
    return {
        "task_title":          f"Build a production-ready {skill_name} service",
        "problem_statement":   f"Implement a real-world application using {skill_name} integrated with your existing {existing_text} skills.",
        "specific_constraint": "Must handle edge cases and include error handling.",
        "deliverable":         f"A working {skill_name} application with tests.",
        "proof_of_work_format":"GitHub repo with README, tests, and deployment instructions.",
        "rubric": [
            {"criterion": "Functionality",  "weight": 40, "pass_condition": "Core features work correctly"},
            {"criterion": "Code Quality",   "weight": 30, "pass_condition": "Clean, documented code"},
            {"criterion": "Tests",          "weight": 20, "pass_condition": "At least 5 passing tests"},
            {"criterion": "Documentation",  "weight": 10, "pass_condition": "README with setup instructions"},
        ],
        "estimated_days": 7,
        "difficulty":     "intermediate",
    }


# ── Dual-Path Roadmap Generator ───────────────────────────────────────────────

def generate_dual_path_roadmap(gap_list: list, existing_skills: list = None,
                               generate_capstones: bool = True) -> dict:
    """
    Convert a gap list into a dual-path curriculum roadmap.

    Args:
        gap_list:          List of gap dicts from identify_precise_gaps()
        existing_skills:   User's current skills (for capstone personalization)
        generate_capstones: If True, generates Llama-3 capstones (slower but unique)

    Returns:
        {
            "roadmap": [learning_unit, ...],
            "summary": { total_skills, total_hacker_hours, total_certified_hours,
                         critical_count, estimated_weeks_hacker, estimated_weeks_certified }
        }

    Each learning_unit:
        {
            "skill":          str,
            "gap_severity":   str,
            "priority":       str,
            "hacker_path":    { resources: [...], estimated_hours: int, free: True },
            "certified_path": { resources: [...], estimated_hours: int, free: False },
            "mini_capstone":  { task_title, problem_statement, ... } | None
        }
    """
    existing_skills = existing_skills or []

    # Only generate roadmap for explicit skill gaps (not functional/hidden)
    # Hidden/functional gaps are addressed through the capstone tasks themselves
    explicit_gaps = [g for g in gap_list if g.get("gap_type") == "explicit"]
    other_gaps    = [g for g in gap_list if g.get("gap_type") != "explicit"]

    roadmap              = []
    total_hacker_hours   = 0
    total_certified_hours = 0

    for gap in explicit_gaps:
        skill_name   = gap.get("skill", "")
        gap_severity = gap.get("gap_severity", "moderate")
        priority     = gap.get("priority", "preferred")
        bridge_hint  = gap.get("bridge_hint", "")

        hacker_resources    = _get_resources(skill_name, "hacker")
        certified_resources = _get_resources(skill_name, "certified")

        hacker_hours    = sum(r["estimated_hours"] for r in hacker_resources)
        certified_hours = sum(r["estimated_hours"] for r in certified_resources)

        total_hacker_hours    += hacker_hours
        total_certified_hours += certified_hours

        # Generate unique capstone (or skip for bonus/minor gaps to save API calls)
        capstone = None
        if generate_capstones and gap_severity in ("critical", "moderate"):
            capstone = _generate_mini_capstone(skill_name, existing_skills, gap_severity)

        unit = {
            "skill":        skill_name,
            "gap_severity": gap_severity,
            "priority":     priority,
            "bridge_hint":  bridge_hint,
            "hacker_path": {
                "resources":       hacker_resources,
                "estimated_hours": hacker_hours,
                "free":            True,
                # Hook for Rutuja's YouTube API
                "youtube_query":   f"{skill_name} tutorial for beginners",
            },
            "certified_path": {
                "resources":       certified_resources,
                "estimated_hours": certified_hours,
                "free":            False,
                # Hook for Rutuja's Udemy API
                "udemy_query":     f"{skill_name} complete course",
            },
            "mini_capstone": capstone,
        }
        roadmap.append(unit)

    # Sort: critical first, then moderate, then minor
    severity_order = {"critical": 0, "moderate": 1, "minor": 2}
    roadmap.sort(key=lambda x: severity_order.get(x["gap_severity"], 1))

    # Add a summary of functional/hidden gaps as development notes
    development_notes = [
        {
            "type":        g.get("gap_type"),
            "skill":       g.get("skill"),
            "priority":    g.get("priority"),
            "bridge_hint": g.get("bridge_hint", ""),
        }
        for g in other_gaps
    ]

    return {
        "roadmap": roadmap,
        "development_notes": development_notes,
        "summary": {
            "total_skills":               len(roadmap),
            "critical_skills":            sum(1 for u in roadmap if u["gap_severity"] == "critical"),
            "total_hacker_hours":         total_hacker_hours,
            "total_certified_hours":      total_certified_hours,
            "estimated_weeks_hacker":     round(total_hacker_hours / 10, 1),
            "estimated_weeks_certified":  round(total_certified_hours / 10, 1),
            "capstones_generated":        sum(1 for u in roadmap if u["mini_capstone"]),
        },
    }


# ── Automated AI Reviewer ─────────────────────────────────────────────────────

REVIEWER_SYSTEM_PROMPT = """
You are a senior engineering mentor reviewing a capstone project submission.

You will receive:
1. The original capstone task requirements
2. The learner's proof-of-work (GitHub URL + description)

Your job: Evaluate the submission against the rubric and return a PASS or FAIL verdict.

Be strict but fair. A PASS requires meeting the pass_condition for criteria
totaling at least 70% of the rubric weight.

Return ONLY a valid JSON object:
{
  "verdict":        "PASS" | "FAIL",
  "total_score":    integer (0-100),
  "criterion_scores": [{"criterion": string, "score": integer, "weight": integer, "feedback": string}],
  "overall_feedback": string (2-3 sentences),
  "strengths":      [string],
  "improvements":   [string],
  "next_steps":     string
}

Return ONLY the JSON object.
"""


def automated_ai_reviewer(capstone_task: dict, proof_of_work: str) -> dict:
    """
    Review a learner's proof-of-work submission against the capstone task rubric.

    Args:
        capstone_task:  The mini_capstone dict from generate_dual_path_roadmap()
        proof_of_work:  GitHub URL or description of what was built

    Returns:
        {
            verdict:          "PASS" | "FAIL",
            total_score:      int (0-100),
            criterion_scores: [...],
            overall_feedback: str,
            strengths:        [str],
            improvements:     [str],
            next_steps:       str,
        }
    """
    rubric_text = json.dumps(capstone_task.get("rubric", []), indent=2)

    user_content = (
        f"CAPSTONE TASK:\n"
        f"Title: {capstone_task.get('task_title', '')}\n"
        f"Problem: {capstone_task.get('problem_statement', '')}\n"
        f"Constraint: {capstone_task.get('specific_constraint', '')}\n"
        f"Deliverable: {capstone_task.get('deliverable', '')}\n"
        f"Expected proof-of-work: {capstone_task.get('proof_of_work_format', '')}\n\n"
        f"RUBRIC:\n{rubric_text}\n\n"
        f"LEARNER SUBMISSION:\n{proof_of_work}\n\n"
        "Evaluate this submission. Infer what was built from the GitHub URL and description."
    )

    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        temperature=0.1,
        max_tokens=1000,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*\]", "]", raw)

    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            # Ensure verdict is valid
            if result.get("verdict") not in ("PASS", "FAIL"):
                score = result.get("total_score", 0)
                result["verdict"] = "PASS" if score >= 70 else "FAIL"
            return result
    except json.JSONDecodeError:
        pass

    return {
        "verdict":          "FAIL",
        "total_score":      0,
        "criterion_scores": [],
        "overall_feedback": "Could not parse submission review. Please resubmit.",
        "strengths":        [],
        "improvements":     ["Ensure your GitHub repo is public and contains the required artifacts."],
        "next_steps":       "Review the capstone requirements and resubmit.",
    }
