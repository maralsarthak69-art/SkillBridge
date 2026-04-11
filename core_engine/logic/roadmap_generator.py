"""
roadmap_generator.py — Generates a personalised week-by-week RoadmapWeek plan.

Called automatically after CV upload (CVIntakeView).
Reads the user's SkillMap freshness scores and builds a structured learning
plan ordered from weakest → strongest skill, with curated free + paid resources.

No external AI calls — fully deterministic so it's fast and free.
"""

from core_engine.models import SkillMap, RoadmapWeek

# ── Resource catalogue ────────────────────────────────────────────────────────
# Curated free + paid resources per skill (canonical name → resources).
# Falls back to generic resources for unknown skills.

RESOURCE_CATALOGUE: dict[str, dict] = {
    "Python": {
        "free": [
            {"title": "Python Official Docs", "link": "https://docs.python.org/3/tutorial/"},
            {"title": "freeCodeCamp — Python Full Course", "link": "https://www.youtube.com/watch?v=rfscVS0vtbw"},
        ],
        "paid": [
            {"title": "100 Days of Code: Python Bootcamp", "platform": "Udemy", "link": "https://www.udemy.com/course/100-days-of-code/"},
        ],
    },
    "JavaScript": {
        "free": [
            {"title": "MDN JavaScript Guide", "link": "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide"},
            {"title": "javascript.info", "link": "https://javascript.info/"},
        ],
        "paid": [
            {"title": "The Complete JavaScript Course", "platform": "Udemy", "link": "https://www.udemy.com/course/the-complete-javascript-course/"},
        ],
    },
    "TypeScript": {
        "free": [
            {"title": "TypeScript Official Handbook", "link": "https://www.typescriptlang.org/docs/handbook/intro.html"},
            {"title": "Matt Pocock — Total TypeScript", "link": "https://www.totaltypescript.com/tutorials"},
        ],
        "paid": [
            {"title": "Understanding TypeScript", "platform": "Udemy", "link": "https://www.udemy.com/course/understanding-typescript/"},
        ],
    },
    "React": {
        "free": [
            {"title": "React Official Docs (react.dev)", "link": "https://react.dev/learn"},
            {"title": "Scrimba — Learn React", "link": "https://scrimba.com/learn/learnreact"},
        ],
        "paid": [
            {"title": "React — The Complete Guide", "platform": "Udemy", "link": "https://www.udemy.com/course/react-the-complete-guide-incl-redux/"},
        ],
    },
    "Next.js": {
        "free": [
            {"title": "Next.js Official Docs", "link": "https://nextjs.org/docs"},
            {"title": "Next.js App Router Tutorial", "link": "https://nextjs.org/learn"},
        ],
        "paid": [
            {"title": "Next.js & React — The Complete Guide", "platform": "Udemy", "link": "https://www.udemy.com/course/nextjs-react-the-complete-guide/"},
        ],
    },
    "Django": {
        "free": [
            {"title": "Django Official Tutorial", "link": "https://docs.djangoproject.com/en/stable/intro/tutorial01/"},
            {"title": "CS50W — Web Programming with Python", "link": "https://cs50.harvard.edu/web/"},
        ],
        "paid": [
            {"title": "Django & Python — The Complete Guide", "platform": "Udemy", "link": "https://www.udemy.com/course/python-django-the-practical-guide/"},
        ],
    },
    "FastAPI": {
        "free": [
            {"title": "FastAPI Official Docs", "link": "https://fastapi.tiangolo.com/tutorial/"},
            {"title": "freeCodeCamp — FastAPI Course", "link": "https://www.youtube.com/watch?v=0sOvCWFmrtA"},
        ],
        "paid": [
            {"title": "FastAPI — The Complete Course", "platform": "Udemy", "link": "https://www.udemy.com/course/fastapi-the-complete-course/"},
        ],
    },
    "PostgreSQL": {
        "free": [
            {"title": "PostgreSQL Official Tutorial", "link": "https://www.postgresql.org/docs/current/tutorial.html"},
            {"title": "freeCodeCamp — PostgreSQL Full Course", "link": "https://www.youtube.com/watch?v=qw--VYLpxG4"},
        ],
        "paid": [
            {"title": "SQL & PostgreSQL for Beginners", "platform": "Udemy", "link": "https://www.udemy.com/course/sql-and-postgresql/"},
        ],
    },
    "Docker": {
        "free": [
            {"title": "Docker Official Get Started", "link": "https://docs.docker.com/get-started/"},
            {"title": "TechWorld with Nana — Docker Tutorial", "link": "https://www.youtube.com/watch?v=3c-iBn73dDE"},
        ],
        "paid": [
            {"title": "Docker & Kubernetes: The Practical Guide", "platform": "Udemy", "link": "https://www.udemy.com/course/docker-kubernetes-the-practical-guide/"},
        ],
    },
    "Kubernetes": {
        "free": [
            {"title": "Kubernetes Official Docs", "link": "https://kubernetes.io/docs/tutorials/"},
            {"title": "TechWorld with Nana — Kubernetes Full Course", "link": "https://www.youtube.com/watch?v=X48VuDVv0do"},
        ],
        "paid": [
            {"title": "Kubernetes for the Absolute Beginners", "platform": "Udemy", "link": "https://www.udemy.com/course/learn-kubernetes/"},
        ],
    },
    "AWS": {
        "free": [
            {"title": "AWS Free Tier + Getting Started", "link": "https://aws.amazon.com/getting-started/"},
            {"title": "freeCodeCamp — AWS Certified Cloud Practitioner", "link": "https://www.youtube.com/watch?v=SOTamWNgDKc"},
        ],
        "paid": [
            {"title": "AWS Certified Solutions Architect", "platform": "Udemy", "link": "https://www.udemy.com/course/aws-certified-solutions-architect-associate-saa-c03/"},
        ],
    },
    "Machine Learning": {
        "free": [
            {"title": "Andrew Ng — ML Specialization (Coursera audit)", "link": "https://www.coursera.org/specializations/machine-learning-introduction"},
            {"title": "fast.ai — Practical Deep Learning", "link": "https://course.fast.ai/"},
        ],
        "paid": [
            {"title": "Machine Learning A-Z", "platform": "Udemy", "link": "https://www.udemy.com/course/machinelearning/"},
        ],
    },
    "LangChain": {
        "free": [
            {"title": "LangChain Official Docs", "link": "https://python.langchain.com/docs/get_started/introduction"},
            {"title": "freeCodeCamp — LangChain Crash Course", "link": "https://www.youtube.com/watch?v=lG7Uxts9SXs"},
        ],
        "paid": [
            {"title": "LangChain & Vector Databases in Production", "platform": "Activeloop", "link": "https://learn.activeloop.ai/courses/langchain"},
        ],
    },
    "Git": {
        "free": [
            {"title": "Pro Git Book (free)", "link": "https://git-scm.com/book/en/v2"},
            {"title": "GitHub Skills", "link": "https://skills.github.com/"},
        ],
        "paid": [
            {"title": "Git & GitHub Bootcamp", "platform": "Udemy", "link": "https://www.udemy.com/course/git-and-github-bootcamp/"},
        ],
    },
    "System Design": {
        "free": [
            {"title": "System Design Primer (GitHub)", "link": "https://github.com/donnemartin/system-design-primer"},
            {"title": "ByteByteGo — System Design YouTube", "link": "https://www.youtube.com/@ByteByteGo"},
        ],
        "paid": [
            {"title": "Grokking the System Design Interview", "platform": "Educative", "link": "https://www.educative.io/courses/grokking-the-system-design-interview"},
        ],
    },
    "REST API": {
        "free": [
            {"title": "REST API Tutorial", "link": "https://restfulapi.net/"},
            {"title": "freeCodeCamp — APIs and Microservices", "link": "https://www.freecodecamp.org/learn/back-end-development-and-apis/"},
        ],
        "paid": [
            {"title": "REST APIs with Flask and Python", "platform": "Udemy", "link": "https://www.udemy.com/course/rest-api-flask-and-python/"},
        ],
    },
}

