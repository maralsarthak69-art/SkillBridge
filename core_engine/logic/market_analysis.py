"""
market_analysis.py — Staleness Index Engine (powered by NeonDB)

Staleness Index (0–100):
    SI = semantic_drift * 50    [growth_rate proxy — declining = drifting]
       + recency_decay * 30     [time penalty since skill peaked]
       + demand_penalty * 20    [low demand + negative growth]

Score of 0 = perfectly fresh. Score of 100 = completely stale.
"""

from .neon_client import get_market_data, initialize_neon

CURRENT_YEAR = 2025
_initialized = False


def _ensure_init():
    global _initialized
    if not _initialized:
        initialize_neon()
        _initialized = True


# ── Recency Decay ─────────────────────────────────────────────────────────────

def _recency_decay(peak_year: int, years_experience) -> float:
    peak_age     = max(0, CURRENT_YEAR - peak_year)
    peak_penalty = min(1.0, peak_age / 8)
    exp_penalty  = min(0.3, (years_experience - 1) * 0.05) if years_experience else 0.0
    return min(1.0, peak_penalty + exp_penalty)


# ── Core Staleness Calculator ─────────────────────────────────────────────────

def calculate_staleness_index(skill_name: str, years_experience=None) -> dict:
    """
    Calculate the Staleness Index for a single skill using NeonDB market data.
    Falls back to heuristic scoring when skill is not in the market database.
    Returns dict with staleness_index (0–100), freshness_score, breakdown.
    """
    _ensure_init()
    data = get_market_data(skill_name)

    if not data:
        # ── Heuristic fallback for unknown skills ─────────────────────────
        # Use years_experience as a proxy for recency:
        #   - No years info → neutral (50)
        #   - Recent (≤2 yrs) → fresher
        #   - Old (>5 yrs) → more stale
        # Also apply a mild penalty for skills not tracked in market DB
        # (they tend to be niche/legacy)
        if years_experience is None:
            staleness_index = 45  # slightly below neutral — unknown = mild risk
        elif years_experience <= 1:
            staleness_index = 25  # very recent use → fresh
        elif years_experience <= 2:
            staleness_index = 35
        elif years_experience <= 4:
            staleness_index = 50
        elif years_experience <= 7:
            staleness_index = 62
        else:
            staleness_index = 72  # 8+ years on an unknown skill → likely legacy

        return {
            "skill":           skill_name,
            "staleness_index": staleness_index,
            "freshness_score": 100 - staleness_index,
            "demand_score":    50,
            "growth_rate":     0.0,
            "semantic_match":  False,
            "breakdown": {
                "semantic_drift":  0.45,
                "recency_penalty": round(min(1.0, (years_experience or 3) / 10), 3),
                "demand_penalty":  0.3,
            },
        }

    demand_score = data["demand_score"]
    growth_rate  = float(data["growth_rate"])
    peak_year    = data["peak_year"]

    # Component 1: Semantic drift — declining growth = drifting from market
    semantic_drift = max(0.0, min(1.0, 0.5 - growth_rate * 0.1))

    # Component 2: Recency decay
    recency_penalty = _recency_decay(peak_year, years_experience)

    # Component 3: Demand penalty
    demand_penalty = min(1.0,
        (1 - demand_score / 100) * 0.7 + (max(0, -growth_rate) / 3) * 0.3
    )

    raw_staleness   = semantic_drift * 50 + recency_penalty * 30 + demand_penalty * 20
    staleness_index = round(min(100, max(0, raw_staleness)))

    return {
        "skill":           data["skill"],
        "staleness_index": staleness_index,
        "freshness_score": 100 - staleness_index,
        "demand_score":    demand_score,
        "growth_rate":     growth_rate,
        "semantic_match":  True,
        "breakdown": {
            "semantic_drift":  round(semantic_drift, 3),
            "recency_penalty": round(recency_penalty, 3),
            "demand_penalty":  round(demand_penalty, 3),
        },
    }


def analyze_skill_vector_decay(skills: list) -> dict:
    """
    Analyze a list of skills from a parsed CV.
    skills: [{"skill": "Python", "years": 5}, ...]
    """
    _ensure_init()
    results = []
    for entry in skills:
        name  = entry.get("skill", "")
        years = entry.get("years")
        if name:
            results.append(calculate_staleness_index(name, years))

    if not results:
        return {
            "overall_staleness": 0,
            "overall_freshness": 100,
            "skills":            [],
            "stale_skills":      [],
            "fresh_skills":      [],
        }

    avg_staleness = round(sum(r["staleness_index"] for r in results) / len(results))

    return {
        "overall_staleness": avg_staleness,
        "overall_freshness": 100 - avg_staleness,
        "skills":            results,
        "stale_skills":      [r for r in results if r["staleness_index"] > 60],
        "fresh_skills":      [r for r in results if r["staleness_index"] < 30],
    }
