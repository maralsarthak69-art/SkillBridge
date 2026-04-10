"""
skill_decay.py — Skill Decay Service

Bridges the NeonDB-powered logic layer (core_engine/logic/market_analysis.py)
with the Django ORM (SkillSnapshot model).

Full pipeline:
    ParsedCV → extract technical_skills
             → calculate_staleness_index() via NeonDB
             → save SkillSnapshot with staleness_index + freshness_score + breakdown
             → return snapshots for API response
"""

from core_engine.logic.market_analysis import calculate_staleness_index


def analyze_skill_decay(parsed_cv) -> list:
    """
    Analyze all technical skills from a ParsedCV instance using NeonDB staleness engine.
    Creates SkillSnapshot records and returns them.
    """
    from core_engine.models import SkillSnapshot

    technical_skills = parsed_cv.extracted_skills.get("technical_skills", [])
    if not technical_skills:
        return []

    snapshots = []
    for skill_entry in technical_skills:
        skill_name = skill_entry.get("skill", "")
        years      = skill_entry.get("years")
        if not skill_name:
            continue

        # Use NeonDB-powered staleness engine
        result = calculate_staleness_index(skill_name, years)

        staleness = result["staleness_index"]
        freshness = result["freshness_score"]
        demand    = result["demand_score"]
        growth    = result["growth_rate"]
        breakdown = result["breakdown"]

        # Build human-readable decay reason
        if staleness >= 70:
            status = "Stale"
        elif staleness >= 40:
            status = "Moderately relevant"
        elif staleness >= 20:
            status = "Relevant"
        else:
            status = "Very fresh"

        reason = (
            f"{status}. Staleness: {staleness}/100. "
            f"Market demand: {demand}/100. "
            f"Growth rate: {'+' if growth >= 0 else ''}{growth}. "
            f"Semantic drift: {breakdown['semantic_drift']}, "
            f"Recency penalty: {breakdown['recency_penalty']}, "
            f"Demand penalty: {breakdown['demand_penalty']}."
        )

        snapshot = SkillSnapshot.objects.create(
            user_profile     = parsed_cv.user_profile,
            skill_name       = skill_name,
            years_experience = years,
            freshness_score  = freshness,
            staleness_index  = staleness,
            demand_score     = demand,
            growth_rate      = growth,
            decay_reason     = reason,
        )
        snapshots.append(snapshot)

    return snapshots


def calculate_overall_health(snapshots: list) -> dict:
    """
    Compute aggregate health metrics across all skill snapshots.
    Returns a dict with overall scores and breakdowns.
    """
    if not snapshots:
        return {
            "overall_freshness":  100,
            "overall_staleness":  0,
            "fresh_count":        0,
            "relevant_count":     0,
            "stale_count":        0,
        }

    avg_staleness = round(sum(s.staleness_index for s in snapshots) / len(snapshots))
    avg_freshness = 100 - avg_staleness

    return {
        "overall_freshness": avg_freshness,
        "overall_staleness": avg_staleness,
        "fresh_count":       sum(1 for s in snapshots if s.staleness_index < 30),
        "relevant_count":    sum(1 for s in snapshots if 30 <= s.staleness_index < 60),
        "stale_count":       sum(1 for s in snapshots if s.staleness_index >= 60),
    }
