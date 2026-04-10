"""
alignment_engine.py — Agnostic Target Alignment Engine (Phase 2)

Industry-agnostic design philosophy:
    Skills are extracted at THREE layers:
        1. EXPLICIT    — tools, technologies, certifications (e.g. Python, AWS, PMP)
        2. FUNCTIONAL  — what the person actually does (e.g. "coordinate cross-functional teams")
        3. HIDDEN      — underlying cognitive/behavioral talents that transfer across
                         industries (e.g. "decision-making under pressure", "systems thinking")

    Layer 3 is the bridge that lets a nurse's triage skills map to a PM's
    stakeholder management, or a teacher's curriculum design map to a
    product manager's roadmap planning.

Semantic similarity (without vector DB):
    We use a keyword-expansion approach — each hidden talent has a set of
    synonyms/indicators. We check if the user's skill descriptions contain
    any of these indicators, giving a similarity score 0–1.
"""

import json
import re
from groq import Groq
from django.conf import settings
from .neon_client import get_market_data, get_canonical_skill, initialize_neon

_initialized = False


def _ensure_init():
    global _initialized
    if not _initialized:
        initialize_neon()
        _initialized = True


# ── Hidden Talent Taxonomy ────────────────────────────────────────────────────
# Maps hidden talent names to their surface-level indicators across industries.
# This is what makes the engine industry-agnostic.

HIDDEN_TALENT_MAP = {
    "decision_making": [
        "decision", "prioritize", "triage", "judgment", "assess", "evaluate",
        "choose", "determine", "resolve", "diagnose", "allocate", "trade-off",
    ],
    "systems_thinking": [
        "architecture", "design", "system", "pipeline", "workflow", "process",
        "infrastructure", "framework", "structure", "model", "schema", "pattern",
    ],
    "crisis_management": [
        "incident", "emergency", "on-call", "outage", "triage", "escalate",
        "pressure", "deadline", "critical", "urgent", "recovery", "mitigation",
    ],
    "stakeholder_communication": [
        "communicate", "present", "report", "brief", "coordinate", "align",
        "collaborate", "negotiate", "facilitate", "document", "explain", "translate",
    ],
    "analytical_thinking": [
        "analyze", "data", "metric", "measure", "insight", "pattern", "trend",
        "research", "investigate", "diagnose", "interpret", "evaluate", "audit",
    ],
    "leadership": [
        "lead", "manage", "mentor", "coach", "guide", "supervise", "direct",
        "team", "delegate", "motivate", "hire", "grow", "develop", "ownership",
    ],
    "project_management": [
        "plan", "schedule", "milestone", "deadline", "deliver", "scope",
        "budget", "resource", "roadmap", "sprint", "agile", "kanban", "track",
    ],
    "adaptability": [
        "adapt", "pivot", "change", "learn", "new", "evolve", "flexible",
        "iterate", "experiment", "prototype", "explore", "shift",
    ],
    "problem_solving": [
        "solve", "debug", "fix", "troubleshoot", "optimize", "improve",
        "refactor", "root cause", "workaround", "solution", "resolve",
    ],
    "attention_to_detail": [
        "review", "audit", "test", "validate", "verify", "quality", "accuracy",
        "precision", "compliance", "standard", "check", "monitor",
    ],
}


# ── Prompt Engineering ────────────────────────────────────────────────────────

PARSE_JD_SYSTEM_PROMPT = """
You are an expert talent analyst. Your job is to extract ALL skills and competencies
from a Job Description at THREE levels:

LEVEL 1 — EXPLICIT SKILLS: Specific tools, technologies, languages, certifications.
LEVEL 2 — FUNCTIONAL SKILLS: What the person actually does day-to-day (verbs + domain).
LEVEL 3 — HIDDEN TALENTS: Underlying cognitive and behavioral competencies that
           transfer across industries. These are NOT job-specific. Examples:
           - "decision-making under pressure" (a nurse triaging = a PM prioritizing)
           - "systems thinking" (an architect designing = an engineer architecting)
           - "stakeholder communication" (a teacher explaining = a PM presenting)
           - "analytical thinking", "leadership", "crisis management", "adaptability"

CRITICAL RULES:
- Strip ALL industry jargon. Translate domain-specific language to universal competencies.
- A "charge nurse" → "team lead under pressure". A "lesson plan" → "structured curriculum design".
- For LEVEL 3, always ask: "What underlying human capability does this require?"
- Assign priority: "must_have" | "preferred" | "bonus"

Return ONLY a valid JSON object with exactly these keys:
{
  "role_title": string,
  "explicit_skills": [{"skill": string, "priority": string, "years_required": number or null}],
  "functional_skills": [{"skill": string, "priority": string, "description": string}],
  "hidden_talents": [{"talent": string, "priority": string, "evidence": string, "universal_name": string}],
  "industry_context": string (one sentence — what industry/domain this JD is from)
}

Return ONLY the JSON object. No markdown, no explanation.
"""


