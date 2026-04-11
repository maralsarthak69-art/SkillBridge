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
    # (skill, demand_score, growth_rate, peak_year)
    # ── Languages ────────────────────────────────────────────────────────────
    ("Python",           96, +0.8, 2024),
    ("JavaScript",       90, +0.3, 2023),
    ("TypeScript",       92, +0.9, 2024),
    ("Go",               82, +0.9, 2024),
    ("Rust",             74, +1.2, 2024),
    ("Java",             68, -0.3, 2018),
    ("C++",              65, -0.2, 2019),
    ("C#",               70, +0.1, 2022),
    ("PHP",              52, -0.5, 2017),
    ("Ruby",             48, -0.6, 2016),
    ("Swift",            72, +0.3, 2023),
    ("Kotlin",           74, +0.4, 2023),
    ("Scala",            55, -0.3, 2019),
    ("R",                60, +0.1, 2022),
    ("MATLAB",           45, -0.4, 2018),
    ("Bash",             70, +0.1, 2022),
    ("Shell Scripting",  68, +0.1, 2022),
    ("Dart",             65, +0.5, 2023),
    # ── Frontend Frameworks ───────────────────────────────────────────────────
    ("React",            88, +0.4, 2023),
    ("Next.js",          86, +1.1, 2025),
    ("Vue.js",           63, -0.2, 2020),
    ("Angular",          58, -0.6, 2019),
    ("Svelte",           68, +0.7, 2024),
    ("Nuxt.js",          62, +0.3, 2023),
    ("Remix",            65, +0.6, 2024),
    ("Tailwind CSS",     85, +1.0, 2024),
    ("Bootstrap",        55, -0.4, 2019),
    ("Material UI",      70, +0.2, 2022),
    ("Shadcn UI",        78, +1.5, 2025),
    # ── Backend Frameworks ────────────────────────────────────────────────────
    ("FastAPI",          87, +1.3, 2024),
    ("Django",           78, +0.1, 2021),
    ("Flask",            72, -0.1, 2021),
    ("Express.js",       78, +0.1, 2022),
    ("NestJS",           76, +0.6, 2023),
    ("Spring Boot",      70, -0.1, 2021),
    ("Laravel",          58, -0.3, 2019),
    ("Rails",            48, -0.6, 2016),
    ("Gin",              72, +0.5, 2023),
    ("Fiber",            68, +0.6, 2023),
    # ── Databases ─────────────────────────────────────────────────────────────
    ("PostgreSQL",       82, +0.2, 2022),
    ("MySQL",            70, -0.1, 2020),
    ("MongoDB",          70, -0.2, 2020),
    ("Redis",            78, +0.3, 2022),
    ("SQLite",           60, +0.0, 2021),
    ("Elasticsearch",    72, +0.2, 2022),
    ("Cassandra",        58, -0.2, 2019),
    ("DynamoDB",         74, +0.3, 2023),
    ("Supabase",         80, +1.2, 2024),
    ("Neon",             75, +1.4, 2025),
    ("PlanetScale",      68, +0.5, 2023),
    ("Pinecone",         82, +1.8, 2025),
    ("Weaviate",         78, +1.6, 2025),
    ("ChromaDB",         76, +1.7, 2025),
    ("SQL",              79, +0.1, 2022),
    # ── Cloud & DevOps ────────────────────────────────────────────────────────
    ("AWS",              93, +0.6, 2024),
    ("Azure",            84, +0.5, 2023),
    ("GCP",              78, +0.4, 2023),
    ("Docker",           91, +0.5, 2023),
    ("Kubernetes",       85, +0.7, 2024),
    ("Terraform",        83, +0.8, 2024),
    ("Ansible",          72, +0.2, 2022),
    ("Jenkins",          62, -0.3, 2019),
    ("GitHub Actions",   84, +0.9, 2024),
    ("GitLab CI",        74, +0.4, 2023),
    ("CircleCI",         62, -0.1, 2021),
    ("CI/CD",            85, +0.4, 2023),
    ("Nginx",            74, +0.1, 2022),
    ("Linux",            80, +0.2, 2022),
    ("Prometheus",       76, +0.5, 2023),
    ("Grafana",          78, +0.6, 2023),
    ("Datadog",          76, +0.5, 2023),
    ("Pulumi",           72, +0.7, 2024),
    ("Helm",             78, +0.5, 2023),
    ("Microservices",    81, +0.3, 2023),
    ("Serverless",       78, +0.4, 2023),
    # ── AI / ML ───────────────────────────────────────────────────────────────
    ("Machine Learning", 88, +0.5, 2024),
    ("Deep Learning",    85, +0.4, 2024),
    ("TensorFlow",       68, -0.4, 2020),
    ("PyTorch",          87, +0.6, 2024),
    ("Scikit-learn",     80, +0.3, 2023),
    ("Pandas",           82, +0.3, 2023),
    ("NumPy",            80, +0.2, 2022),
    ("LangChain",        96, +2.5, 2025),
    ("LLM",              95, +2.8, 2025),
    ("Groq",             88, +2.0, 2025),
    ("RAG",              91, +2.2, 2025),
    ("Vector Database",  85, +1.8, 2025),
    ("OpenAI API",       92, +2.0, 2025),
    ("Hugging Face",     88, +1.5, 2024),
    ("Stable Diffusion", 72, +0.8, 2024),
    ("Computer Vision",  80, +0.6, 2024),
    ("NLP",              84, +0.7, 2024),
    ("MLOps",            82, +1.0, 2024),
    ("Data Science",     84, +0.4, 2023),
    ("Data Engineering", 86, +0.7, 2024),
    ("Apache Spark",     72, +0.1, 2022),
    ("Airflow",          74, +0.3, 2023),
    ("dbt",              76, +0.8, 2024),
    # ── Mobile ────────────────────────────────────────────────────────────────
    ("React Native",     74, +0.2, 2023),
    ("Flutter",          76, +0.5, 2023),
    ("iOS Development",  68, +0.1, 2022),
    ("Android Development", 66, +0.0, 2021),
    # ── Tools & Practices ─────────────────────────────────────────────────────
    ("Git",              88, +0.2, 2023),
    ("GraphQL",          66, -0.1, 2021),
    ("REST API",         84, +0.2, 2023),
    ("gRPC",             74, +0.5, 2023),
    ("WebSockets",       72, +0.3, 2023),
    ("OAuth",            76, +0.2, 2022),
    ("JWT",              78, +0.2, 2023),
    ("Agile",            78, +0.1, 2022),
    ("Scrum",            72, +0.0, 2021),
    ("System Design",    84, +0.4, 2023),
    ("Microservices Architecture", 80, +0.3, 2023),
    ("Node.js",          82, +0.2, 2022),
    ("Webpack",          62, -0.3, 2020),
    ("Vite",             80, +0.9, 2024),
    ("Testing",          78, +0.2, 2022),
    ("Jest",             78, +0.2, 2022),
    ("Pytest",           80, +0.3, 2023),
    ("Cypress",          74, +0.3, 2023),
    ("Playwright",       78, +0.7, 2024),
    ("Figma",            80, +0.5, 2023),
    ("Storybook",        68, +0.2, 2022),
    ("Prisma",           78, +0.8, 2024),
    ("tRPC",             72, +0.9, 2024),
    ("Drizzle ORM",      70, +1.0, 2025),
    ("Celery",           68, +0.1, 2021),
    ("RabbitMQ",         66, +0.0, 2021),
    ("Kafka",            78, +0.4, 2023),
    ("WebAssembly",      68, +0.6, 2024),
    ("Blockchain",       52, -0.3, 2021),
    ("Solidity",         48, -0.4, 2021),
    ("Cybersecurity",    82, +0.5, 2023),
    ("Networking",       70, +0.1, 2022),
]

