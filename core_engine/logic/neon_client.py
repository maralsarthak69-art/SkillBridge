"""
neon_client.py — NeonDB connection and schema manager

Tables:
    market_trends  — skill market data (demand, growth, peak year)
    skill_map      — canonical skill name aliases for alignment engine

Uses psycopg2 directly (already installed). NeonDB is PostgreSQL-compatible
so no extra dependencies needed.
"""

import psycopg2
import psycopg2.extras
from django.conf import settings

# ── Connection ────────────────────────────────────────────────────────────────

def get_neon_conn():
    """Return a new psycopg2 connection to NeonDB."""
    url = settings.NEON_DATABASE_URL
    if not url:
        raise RuntimeError("NEON_DATABASE_URL is not set in environment.")
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


# ── Schema Bootstrap ──────────────────────────────────────────────────────────

CREATE_MARKET_TRENDS = """
CREATE TABLE IF NOT EXISTS market_trends (
    id            SERIAL PRIMARY KEY,
    skill         VARCHAR(150) NOT NULL UNIQUE,
    skill_lower   VARCHAR(150) NOT NULL UNIQUE,
    demand_score  INTEGER      NOT NULL DEFAULT 50,
    growth_rate   FLOAT        NOT NULL DEFAULT 0.0,
    peak_year     INTEGER      NOT NULL DEFAULT 2023,
    updated_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);
"""

CREATE_SKILL_MAP = """
CREATE TABLE IF NOT EXISTS skill_map (
    id            SERIAL PRIMARY KEY,
    alias         VARCHAR(150) NOT NULL UNIQUE,
    canonical     VARCHAR(150) NOT NULL,
    category      VARCHAR(50)  NOT NULL DEFAULT 'tool'
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_market_trends_skill_lower ON market_trends(skill_lower);
CREATE INDEX IF NOT EXISTS idx_skill_map_alias           ON skill_map(alias);
"""

CREATE_SOFT_SKILL_SESSIONS = """
CREATE TABLE IF NOT EXISTS soft_skill_sessions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER      NOT NULL,
    request_type    VARCHAR(50)  NOT NULL DEFAULT 'soft_skills',
    original_text   TEXT         NOT NULL,
    corrected_text  TEXT         NOT NULL,
    corrections     JSONB        NOT NULL DEFAULT '[]',
    ai_feedback     TEXT         NOT NULL DEFAULT '',
    improvement_score INTEGER    NOT NULL DEFAULT 0,
    readability_level VARCHAR(20) NOT NULL DEFAULT 'mid',
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_soft_skill_sessions_user ON soft_skill_sessions(user_id);
"""


def bootstrap_schema():
    """Create tables if they don't exist. Safe to call multiple times."""
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_MARKET_TRENDS)
            cur.execute(CREATE_SKILL_MAP)
            cur.execute(CREATE_INDEXES)
            cur.execute(CREATE_SOFT_SKILL_SESSIONS)
        conn.commit()


# ── Seed Data ─────────────────────────────────────────────────────────────────

MARKET_SEED = [
    ("Python",           96, +0.8, 2024),
    ("JavaScript",       90, +0.3, 2023),
    ("TypeScript",       92, +0.9, 2024),
    ("React",            88, +0.4, 2023),
    ("Next.js",          86, +1.1, 2025),
    ("FastAPI",          87, +1.3, 2024),
    ("Django",           78, +0.1, 2021),
    ("Docker",           91, +0.5, 2023),
    ("Kubernetes",       85, +0.7, 2024),
    ("AWS",              93, +0.6, 2024),
    ("Azure",            84, +0.5, 2023),
    ("GCP",              78, +0.4, 2023),
    ("Terraform",        83, +0.8, 2024),
    ("LangChain",        96, +2.5, 2025),
    ("LLM",              95, +2.8, 2025),
    ("PostgreSQL",       82, +0.2, 2022),
    ("Redis",            78, +0.3, 2022),
    ("MongoDB",          70, -0.2, 2020),
    ("GraphQL",          66, -0.1, 2021),
    ("Go",               82, +0.9, 2024),
    ("Rust",             74, +1.2, 2024),
    ("Java",             68, -0.3, 2018),
    ("Angular",          58, -0.6, 2019),
    ("Vue.js",           63, -0.2, 2020),
    ("TensorFlow",       68, -0.4, 2020),
    ("PyTorch",          87, +0.6, 2024),
    ("Machine Learning", 88, +0.5, 2024),
    ("SQL",              79, +0.1, 2022),
    ("CI/CD",            85, +0.4, 2023),
    ("Microservices",    81, +0.3, 2023),
    ("Node.js",          82, +0.2, 2022),
    ("Groq",             88, +2.0, 2025),
    ("RAG",              91, +2.2, 2025),
    ("Vector Database",  85, +1.8, 2025),
]