def parse_target_jd(jd_text: str) -> dict:
    """
    Parse a Job Description into a 3-layer skill structure using Llama-3.

    Returns:
        {
            role_title:       str,
            explicit_skills:  [{skill, priority, years_required}],
            functional_skills:[{skill, priority, description}],
            hidden_talents:   [{talent, priority, evidence, universal_name}],
            industry_context: str,
        }
    """
    client = Groq(api_key=settings.GROQ_API_KEY)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": PARSE_JD_SYSTEM_PROMPT},
            {"role": "user",   "content": f"Parse this Job Description:\n\n{jd_text}"},
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
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Fallback extraction
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JD response.\nRaw:\n{raw[:400]}")


# ── Semantic Similarity (Industry-Agnostic) ───────────────────────────────────

def _compute_hidden_talent_score(user_skill_text: str, talent_key: str) -> float:
    """
    Score how much a user's skill description matches a hidden talent.
    Uses keyword expansion — no vector DB needed.
    Returns 0.0–1.0.
    """
    indicators = HIDDEN_TALENT_MAP.get(talent_key, [])
    if not indicators:
        return 0.0

    text_lower = user_skill_text.lower()
    matches    = sum(1 for kw in indicators if kw in text_lower)
    return round(min(1.0, matches / max(3, len(indicators) * 0.4)), 3)


def _build_user_skill_corpus(user_skill_map: dict) -> str:
    """
    Flatten a user's skill map (from ParsedCV) into a single searchable text corpus.
    Includes skill names, roles, and any descriptions.
    """
    parts = []

    # Technical skills
    for s in user_skill_map.get("technical_skills", []):
        skill = s.get("skill", "")
        years = s.get("years")
        parts.append(f"{skill} {years or ''} years experience")

    # Soft skills
    for s in user_skill_map.get("soft_skills", []):
        parts.append(str(s))

    # Roles held
    for r in user_skill_map.get("roles", []):
        title    = r.get("title", "")
        company  = r.get("company", "")
        duration = r.get("duration", "")
        parts.append(f"{title} at {company} {duration}")

    return " ".join(parts).lower()


# ── Talent Overlap Calculator ─────────────────────────────────────────────────

