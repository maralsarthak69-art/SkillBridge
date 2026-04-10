from .chroma_client import query_market_relevance, seed_market_trends


# ── Freshness Score Calculator ────────────────────────────────────────────────

def calculate_freshness_score(skill_name: str, years_experience) -> tuple:
    """
    Combine market relevance + experience depth into a freshness score (0–100).
    Returns: (score: int, reason: str)
    """
    market = query_market_relevance(skill_name)
    relevance = market["relevance_score"]

    exp_bonus = 0
    if years_experience:
        if years_experience >= 5:
            exp_bonus = 10
        elif years_experience >= 3:
            exp_bonus = 7
        elif years_experience >= 1:
            exp_bonus = 4
        else:
            exp_bonus = 1

    final_score = min(100, relevance + exp_bonus)

    if final_score >= 85:
        status = "Very fresh"
    elif final_score >= 70:
        status = "Relevant"
    elif final_score >= 50:
        status = "Moderately relevant"
    else:
        status = "Stale or declining"

    reason = (
        f"{status}. Market relevance: {relevance}/100. "
        f"Experience: {years_experience or 'unknown'} years (+{exp_bonus} pts). "
        f"{market['description']}"
    )

    return final_score, reason


# ── Main Analyzer ─────────────────────────────────────────────────────────────

def analyze_skill_decay(parsed_cv) -> list:
    """
    Analyze all technical skills from a ParsedCV instance.
    Creates SkillSnapshot records and returns a list of results.
    """
    from core_engine.models import SkillSnapshot

    seed_market_trends()

    technical_skills = parsed_cv.extracted_skills.get("technical_skills", [])
    if not technical_skills:
        return []

    snapshots = []
    for skill_entry in technical_skills:
        skill_name = skill_entry.get("skill", "")
        years = skill_entry.get("years")

        if not skill_name:
            continue

        score, reason = calculate_freshness_score(skill_name, years)

        snapshot = SkillSnapshot.objects.create(
            user_profile=parsed_cv.user_profile,
            skill_name=skill_name,
            years_experience=years,
            freshness_score=score,
            decay_reason=reason,
        )
        snapshots.append(snapshot)

    return snapshots


# ── Overall Health Score ──────────────────────────────────────────────────────

def calculate_overall_health(snapshots: list) -> int:
    """Average freshness score across all skills. Returns 0 if no snapshots."""
    if not snapshots:
        return 0
    return round(sum(s.freshness_score for s in snapshots) / len(snapshots))
