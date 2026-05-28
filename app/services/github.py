import logging
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import GITHUB_API_BASE, GITHUB_TOKEN, STAR_SPIKE_THRESHOLD
from app.models import DailySnapshot, FetchLog, Project

logger = logging.getLogger(__name__)

HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"


async def fetch_trending_repos(
    language: str = "",
    since: str = "monthly",
    page: int = 1,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Fetch trending repositories via GitHub Search API."""
    date_map = {
        "daily": datetime.utcnow() - timedelta(days=14),
        "weekly": datetime.utcnow() - timedelta(weeks=4),
        "monthly": datetime.utcnow() - timedelta(days=90),
    }
    since_date = date_map.get(since, datetime.utcnow() - timedelta(days=30))
    date_str = since_date.strftime("%Y-%m-%d")

    # Use a broader query to get projects with more stars
    query = f"created:>{date_str} stars:>50"
    if language:
        query += f" language:{language}"

    url = f"{GITHUB_API_BASE}/search/repositories"
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": 100, "page": page}

    import asyncio
    _client = client or httpx.AsyncClient()
    try:
        repos: list[dict[str, Any]] = []
        resp = await _client.get(url, headers=HEADERS, params=params, timeout=30)
        
        if resp.status_code in (403, 429):
            logger.warning(f"GitHub API Rate limit exceeded. Status: {resp.status_code}")
            return repos

        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", []):
            repos.append(_parse_repo(item))
        
        await asyncio.sleep(1)
        return repos
    finally:
        if client is None:
            await _client.aclose()


def _parse_repo(item: dict[str, Any]) -> dict[str, Any]:
    """Parse a GitHub API repo item into our model fields."""
    return {
        "github_id": item["id"],
        "name": item["name"],
        "full_name": item["full_name"],
        "owner_avatar_url": (item.get("owner") or {}).get("avatar_url", ""),
        "description": item.get("description", ""),
        "url": item["html_url"],
        "homepage": item.get("homepage", ""),
        "language": item.get("language", ""),
        "stars": item.get("stargazers_count", 0),
        "forks": item.get("forks_count", 0),
        "open_issues": item.get("open_issues_count", 0),
        "watchers": item.get("watchers_count", 0),
        "topics": ",".join(item.get("topics", [])),
        "license_name": (item.get("license") or {}).get("name", ""),
        "created_at": _parse_dt(item.get("created_at")),
        "pushed_at": _parse_dt(item.get("pushed_at")),
    }


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def store_repos(db: AsyncSession, repos: list[dict[str, Any]]) -> dict[str, int]:
    """Store fetched repos, update existing or create new. Returns stats."""
    new_count = 0
    spike_count = 0
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    for repo_data in repos:
        result = await db.execute(
            select(Project).where(Project.github_id == repo_data["github_id"])
        )
        existing = result.scalar_one_or_none()

        if existing:
            old_stars = existing.stars
            repo_data["star_growth_24h"] = repo_data["stars"] - old_stars
            repo_data["star_growth_7d"] = repo_data["stars"] - old_stars  # simplified
            repo_data["last_updated_at"] = datetime.utcnow()
            if old_stars > 0 and repo_data["stars"] / old_stars > STAR_SPIKE_THRESHOLD:
                repo_data["spike_detected"] = True
                spike_count += 1
            for key, value in repo_data.items():
                if hasattr(existing, key) and key != "github_id":
                    setattr(existing, key, value)
        else:
            new_count += 1
            project = Project(**repo_data)
            db.add(project)

    await db.flush()

    # Store daily snapshots
    result = await db.execute(select(Project))
    all_projects = result.scalars().all()
    for proj in all_projects:
        snapshot = DailySnapshot(
            project_id=proj.id,
            github_id=proj.github_id,
            stars=proj.stars,
            forks=proj.forks,
            snapshot_date=today,
        )
        db.add(snapshot)

    # Log fetch
    log = FetchLog(
        projects_count=len(repos),
        new_projects=new_count,
        spikes_detected=spike_count,
        status="success",
    )
    db.add(log)

    return {"total": len(repos), "new": new_count, "spikes": spike_count}


async def sync_github_star(full_name: str, star: bool = True) -> bool:
    """Star or unstar a repository on GitHub using the configured token."""
    if not GITHUB_TOKEN:
        return False
        
    url = f"{GITHUB_API_BASE}/user/starred/{full_name}"
    headers = HEADERS.copy()
    headers["Content-Length"] = "0"
    
    async with httpx.AsyncClient() as client:
        try:
            if star:
                resp = await client.put(url, headers=headers, timeout=10)
            else:
                resp = await client.delete(url, headers=headers, timeout=10)
            return resp.status_code in (204, 304)
        except Exception as e:
            logger.error(f"Failed to sync star for {full_name}: {e}")
            return False