def calculate_talent_overlap(user_skill_map: dict, parsed_jd: dict) -> dict:
    """
    Compare user's SkillMap against parsed JD requirements.
    Industry-agnostic: matches explicit skills AND hidden talents.

    Args:
        user_skill_map: dict from ParsedCV.extracted_skills
        parsed_jd:      dict from parse_target_jd()

    Returns:
        {
            explicit_overlap:  [{skill, user_has, match_type, demand_score}],
            functional_overlap:[{skill, user_has, similarity}],
            hidden_overlap:    [{talent, user_score, threshold_met, universal_name}],
            overall_overlap_pct: int (0–100),
        }
    """
    _ensure_init()
    corpus = _build_user_skill_corpus(user_skill_map)

    user_skills_lower = {
        s.get("skill", "").lower()
        for s in user_skill_map.get("technical_skills", [])
    }
    user_soft_lower = {
        str(s).lower()
        for s in user_skill_map.get("soft_skills", [])
    }
    all_user_text = user_skills_lower | user_soft_lower

    # ── Explicit Skills Overlap ───────────────────────────────────────────────
    explicit_overlap = []
    for item in parsed_jd.get("explicit_skills", []):
        skill_name  = item.get("skill", "")
        skill_lower = skill_name.lower()

        # Resolve alias via NeonDB
        canonical_result = get_canonical_skill(skill_lower)
        canonical        = canonical_result["canonical"].lower() if canonical_result else skill_lower

        # Check match
        exact_match    = skill_lower in all_user_text or canonical in all_user_text
        partial_match  = any(skill_lower in u or u in skill_lower for u in all_user_text)
        user_has       = exact_match or partial_match
        match_type     = "exact" if exact_match else ("partial" if partial_match else "none")

        # Get market demand from NeonDB
        market = get_market_data(skill_name)
        demand = market["demand_score"] if market else 50

        explicit_overlap.append({
            "skill":        skill_name,
            "priority":     item.get("priority", "preferred"),
            "user_has":     user_has,
            "match_type":   match_type,
            "demand_score": demand,
        })

    # ── Functional Skills Overlap ─────────────────────────────────────────────
    functional_overlap = []
    for item in parsed_jd.get("functional_skills", []):
        skill_name  = item.get("skill", "")
        description = item.get("description", "")
        combined    = f"{skill_name} {description}".lower()

        # Keyword overlap with user corpus
        jd_words   = set(re.findall(r'\b\w{4,}\b', combined))
        user_words = set(re.findall(r'\b\w{4,}\b', corpus))
        overlap    = jd_words & user_words
        similarity = round(len(overlap) / max(len(jd_words), 1) * 1.5, 2)
        similarity = min(1.0, similarity)

        functional_overlap.append({
            "skill":      skill_name,
            "priority":   item.get("priority", "preferred"),
            "user_has":   similarity >= 0.3,
            "similarity": similarity,
        })

    # ── Hidden Talent Overlap ─────────────────────────────────────────────────
    hidden_overlap = []
    for item in parsed_jd.get("hidden_talents", []):
        talent_name    = item.get("talent", "")
        universal_name = item.get("universal_name", talent_name)

        # Map universal_name to our taxonomy key
        talent_key = universal_name.lower().replace(" ", "_").replace("-", "_")
        # Try to find closest key
        if talent_key not in HIDDEN_TALENT_MAP:
            talent_key = next(
                (k for k in HIDDEN_TALENT_MAP if k in talent_key or talent_key in k),
                None
            )

        score = _compute_hidden_talent_score(corpus, talent_key) if talent_key else 0.0

        hidden_overlap.append({
            "talent":         talent_name,
            "universal_name": universal_name,
            "priority":       item.get("priority", "preferred"),
            "user_score":     score,
            "threshold_met":  score >= 0.3,
            "evidence":       item.get("evidence", ""),
        })

    # ── Overall Overlap % ─────────────────────────────────────────────────────
    total_items  = len(explicit_overlap) + len(functional_overlap) + len(hidden_overlap)
    matched      = (
        sum(1 for e in explicit_overlap    if e["user_has"]) +
        sum(1 for f in functional_overlap  if f["user_has"]) +
        sum(1 for h in hidden_overlap      if h["threshold_met"])
    )
    overlap_pct = round(matched / total_items * 100) if total_items > 0 else 0

    return {
        "explicit_overlap":   explicit_overlap,
        "functional_overlap": functional_overlap,
        "hidden_overlap":     hidden_overlap,
        "overall_overlap_pct": overlap_pct,
        "matched_count":      matched,
        "total_count":        total_items,
    }


# ── Precise Gap Identifier ────────────────────────────────────────────────────