# Generic fallback for skills not in the catalogue
GENERIC_RESOURCES = {
    "free": [
        {"title": "freeCodeCamp — Search for tutorials", "link": "https://www.freecodecamp.org/news/search/?query={skill}"},
        {"title": "MDN Web Docs", "link": "https://developer.mozilla.org/en-US/search?q={skill}"},
    ],
    "paid": [
        {"title": "Udemy — Top courses", "platform": "Udemy", "link": "https://www.udemy.com/courses/search/?q={skill}"},
    ],
}

# ── Task templates ────────────────────────────────────────────────────────────

TASK_TEMPLATES = {
    "basic":        "Build a small project demonstrating core {skill} concepts. Focus on fundamentals and write clean, readable code.",
    "intermediate": "Build a real-world mini-app using {skill}. Integrate it with at least one other technology from your stack.",
    "advanced":     "Architect and build a production-ready feature using {skill}. Include tests, error handling, and documentation.",
}

# ── Level mapping ─────────────────────────────────────────────────────────────

def _get_level(freshness_score: int) -> str:
    """Map freshness score to learning level."""
    if freshness_score >= 70:
        return "advanced"
    if freshness_score >= 40:
        return "intermediate"
    return "basic"


def _is_trending(growth_rate: float) -> bool:
    """Mark skill as trending if growth rate is above 0.5."""
    return growth_rate >= 0.5