SKILL_MAP_SEED = [
    # (alias, canonical, category)
    ("python3",          "Python",        "language"),
    ("py",               "Python",        "language"),
    ("js",               "JavaScript",    "language"),
    ("javascript",       "JavaScript",    "language"),
    ("ts",               "TypeScript",    "language"),
    ("typescript",       "TypeScript",    "language"),
    ("reactjs",          "React",         "framework"),
    ("react.js",         "React",         "framework"),
    ("nextjs",           "Next.js",       "framework"),
    ("next",             "Next.js",       "framework"),
    ("nodejs",           "Node.js",       "framework"),
    ("node",             "Node.js",       "framework"),
    ("vuejs",            "Vue.js",        "framework"),
    ("vue",              "Vue.js",        "framework"),
    ("k8s",              "Kubernetes",    "tool"),
    ("kube",             "Kubernetes",    "tool"),
    ("postgres",         "PostgreSQL",    "database"),
    ("psql",             "PostgreSQL",    "database"),
    ("mongo",            "MongoDB",       "database"),
    ("ml",               "Machine Learning", "ai_ml"),
    ("deep learning",    "Machine Learning", "ai_ml"),
    ("llms",             "LLM",           "ai_ml"),
    ("large language model", "LLM",       "ai_ml"),
    ("amazon web services",  "AWS",       "cloud"),
    ("google cloud",     "GCP",           "cloud"),
    ("microsoft azure",  "Azure",         "cloud"),
    ("ci cd",            "CI/CD",         "methodology"),
    ("continuous integration", "CI/CD",   "methodology"),
    ("microservice",     "Microservices", "methodology"),
    ("iac",              "Terraform",     "tool"),
    ("infrastructure as code", "Terraform", "tool"),
]


def seed_data():
    """Insert seed data if tables are empty. Safe to call multiple times."""
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            # Market trends
            cur.execute("SELECT COUNT(*) FROM market_trends")
            count = cur.fetchone()["count"]
            if count == 0:
                cur.executemany(
                    """
                    INSERT INTO market_trends (skill, skill_lower, demand_score, growth_rate, peak_year)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (skill_lower) DO NOTHING
                    """,
                    [(s, s.lower(), d, g, p) for s, d, g, p in MARKET_SEED],
                )

            # Skill map
            cur.execute("SELECT COUNT(*) FROM skill_map")
            count = cur.fetchone()["count"]
            if count == 0:
                cur.executemany(
                    """
                    INSERT INTO skill_map (alias, canonical, category)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (alias) DO NOTHING
                    """,
                    SKILL_MAP_SEED,
                )
        conn.commit()


# ── Query Helpers ─────────────────────────────────────────────────────────────

def get_market_data(skill_name: str) -> dict | None:
    """
    Look up market trend data for a skill.
    Tries exact match on skill_lower, then partial ILIKE match.
    """
    skill_lower = skill_name.lower().strip()
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            # Exact match
            cur.execute(
                "SELECT * FROM market_trends WHERE skill_lower = %s",
                (skill_lower,)
            )
            row = cur.fetchone()
            if row:
                return dict(row)

            # Partial match
            cur.execute(
                "SELECT * FROM market_trends WHERE skill_lower ILIKE %s OR %s ILIKE '%%' || skill_lower || '%%' LIMIT 1",
                (f"%{skill_lower}%", skill_lower)
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_canonical_skill(alias: str) -> dict | None:
    """
    Resolve a skill alias to its canonical name via skill_map table.
    """
    alias_lower = alias.lower().strip()
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT canonical, category FROM skill_map WHERE alias = %s",
                (alias_lower,)
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_all_market_skills() -> list:
    """Return all skills from market_trends table."""
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT skill, skill_lower, demand_score, growth_rate, peak_year FROM market_trends ORDER BY demand_score DESC")
            return [dict(r) for r in cur.fetchall()]


def initialize_neon():
    """Bootstrap schema + seed data. Call once on startup."""
    bootstrap_schema()
    seed_data()


# ── SoftSkillSession Helpers ──────────────────────────────────────────────────

def save_soft_skill_session(user_id: int, original_text: str, result: dict) -> int:
    """
    Save a soft skills grammar coaching session to NeonDB.
    Returns the new session id.
    """
    import json as _json
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO soft_skill_sessions
                    (user_id, request_type, original_text, corrected_text,
                     corrections, ai_feedback, improvement_score, readability_level)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    user_id,
                    "soft_skills",
                    original_text,
                    result.get("corrected_text", ""),
                    _json.dumps(result.get("changes", [])),
                    result.get("ai_feedback", ""),
                    result.get("improvement_score", 0),
                    result.get("readability_level", "mid"),
                ),
            )
            session_id = cur.fetchone()["id"]
        conn.commit()
    return session_id


def get_soft_skill_sessions(user_id: int) -> list:
    """Return all soft skill sessions for a user, newest first."""
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, request_type, original_text, corrected_text,
                       corrections, ai_feedback, improvement_score,
                       readability_level, created_at
                FROM soft_skill_sessions
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            return [dict(r) for r in cur.fetchall()]
