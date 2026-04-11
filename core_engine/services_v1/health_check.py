"""
health_check.py — Background API health checker

Scans roadmap resource URLs for 404/broken links.
Designed to run as a management command or scheduled task (cron/Celery).

Usage:
    python manage.py check_roadmap_links
    (management command defined below)
"""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.utils import timezone


TIMEOUT_SECONDS = 8
MAX_WORKERS     = 10  # concurrent checks

# Domains that block HEAD requests — use GET instead
GET_ONLY_DOMAINS = {
    "udemy.com", "labs.play-with-k8s.com", "linkedin.com",
    "pluralsight.com", "coursera.org",
}

# Domains that block all automated requests but are known-good
TRUSTED_DOMAINS = {
    "udemy.com", "coursera.org", "linkedin.com", "pluralsight.com",
    "aws.amazon.com", "hashicorp.com",
}


def check_url(url: str) -> dict:
    """
    Check if a URL is reachable. Returns status dict.
    Uses GET for domains that block HEAD requests.
    """
    if not url or url.startswith("https://www.youtube.com/results"):
        return {"url": url, "status": "skipped", "code": None}

    # Trusted domains — skip automated check, known to block bots
    if any(domain in url for domain in TRUSTED_DOMAINS):
        return {"url": url, "status": "trusted", "code": None}

    # Determine method based on domain
    use_get = any(domain in url for domain in GET_ONLY_DOMAINS)
    method  = requests.get if use_get else requests.head

    try:
        response = method(
            url,
            timeout=TIMEOUT_SECONDS,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SkillBuild-HealthCheck/1.0)"},
            stream=True,   # don't download body for GET
        )
        ok = response.status_code < 400
        return {
            "url":    url,
            "status": "ok" if ok else "broken",
            "code":   response.status_code,
        }
    except requests.exceptions.Timeout:
        return {"url": url, "status": "timeout", "code": None}
    except requests.exceptions.ConnectionError:
        return {"url": url, "status": "unreachable", "code": None}
    except Exception as e:
        return {"url": url, "status": "error", "code": str(e)}


def scan_roadmap_links(roadmap_id: int = None) -> dict:
    """
    Scan all resource URLs in RoadmapTask records.
    If roadmap_id is given, scan only that roadmap.

    Returns:
        {
            "scanned":   int,
            "ok":        int,
            "broken":    [{"url", "status", "code", "task_id", "skill_name"}],
            "skipped":   int,
            "checked_at": str,
        }
    """
    from core_engine.models import RoadmapTask

    qs = RoadmapTask.objects.all()
    if roadmap_id:
        qs = qs.filter(roadmap_id=roadmap_id)

    # Collect all URLs with their task context
    url_tasks = []
    for task in qs:
        for resource in task.hacker_resources + task.certified_resources:
            url = resource.get("url", "")
            if url:
                url_tasks.append({
                    "url":        url,
                    "task_id":    task.id,
                    "skill_name": task.skill_name,
                })

    if not url_tasks:
        return {"scanned": 0, "ok": 0, "broken": [], "skipped": 0,
                "checked_at": timezone.now().isoformat()}

    # Concurrent URL checks
    results   = {"ok": 0, "broken": [], "skipped": 0}
    url_map   = {item["url"]: item for item in url_tasks}
    unique_urls = list(url_map.keys())

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(check_url, url): url for url in unique_urls}
        for future in as_completed(futures):
            result = future.result()
            url    = result["url"]
            ctx    = url_map.get(url, {})

            if result["status"] == "ok":
                results["ok"] += 1
            elif result["status"] in ("skipped", "trusted"):
                results["skipped"] += 1
            else:
                results["broken"].append({
                    **result,
                    "task_id":    ctx.get("task_id"),
                    "skill_name": ctx.get("skill_name"),
                })

    return {
        "scanned":    len(unique_urls),
        "ok":         results["ok"],
        "broken":     results["broken"],
        "skipped":    results["skipped"],
        "checked_at": timezone.now().isoformat(),
    }