def _get_resources(skill_name: str) -> dict:
    """Return curated resources for a skill, falling back to generic."""
    resources = RESOURCE_CATALOGUE.get(skill_name)
    if resources:
        return resources

    # Fill in skill name in generic template links
    return {
        "free": [
            {**r, "link": r["link"].replace("{skill}", skill_name.replace(" ", "+"))}
            for r in GENERIC_RESOURCES["free"]
        ],
        "paid": [
            {**r, "link": r["link"].replace("{skill}", skill_name.replace(" ", "+"))}
            for r in GENERIC_RESOURCES["paid"]
        ],
    }


# ── Main generator ────────────────────────────────────────────────────────────

def generate_roadmap_for_user(user) -> int:
    """
    Generate (or regenerate) the week-by-week RoadmapWeek plan for a user.

    Strategy:
    1. Read all skills from SkillMap, sorted by freshness_score ASC
       (weakest skills first — most important to improve)
    2. Cap at 12 weeks (manageable plan)
    3. Create one RoadmapWeek per skill
    4. Delete old weeks and replace with fresh plan

    Returns the number of weeks created.
    """
    skills = (
        SkillMap.objects
        .filter(user=user)
        .order_by("freshness_score")  # weakest first
        [:12]                          # max 12 weeks
    )

    if not skills:
        return 0

    # Delete existing roadmap weeks for this user (full regeneration)
    RoadmapWeek.objects.filter(user=user).delete()

    weeks_created = 0
    for i, skill_entry in enumerate(skills, start=1):
        skill_name = skill_entry.skill_name
        level      = _get_level(skill_entry.freshness_score)
        trending   = _is_trending(skill_entry.growth_rate)
        resources  = _get_resources(skill_name)
        task       = TASK_TEMPLATES[level].format(skill=skill_name)

        # Build a descriptive title
        level_label = {"basic": "Fundamentals", "intermediate": "Deep Dive", "advanced": "Mastery"}[level]
        title = f"{skill_name} — {level_label}"

        RoadmapWeek.objects.create(
            user      = user,
            week      = i,
            title     = title,
            skill     = skill_name,
            level     = level,
            trending  = trending,
            task      = task,
            resources = resources,
            status    = "not_started",
        )
        weeks_created += 1

    return weeks_created
