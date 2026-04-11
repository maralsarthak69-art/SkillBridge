"""
youtube_api.py — High-quality YouTube tutorial fetcher

Quality Score Formula:
    score = (view_count * 0.4) + (like_count * 0.4) + (recency_bonus * 0.2)
    recency_bonus = max(0, 100 - years_since_published * 15)

Query Engineering:
    - Appends "tutorial" + "for beginners" or "advanced" based on gap_severity
    - Filters: medium/long duration, English, video type only
    - Re-ranks by quality score after YouTube relevance fetch
    - Blacklists clickbait channels and low-quality content
"""

import re
from datetime import datetime, timezone
from django.conf import settings
from django.core.cache import cache

try:
    from googleapiclient.discovery import build
    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False

CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours

# Channels known for high-quality tech education
QUALITY_CHANNELS = {
    "traversy media", "fireship", "tech with tim", "corey schafer",
    "sentdex", "programming with mosh", "net ninja", "academind",
    "freecodecamp.org", "cs dojo", "tech lead", "arjan codes",
    "patrick loeber", "anthonygg_", "indently", "pixegami",
    "networkchuck", "tiff in tech", "bytebytego",
}

# Channels to deprioritize
LOW_QUALITY_SIGNALS = ["shorts", "reaction", "vlog", "unboxing", "review"]


def _build_query(skill_name: str, gap_severity: str = "moderate") -> str:
    """
    Build an optimized YouTube search query for educational content.
    """
    base = skill_name.strip()

    if gap_severity == "critical":
        # Beginner-focused for critical gaps
        return f"{base} tutorial complete beginner guide"
    elif gap_severity == "moderate":
        return f"{base} tutorial project build"
    else:
        # Bonus/minor gaps — more advanced
        return f"{base} advanced tutorial best practices"


def _quality_score(item: dict) -> float:
    """
    Compute a quality score for a YouTube video.
    Higher = better educational content.
    """
    stats    = item.get("statistics", {})
    snippet  = item.get("snippet", {})

    view_count = int(stats.get("viewCount", 0))
    like_count = int(stats.get("likeCount", 0))

    # Recency bonus — newer content scores higher (capped at 100)
    published_str = snippet.get("publishedAt", "")
    recency_bonus = 50  # default
    if published_str:
        try:
            published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            years_old = (datetime.now(timezone.utc) - published).days / 365
            recency_bonus = max(0, 100 - years_old * 15)
        except (ValueError, TypeError):
            pass

    # Channel quality boost
    channel_lower = snippet.get("channelTitle", "").lower()
    channel_boost = 30 if any(q in channel_lower for q in QUALITY_CHANNELS) else 0

    # Penalize low-quality signals in title
    title_lower = snippet.get("title", "").lower()
    quality_penalty = -20 if any(s in title_lower for s in LOW_QUALITY_SIGNALS) else 0

    # Normalize view/like counts (log scale)
    import math
    view_score = math.log10(max(view_count, 1)) * 10
    like_score = math.log10(max(like_count, 1)) * 10

    return (view_score * 0.4) + (like_score * 0.4) + (recency_bonus * 0.2) + channel_boost + quality_penalty


def _parse_duration(iso_duration: str) -> str:
    """Convert ISO 8601 duration (PT10M30S) to human-readable (10m 30s)."""
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration or "")
    if not match:
        return ""
    hours, minutes, seconds = match.groups()
    parts = []
    if hours:   parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if seconds: parts.append(f"{seconds}s")
    return " ".join(parts)


def fetch_youtube_tutorials(skill_name: str, gap_severity: str = "moderate",
                             max_results: int = 5) -> list:
    """
    Fetch top-quality YouTube tutorials for a skill gap.

    Args:
        skill_name:   The skill to search for
        gap_severity: "critical" | "moderate" | "minor" — affects query style
        max_results:  Number of results to return

    Returns:
        List of resource dicts, sorted by quality score:
        [{title, url, thumbnail, channel, duration, quality_score, source}]
    """
    cache_key = f"yt_{skill_name.lower().replace(' ', '_')}_{gap_severity}"
    cached    = cache.get(cache_key)
    if cached:
        return cached

    if not YOUTUBE_AVAILABLE or not settings.YOUTUBE_API_KEY:
        return _fallback_resources(skill_name)

    try:
        youtube = build("youtube", "v3", developerKey=settings.YOUTUBE_API_KEY)
        query   = _build_query(skill_name, gap_severity)

        # Step 1: Search for videos
        search_response = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=max_results * 3,  # fetch more, re-rank, return top N
            relevanceLanguage="en",
            videoDuration="medium",      # 4–20 minutes
            safeSearch="strict",
            order="relevance",
        ).execute()

        video_ids = [
            item["id"]["videoId"]
            for item in search_response.get("items", [])
            if item.get("id", {}).get("videoId")
        ]

        if not video_ids:
            return _fallback_resources(skill_name)

        # Step 2: Fetch statistics + content details for quality scoring
        details_response = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids),
        ).execute()

        # Step 3: Score and sort
        scored = []
        for item in details_response.get("items", []):
            snippet  = item.get("snippet", {})
            score    = _quality_score(item)
            duration = _parse_duration(
                item.get("contentDetails", {}).get("duration", "")
            )
            scored.append({
                "source":        "youtube",
                "title":         snippet.get("title", ""),
                "url":           f"https://www.youtube.com/watch?v={item['id']}",
                "thumbnail":     snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "channel":       snippet.get("channelTitle", ""),
                "duration":      duration,
                "quality_score": round(score, 1),
                "api_enriched":  True,
            })

        scored.sort(key=lambda x: x["quality_score"], reverse=True)
        results = scored[:max_results]

        cache.set(cache_key, results, CACHE_TIMEOUT)
        return results

    except Exception:
        return _fallback_resources(skill_name)


def _fallback_resources(skill_name: str) -> list:
    """Return curated fallback when YouTube API is unavailable."""
    return [
        {
            "source":        "youtube",
            "title":         f"{skill_name} Full Tutorial for Beginners",
            "url":           f"https://www.youtube.com/results?search_query={skill_name.replace(' ', '+')}+tutorial",
            "thumbnail":     "",
            "channel":       "Search YouTube",
            "duration":      "",
            "quality_score": 0.0,
            "api_enriched":  False,
        }
    ]


def enrich_roadmap_with_youtube(roadmap: dict) -> dict:
    """
    Enrich a roadmap's hacker_path resources with real YouTube data.
    Replaces source_hook placeholders with actual video results.
    Called after generate_dual_path_roadmap() if YouTube API is available.
    """
    for unit in roadmap.get("roadmap", []):
        skill_name   = unit.get("skill", "")
        gap_severity = unit.get("gap_severity", "moderate")
        hacker_path  = unit.get("hacker_path", {})

        if not hacker_path:
            continue

        youtube_results = fetch_youtube_tutorials(skill_name, gap_severity, max_results=2)
        if youtube_results:
            # Replace or prepend YouTube results to hacker resources
            existing   = [r for r in hacker_path.get("resources", [])
                          if r.get("source") != "youtube"]
            hacker_path["resources"] = youtube_results + existing
            hacker_path["estimated_hours"] = sum(
                r.get("estimated_hours", 0) for r in hacker_path["resources"]
            )

    return roadmap
