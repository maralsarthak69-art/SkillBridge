"""
resource_service.py
Fetches learning resources from YouTube and Udemy for a given skill.
Results are cached to avoid repeated API calls.
"""
import requests
from django.conf import settings
from django.core.cache import cache
from googleapiclient.discovery import build


CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours


# ──────────────────────────────────────────────
# YouTube
# ──────────────────────────────────────────────

def fetch_youtube_resources(skill_name: str, max_results: int = 5) -> list:
    """
    Queries YouTube Data API v3 for top tutorial videos for a skill.
    Returns list of resource dicts.
    """
    cache_key = f"youtube_{skill_name.lower().replace(' ', '_')}"
    cached    = cache.get(cache_key)
    if cached:
        return cached

    if not settings.YOUTUBE_API_KEY:
        return []

    try:
        youtube  = build("youtube", "v3", developerKey=settings.YOUTUBE_API_KEY)
        request  = youtube.search().list(
            q=f"{skill_name} tutorial for beginners",
            part="snippet",
            type="video",
            maxResults=max_results,
            relevanceLanguage="en",
            videoDuration="medium",
        )
        response = request.execute()

        results = []
        for item in response.get("items", []):
            snippet = item["snippet"]
            results.append({
                "source":    "youtube",
                "title":     snippet.get("title", ""),
                "url":       f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "channel":   snippet.get("channelTitle", ""),
                "duration":  "",
            })

        cache.set(cache_key, results, CACHE_TIMEOUT)
        return results

    except Exception:
        return []


# ──────────────────────────────────────────────
# Udemy
# ──────────────────────────────────────────────

def fetch_udemy_resources(skill_name: str, max_results: int = 5) -> list:
    """
    Queries Udemy's course discovery API for courses related to a skill.
    Returns list of resource dicts.
    """
    cache_key = f"udemy_{skill_name.lower().replace(' ', '_')}"
    cached    = cache.get(cache_key)
    if cached:
        return cached

    if not settings.UDEMY_CLIENT_ID or not settings.UDEMY_CLIENT_SECRET:
        return []

    try:
        response = requests.get(
            "https://www.udemy.com/api-2.0/courses/",
            auth=(settings.UDEMY_CLIENT_ID, settings.UDEMY_CLIENT_SECRET),
            params={
                "search":        skill_name,
                "page_size":     max_results,
                "ordering":      "relevance",
                "language":      "en",
                "fields[course]": "title,url,image_480x270,primary_category,visible_instructors",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for course in data.get("results", []):
            instructors = course.get("visible_instructors", [])
            channel     = instructors[0].get("display_name", "") if instructors else ""
            results.append({
                "source":    "udemy",
                "title":     course.get("title", ""),
                "url":       f"https://www.udemy.com{course.get('url', '')}",
                "thumbnail": course.get("image_480x270", ""),
                "channel":   channel,
                "duration":  "",
            })

        cache.set(cache_key, results, CACHE_TIMEOUT)
        return results

    except Exception:
        return []


# ──────────────────────────────────────────────
# Combined fetch + DB save
# ──────────────────────────────────────────────

def fetch_and_store_resources(skill) -> int:
    """
    Fetches resources from both YouTube and Udemy for a skill,
    saves new ones to the DB, and returns the count of new records added.
    """
    from .models import LearningResource

    youtube_results = fetch_youtube_resources(skill.name)
    udemy_results   = fetch_udemy_resources(skill.name)
    all_results     = youtube_results + udemy_results

    created_count = 0
    for item in all_results:
        _, created = LearningResource.objects.get_or_create(
            skill=skill,
            url=item["url"],
            defaults={
                "source":    item["source"],
                "title":     item["title"],
                "thumbnail": item["thumbnail"],
                "channel":   item["channel"],
                "duration":  item["duration"],
            },
        )
        if created:
            created_count += 1

    return created_count
