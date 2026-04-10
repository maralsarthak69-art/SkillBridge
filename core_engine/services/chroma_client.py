"""
Market trends lookup — uses a simple in-memory dict for fast, zero-dependency
skill relevance scoring. ChromaDB vector search is reserved for Phase 3+
when we have real job posting embeddings to work with.
"""

MARKET_TRENDS = {
    "python":        {"skill": "Python",        "relevance_score": 95, "description": "Highly in-demand for AI, backend, and data science. Very fresh in 2025."},
    "javascript":    {"skill": "JavaScript",    "relevance_score": 90, "description": "Core web language, always relevant. Frameworks evolve fast."},
    "typescript":    {"skill": "TypeScript",    "relevance_score": 92, "description": "Rapidly replacing plain JS in enterprise. Very high demand."},
    "react":         {"skill": "React",         "relevance_score": 88, "description": "Dominant frontend framework. Still top of job postings."},
    "django":        {"skill": "Django",        "relevance_score": 80, "description": "Solid Python web framework. Steady demand, not declining."},
    "fastapi":       {"skill": "FastAPI",       "relevance_score": 87, "description": "Rising fast as preferred Python API framework over Django REST."},
    "docker":        {"skill": "Docker",        "relevance_score": 91, "description": "Essential DevOps skill. Universal in modern stacks."},
    "kubernetes":    {"skill": "Kubernetes",    "relevance_score": 85, "description": "High demand in cloud-native roles. Complex but valued."},
    "postgresql":    {"skill": "PostgreSQL",    "relevance_score": 83, "description": "Most popular open-source relational DB. Very stable demand."},
    "mongodb":       {"skill": "MongoDB",       "relevance_score": 72, "description": "Popular NoSQL option. Demand steady but not growing fast."},
    "redis":         {"skill": "Redis",         "relevance_score": 78, "description": "Widely used for caching and queues. Solid demand."},
    "aws":           {"skill": "AWS",           "relevance_score": 93, "description": "Market-leading cloud platform. Certifications highly valued."},
    "azure":         {"skill": "Azure",         "relevance_score": 85, "description": "Strong enterprise cloud demand, especially in Microsoft shops."},
    "langchain":     {"skill": "LangChain",     "relevance_score": 96, "description": "Cutting-edge LLM orchestration. Extremely hot in 2025."},
    "machine learning": {"skill": "Machine Learning", "relevance_score": 89, "description": "Core AI skill. High demand but competitive market."},
    "tensorflow":    {"skill": "TensorFlow",    "relevance_score": 70, "description": "Established ML framework. Slightly declining vs PyTorch."},
    "pytorch":       {"skill": "PyTorch",       "relevance_score": 88, "description": "Preferred ML framework in research and production. Growing."},
    "graphql":       {"skill": "GraphQL",       "relevance_score": 68, "description": "Niche but valued in API-heavy products."},
    "rest api":      {"skill": "REST API",      "relevance_score": 65, "description": "Fundamental skill. Expected baseline, not a differentiator."},
    "java":          {"skill": "Java",          "relevance_score": 70, "description": "Enterprise staple. Demand stable but not growing."},
    "go":            {"skill": "Go",            "relevance_score": 82, "description": "Growing fast in cloud infrastructure and microservices."},
    "rust":          {"skill": "Rust",          "relevance_score": 75, "description": "Niche but rising. High value in systems programming."},
    "vue.js":        {"skill": "Vue.js",        "relevance_score": 65, "description": "Solid frontend framework. Smaller market share than React."},
    "angular":       {"skill": "Angular",       "relevance_score": 60, "description": "Enterprise frontend. Demand declining vs React/Vue."},
    "sql":           {"skill": "SQL",           "relevance_score": 80, "description": "Evergreen data skill. Always required."},
    "git":           {"skill": "Git",           "relevance_score": 70, "description": "Universal baseline. Expected in every role."},
    "ci/cd":         {"skill": "CI/CD",         "relevance_score": 85, "description": "DevOps essential. High demand across all engineering roles."},
    "terraform":     {"skill": "Terraform",     "relevance_score": 83, "description": "Infrastructure as code. Growing fast in DevOps roles."},
    "linux":         {"skill": "Linux",         "relevance_score": 78, "description": "Fundamental ops skill. Always relevant."},
    "microservices": {"skill": "Microservices", "relevance_score": 82, "description": "Architecture pattern. High demand in backend roles."},
    "node.js":       {"skill": "Node.js",       "relevance_score": 82, "description": "Popular JS runtime for backend. Steady demand."},
    "nodejs":        {"skill": "Node.js",       "relevance_score": 82, "description": "Popular JS runtime for backend. Steady demand."},
    "next.js":       {"skill": "Next.js",       "relevance_score": 86, "description": "React meta-framework. Growing fast in full-stack roles."},
    "nextjs":        {"skill": "Next.js",       "relevance_score": 86, "description": "React meta-framework. Growing fast in full-stack roles."},
}


def query_market_relevance(skill_name: str) -> dict:
    """
    Look up skill market relevance from the in-memory trends dict.
    Tries exact match, then partial match. Falls back to neutral score.
    """
    key = skill_name.lower().strip()

    # Exact match
    if key in MARKET_TRENDS:
        data = MARKET_TRENDS[key]
        return {**data, "matched": True}

    # Partial match — check if query is contained in any key or vice versa
    for stored_key, data in MARKET_TRENDS.items():
        if key in stored_key or stored_key in key:
            return {**data, "matched": True}

    return {
        "skill": skill_name,
        "relevance_score": 55,
        "description": "Skill not found in market trends database. Assigned neutral score.",
        "matched": False,
    }


def seed_market_trends():
    """No-op — data is already in memory. Kept for API compatibility."""
    print(f"[MarketTrends] {len(MARKET_TRENDS)} skills loaded from in-memory store.")