SKILL_MAP_SEED = [
    # (alias, canonical, category)
    ("python3",                  "Python",           "language"),
    ("py",                       "Python",           "language"),
    ("js",                       "JavaScript",       "language"),
    ("javascript",               "JavaScript",       "language"),
    ("ts",                       "TypeScript",       "language"),
    ("typescript",               "TypeScript",       "language"),
    ("reactjs",                  "React",            "framework"),
    ("react.js",                 "React",            "framework"),
    ("nextjs",                   "Next.js",          "framework"),
    ("next",                     "Next.js",          "framework"),
    ("nodejs",                   "Node.js",          "framework"),
    ("node",                     "Node.js",          "framework"),
    ("vuejs",                    "Vue.js",           "framework"),
    ("vue",                      "Vue.js",           "framework"),
    ("k8s",                      "Kubernetes",       "tool"),
    ("kube",                     "Kubernetes",       "tool"),
    ("postgres",                 "PostgreSQL",       "database"),
    ("psql",                     "PostgreSQL",       "database"),
    ("mongo",                    "MongoDB",          "database"),
    ("ml",                       "Machine Learning", "ai_ml"),
    ("deep learning",            "Machine Learning", "ai_ml"),
    ("llms",                     "LLM",              "ai_ml"),
    ("large language model",     "LLM",              "ai_ml"),
    ("amazon web services",      "AWS",              "cloud"),
    ("google cloud",             "GCP",              "cloud"),
    ("google cloud platform",    "GCP",              "cloud"),
    ("microsoft azure",          "Azure",            "cloud"),
    ("ci cd",                    "CI/CD",            "methodology"),
    ("continuous integration",   "CI/CD",            "methodology"),
    ("continuous deployment",    "CI/CD",            "methodology"),
    ("microservice",             "Microservices",    "methodology"),
    ("iac",                      "Terraform",        "tool"),
    ("infrastructure as code",   "Terraform",        "tool"),
    ("expressjs",                "Express.js",       "framework"),
    ("express",                  "Express.js",       "framework"),
    ("nestjs",                   "NestJS",           "framework"),
    ("nest",                     "NestJS",           "framework"),
    ("springboot",               "Spring Boot",      "framework"),
    ("spring",                   "Spring Boot",      "framework"),
    ("tailwind",                 "Tailwind CSS",     "framework"),
    ("tailwindcss",              "Tailwind CSS",     "framework"),
    ("sklearn",                  "Scikit-learn",     "ai_ml"),
    ("scikit learn",             "Scikit-learn",     "ai_ml"),
    ("pytorch",                  "PyTorch",          "ai_ml"),
    ("tensorflow",               "TensorFlow",       "ai_ml"),
    ("tf",                       "TensorFlow",       "ai_ml"),
    ("hf",                       "Hugging Face",     "ai_ml"),
    ("huggingface",              "Hugging Face",     "ai_ml"),
    ("openai",                   "OpenAI API",       "ai_ml"),
    ("chatgpt api",              "OpenAI API",       "ai_ml"),
    ("langchain",                "LangChain",        "ai_ml"),
    ("rag",                      "RAG",              "ai_ml"),
    ("vector db",                "Vector Database",  "ai_ml"),
    ("vectordb",                 "Vector Database",  "ai_ml"),
    ("github actions",           "GitHub Actions",   "tool"),
    ("gh actions",               "GitHub Actions",   "tool"),
    ("gitlab ci",                "GitLab CI",        "tool"),
    ("rest",                     "REST API",         "methodology"),
    ("restful",                  "REST API",         "methodology"),
    ("rest apis",                "REST API",         "methodology"),
    ("api",                      "REST API",         "methodology"),
    ("react native",             "React Native",     "framework"),
    ("rn",                       "React Native",     "framework"),
    ("data science",             "Data Science",     "ai_ml"),
    ("data engineering",         "Data Engineering", "ai_ml"),
    ("mlops",                    "MLOps",            "ai_ml"),
    ("nlp",                      "NLP",              "ai_ml"),
    ("natural language processing", "NLP",           "ai_ml"),
    ("computer vision",          "Computer Vision",  "ai_ml"),
    ("cv",                       "Computer Vision",  "ai_ml"),
    ("system design",            "System Design",    "methodology"),
    ("distributed systems",      "System Design",    "methodology"),
    ("mysql",                    "MySQL",            "database"),
    ("sqlite",                   "SQLite",           "database"),
    ("redis cache",              "Redis",            "database"),
    ("elasticsearch",            "Elasticsearch",    "database"),
    ("elastic search",           "Elasticsearch",    "database"),
    ("kafka",                    "Kafka",            "tool"),
    ("apache kafka",             "Kafka",            "tool"),
    ("rabbitmq",                 "RabbitMQ",         "tool"),
    ("celery",                   "Celery",           "tool"),
    ("pytest",                   "Pytest",           "tool"),
    ("jest",                     "Jest",             "tool"),
    ("cypress",                  "Cypress",          "tool"),
    ("playwright",               "Playwright",       "tool"),
    ("figma",                    "Figma",            "tool"),
    ("git",                      "Git",              "tool"),
    ("github",                   "Git",              "tool"),
    ("agile",                    "Agile",            "methodology"),
    ("scrum",                    "Scrum",            "methodology"),
    ("jwt",                      "JWT",              "methodology"),
    ("oauth",                    "OAuth",            "methodology"),
    ("oauth2",                   "OAuth",            "methodology"),
    ("graphql",                  "GraphQL",          "methodology"),
    ("grpc",                     "gRPC",             "methodology"),
    ("websocket",                "WebSockets",       "methodology"),
    ("websockets",               "WebSockets",       "methodology"),
    ("linux",                    "Linux",            "tool"),
    ("ubuntu",                   "Linux",            "tool"),
    ("bash",                     "Bash",             "language"),
    ("shell",                    "Shell Scripting",  "language"),
    ("shell script",             "Shell Scripting",  "language"),
    ("nginx",                    "Nginx",            "tool"),
    ("apache",                   "Nginx",            "tool"),
    ("prometheus",               "Prometheus",       "tool"),
    ("grafana",                  "Grafana",          "tool"),
    ("datadog",                  "Datadog",          "tool"),
    ("helm",                     "Helm",             "tool"),
    ("ansible",                  "Ansible",          "tool"),
    ("jenkins",                  "Jenkins",          "tool"),
    ("circleci",                 "CircleCI",         "tool"),
    ("webpack",                  "Webpack",          "tool"),
    ("vite",                     "Vite",             "tool"),
    ("prisma",                   "Prisma",           "tool"),
    ("trpc",                     "tRPC",             "tool"),
    ("drizzle",                  "Drizzle ORM",      "tool"),
    ("storybook",                "Storybook",        "tool"),
    ("pandas",                   "Pandas",           "ai_ml"),
    ("numpy",                    "NumPy",            "ai_ml"),
    ("spark",                    "Apache Spark",     "tool"),
    ("apache spark",             "Apache Spark",     "tool"),
    ("airflow",                  "Airflow",          "tool"),
    ("apache airflow",           "Airflow",          "tool"),
    ("dbt",                      "dbt",              "tool"),
    ("flutter",                  "Flutter",          "framework"),
    ("dart",                     "Dart",             "language"),
    ("ios",                      "iOS Development",  "mobile"),
    ("android",                  "Android Development", "mobile"),
    ("swift",                    "Swift",            "language"),
    ("kotlin",                   "Kotlin",           "language"),
    ("c sharp",                  "C#",               "language"),
    ("dotnet",                   "C#",               "language"),
    (".net",                     "C#",               "language"),
    ("asp.net",                  "C#",               "language"),
    ("php",                      "PHP",              "language"),
    ("laravel",                  "Laravel",          "framework"),
    ("ruby",                     "Ruby",             "language"),
    ("rails",                    "Rails",            "framework"),
    ("ruby on rails",            "Rails",            "framework"),
    ("scala",                    "Scala",            "language"),
    ("r language",               "R",                "language"),
    ("matlab",                   "MATLAB",           "language"),
    ("solidity",                 "Solidity",         "language"),
    ("blockchain",               "Blockchain",       "methodology"),
    ("web3",                     "Blockchain",       "methodology"),
    ("cybersecurity",            "Cybersecurity",    "methodology"),
    ("security",                 "Cybersecurity",    "methodology"),
    ("networking",               "Networking",       "methodology"),
    ("tcp ip",                   "Networking",       "methodology"),
    ("supabase",                 "Supabase",         "database"),
    ("pinecone",                 "Pinecone",         "database"),
    ("weaviate",                 "Weaviate",         "database"),
    ("chromadb",                 "ChromaDB",         "database"),
    ("dynamodb",                 "DynamoDB",         "database"),
    ("cassandra",                "Cassandra",        "database"),
    ("shadcn",                   "Shadcn UI",        "framework"),
    ("material ui",              "Material UI",      "framework"),
    ("mui",                      "Material UI",      "framework"),
    ("bootstrap",                "Bootstrap",        "framework"),
    ("svelte",                   "Svelte",           "framework"),
    ("sveltekit",                "Svelte",           "framework"),
    ("nuxt",                     "Nuxt.js",          "framework"),
    ("remix",                    "Remix",            "framework"),
    ("fastapi",                  "FastAPI",          "framework"),
    ("flask",                    "Flask",            "framework"),
    ("gin",                      "Gin",              "framework"),
    ("fiber",                    "Fiber",            "framework"),
    ("wasm",                     "WebAssembly",      "language"),
    ("webassembly",              "WebAssembly",      "language"),
]


def seed_data():
    """Insert/update seed data. Uses ON CONFLICT DO UPDATE to refresh existing rows."""
    with get_neon_conn() as conn:
        with conn.cursor() as cur:
            # Market trends — upsert so new skills are added and existing ones updated
            cur.executemany(
                """
                INSERT INTO market_trends (skill, skill_lower, demand_score, growth_rate, peak_year)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (skill_lower) DO UPDATE SET
                    demand_score = EXCLUDED.demand_score,
                    growth_rate  = EXCLUDED.growth_rate,
                    peak_year    = EXCLUDED.peak_year,
                    updated_at   = NOW()
                """,
                [(s, s.lower(), d, g, p) for s, d, g, p in MARKET_SEED],
            )

            # Skill map aliases — upsert
            cur.executemany(
                """
                INSERT INTO skill_map (alias, canonical, category)
                VALUES (%s, %s, %s)
                ON CONFLICT (alias) DO UPDATE SET
                    canonical = EXCLUDED.canonical,
                    category  = EXCLUDED.category
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