def identify_precise_gaps(user_skill_map: dict, parsed_jd: dict) -> dict:
    """
    Output a final JSON list of missing skills — explicit, functional, and hidden.
    Industry-agnostic: gaps are expressed as universal competencies.

    Returns:
        {
            gaps: [
                {
                    gap_type:       "explicit" | "functional" | "hidden",
                    skill:          str,
                    universal_name: str,
                    priority:       "must_have" | "preferred" | "bonus",
                    gap_severity:   "critical" | "moderate" | "minor",
                    demand_score:   int,
                    bridge_hint:    str  (how existing skills might partially cover this)
                }
            ],
            gap_score:        int (0–100, higher = bigger gap),
            critical_gaps:    int,
            transferable_strengths: [str]  (hidden talents user already has)
        }
    """
    overlap = calculate_talent_overlap(user_skill_map, parsed_jd)
    gaps    = []

    # Explicit gaps
    for item in overlap["explicit_overlap"]:
        if not item["user_has"]:
            market   = get_market_data(item["skill"]) or {}
            demand   = market.get("demand_score", 50)
            growth   = market.get("growth_rate", 0.0)
            severity = "critical" if item["priority"] == "must_have" else \
                       "moderate" if item["priority"] == "preferred" else "minor"

            gaps.append({
                "gap_type":       "explicit",
                "skill":          item["skill"],
                "universal_name": item["skill"],
                "priority":       item["priority"],
                "gap_severity":   severity,
                "demand_score":   demand,
                "growth_rate":    growth,
                "bridge_hint":    _find_bridge_hint(item["skill"], user_skill_map),
            })

    # Functional gaps
    for item in overlap["functional_overlap"]:
        if not item["user_has"]:
            severity = "critical" if item["priority"] == "must_have" else \
                       "moderate" if item["priority"] == "preferred" else "minor"
            gaps.append({
                "gap_type":       "functional",
                "skill":          item["skill"],
                "universal_name": item["skill"],
                "priority":       item["priority"],
                "gap_severity":   severity,
                "demand_score":   60,
                "growth_rate":    0.0,
                "bridge_hint":    "",
            })

    # Hidden talent gaps
    for item in overlap["hidden_overlap"]:
        if not item["threshold_met"]:
            severity = "critical" if item["priority"] == "must_have" else \
                       "moderate" if item["priority"] == "preferred" else "minor"
            gaps.append({
                "gap_type":       "hidden",
                "skill":          item["talent"],
                "universal_name": item["universal_name"],
                "priority":       item["priority"],
                "gap_severity":   severity,
                "demand_score":   70,
                "growth_rate":    0.0,
                "bridge_hint":    f"Develop through: {item['evidence']}",
            })

    # Sort: critical first, then by demand_score desc
    severity_order = {"critical": 0, "moderate": 1, "minor": 2}
    gaps.sort(key=lambda x: (severity_order[x["gap_severity"]], -x["demand_score"]))

    # Transferable strengths — hidden talents the user DOES have
    strengths = [
        h["universal_name"]
        for h in overlap["hidden_overlap"]
        if h["threshold_met"]
    ]

    total          = overlap["total_count"]
    gap_score      = round((len(gaps) / total * 100)) if total > 0 else 0
    critical_count = sum(1 for g in gaps if g["gap_severity"] == "critical")

    return {
        "gaps":                   gaps,
        "gap_score":              gap_score,
        "critical_gaps":          critical_count,
        "overall_overlap_pct":    overlap["overall_overlap_pct"],
        "transferable_strengths": strengths,
        "total_jd_requirements":  total,
    }


def _find_bridge_hint(missing_skill: str, user_skill_map: dict) -> str:
    """
    Find if any existing user skill could partially bridge a gap.
    Returns a hint string or empty string.
    """
    skill_lower = missing_skill.lower()
    user_skills = [s.get("skill", "") for s in user_skill_map.get("technical_skills", [])]

    # Simple domain proximity check
    BRIDGES = {
        "fastapi":      ["django", "flask", "python"],
        "kubernetes":   ["docker", "devops", "aws"],
        "typescript":   ["javascript", "react"],
        "pytorch":      ["tensorflow", "machine learning", "python"],
        "terraform":    ["aws", "azure", "devops", "docker"],
        "next.js":      ["react", "javascript", "node.js"],
        "graphql":      ["rest api", "django", "fastapi"],
        "go":           ["python", "java", "microservices"],
        "rust":         ["c++", "systems", "go"],
    }

    related = BRIDGES.get(skill_lower, [])
    matched = [s for s in user_skills if s.lower() in related]

    if matched:
        return f"Your {', '.join(matched)} experience provides a foundation."
    return ""


# ── Main Entry Point ──────────────────────────────────────────────────────────

def analyze_jd_alignment(jd_text: str, user_skill_map: dict) -> dict:
    """
    Full pipeline: JD text + user SkillMap → precise gap analysis.
    Industry-agnostic.
    """
    parsed_jd  = parse_target_jd(jd_text)
    gap_report = identify_precise_gaps(user_skill_map, parsed_jd)

    gap_report["role_title"]       = parsed_jd.get("role_title", "")
    gap_report["industry_context"] = parsed_jd.get("industry_context", "")

    return gap_report
