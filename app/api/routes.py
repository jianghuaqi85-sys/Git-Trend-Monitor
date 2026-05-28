from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import DailySnapshot, FetchLog, Project

router = APIRouter()


@router.get("/api/projects")
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    language: str = Query("", description="Filter by language"),
    min_stars: int = Query(0, description="Minimum star count"),
    max_stars: int = Query(0, description="Maximum star count (0 = no limit)"),
    sort_by: str = Query("stars", description="Sort field: stars, star_growth_24h, created_at, pushed_at"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    show_viewed: bool = Query(False, description="Include viewed projects"),
    show_hidden: bool = Query(False, description="Include hidden projects"),
    favorites_only: bool = Query(False, description="Show only favorites"),
    trending_only: bool = Query(False, description="Show only trending projects"),
    topic: str = Query("", description="Filter by topic"),
    search: str = Query("", description="Search in name and description"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Project)

    if not show_hidden:
        query = query.where(Project.is_hidden == False)
    if not show_viewed:
        query = query.where(Project.is_viewed == False)
    if favorites_only:
        query = query.where(Project.is_favorite == True)
    if trending_only:
        query = query.where(Project.is_trending == True)
    if language:
        query = query.where(Project.language == language)
    if min_stars > 0:
        query = query.where(Project.stars >= min_stars)
    if max_stars > 0:
        query = query.where(Project.stars <= max_stars)
    if topic:
        query = query.where(Project.topics.ilike(f"%{topic}%"))
    if search:
        query = query.where(
            Project.name.ilike(f"%{search}%") | Project.description.ilike(f"%{search}%")
        )

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Sort
    sort_col = getattr(Project, sort_by, Project.stars)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    projects = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "projects": [_project_to_dict(p) for p in projects],
    }


@router.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(Project.id)))).scalar()
    viewed = (await db.execute(
        select(func.count(Project.id)).where(Project.is_viewed == True)
    )).scalar()
    hidden = (await db.execute(
        select(func.count(Project.id)).where(Project.is_hidden == True)
    )).scalar()
    favorites = (await db.execute(
        select(func.count(Project.id)).where(Project.is_favorite == True)
    )).scalar()
    trending = (await db.execute(
        select(func.count(Project.id)).where(Project.is_trending == True)
    )).scalar()
    spikes = (await db.execute(
        select(func.count(Project.id)).where(Project.spike_detected == True)
    )).scalar()

    # Top languages
    lang_query = (
        select(Project.language, func.count(Project.id).label("count"))
        .where(Project.language.isnot(None))
        .where(Project.language != "")
        .group_by(Project.language)
        .order_by(func.count(Project.id).desc())
        .limit(10)
    )
    langs = (await db.execute(lang_query)).fetchall()

    # Latest fetch log
    latest_log = (
        await db.execute(
            select(FetchLog).order_by(FetchLog.fetched_at.desc()).limit(1)
        )
    ).scalar_one_or_none()

    return {
        "total_projects": total or 0,
        "viewed": viewed or 0,
        "hidden": hidden or 0,
        "favorites": favorites or 0,
        "trending": trending or 0,
        "spikes": spikes or 0,
        "unviewed": (total or 0) - (viewed or 0),
        "top_languages": [{"language": r[0], "count": r[1]} for r in langs],
        "last_fetch": {
            "time": latest_log.fetched_at.isoformat() if latest_log else None,
            "projects_count": latest_log.projects_count if latest_log else 0,
            "new_projects": latest_log.new_projects if latest_log else 0,
            "spikes_detected": latest_log.spikes_detected if latest_log else 0,
        },
    }


@router.get("/api/languages")
async def list_languages(db: AsyncSession = Depends(get_db)):
    query = (
        select(Project.language, func.count(Project.id).label("count"))
        .where(Project.language.isnot(None))
        .where(Project.language != "")
        .group_by(Project.language)
        .order_by(func.count(Project.id).desc())
    )
    result = await db.execute(query)
    return [{"language": r[0], "count": r[1]} for r in result.fetchall()]


@router.get("/api/timeline")
async def get_timeline(days: int = Query(7, ge=1, le=30), db: AsyncSession = Depends(get_db)):
    from datetime import timedelta

    start = datetime.utcnow() - timedelta(days=days)
    query = (
        select(DailySnapshot.snapshot_date, func.count(DailySnapshot.id))
        .where(DailySnapshot.snapshot_date >= start)
        .group_by(DailySnapshot.snapshot_date)
        .order_by(DailySnapshot.snapshot_date.asc())
    )
    result = await db.execute(query)
    return [{"date": r[0].isoformat(), "count": r[1]} for r in result.fetchall()]


@router.put("/api/projects/{github_id}/viewed")
async def mark_viewed(github_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(Project)
        .where(Project.github_id == github_id)
        .values(is_viewed=True, viewed_at=datetime.utcnow())
    )
    return {"status": "ok"}


@router.put("/api/projects/{github_id}/favorite")
async def toggle_favorite(github_id: int, db: AsyncSession = Depends(get_db)):
    from app.services.github import sync_github_star
    
    result = await db.execute(select(Project).where(Project.github_id == github_id))
    proj = result.scalar_one_or_none()
    if not proj:
        return {"error": "not found"}
        
    proj.is_favorite = not proj.is_favorite
    
    # Sync with GitHub in background (or fire-and-forget)
    # We do this asynchronously but wait for it so we don't return before it's dispatched
    import asyncio
    asyncio.create_task(sync_github_star(proj.full_name, proj.is_favorite))
    
    return {"status": "ok", "is_favorite": proj.is_favorite}


@router.put("/api/projects/{github_id}/hide")
async def hide_project(github_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(Project).where(Project.github_id == github_id).values(is_hidden=True)
    )
    return {"status": "ok"}


@router.put("/api/projects/batch-viewed")
async def batch_mark_viewed(github_ids: list[int], db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(Project)
        .where(Project.github_id.in_(github_ids))
        .values(is_viewed=True, viewed_at=datetime.utcnow())
    )
    return {"status": "ok", "count": len(github_ids)}


@router.post("/api/fetch")
async def trigger_fetch(db: AsyncSession = Depends(get_db)):
    from app.services.github import fetch_trending_repos, store_repos

    # Calculate how many unviewed projects we have
    unviewed_count = await db.scalar(
        select(func.count(Project.id))
        .where(Project.is_viewed == False)
        .where(Project.is_hidden == False)
    )
    
    target_unviewed = 200
    if unviewed_count >= target_unviewed:
        # Just update top page for stats
        repos = await fetch_trending_repos(page=1)
        stats = await store_repos(db, repos)
        return {"status": "ok", "msg": "Enough unviewed projects, stats updated", **stats}

    total_new = 0
    total_spikes = 0
    total_repos = 0
    page = 1
    max_pages = 10 
    
    while unviewed_count < target_unviewed and page <= max_pages:
        repos = await fetch_trending_repos(page=page)
        if not repos:
            break # rate limit or no more data
        
        stats = await store_repos(db, repos)
        total_repos += stats["total"]
        total_new += stats["new"]
        total_spikes += stats["spikes"]
        
        # update unviewed count
        unviewed_count = await db.scalar(
            select(func.count(Project.id))
            .where(Project.is_viewed == False)
            .where(Project.is_hidden == False)
        )
        page += 1

    return {"status": "ok", "total": total_repos, "new": total_new, "spikes": total_spikes}


@router.get("/api/topics")
async def get_topics(db: AsyncSession = Depends(get_db)):
    # Fetch all topics from unviewed and unhidden projects
    query = select(Project.topics).where(Project.is_viewed == False).where(Project.is_hidden == False).where(Project.topics.isnot(None))
    result = await db.execute(query)
    topics_list = result.scalars().all()
    
    topic_counts = {}
    for topics_str in topics_list:
        if not topics_str:
            continue
        for t in topics_str.split(","):
            t = t.strip()
            if t:
                topic_counts[t] = topic_counts.get(t, 0) + 1
                
    # Sort by count desc and return top 30
    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:30]
    return [{"topic": k, "count": v} for k, v in sorted_topics]


@router.get("/api/projects/velocity")
async def get_velocity_leaderboard(db: AsyncSession = Depends(get_db)):
    query = (
        select(Project)
        .where(Project.is_hidden == False)
        .where(Project.star_growth_24h > 0)
        .order_by(Project.star_growth_24h.desc())
        .limit(10)
    )
    result = await db.execute(query)
    projects = result.scalars().all()
    return [_project_to_dict(p) for p in projects]


@router.get("/api/projects/{github_id}/readme")
async def get_readme(github_id: int, db: AsyncSession = Depends(get_db)):
    from app.services.github import HEADERS
    import httpx
    
    result = await db.execute(select(Project).where(Project.github_id == github_id))
    proj = result.scalar_one_or_none()
    if not proj:
        return {"error": "Project not found"}
        
    url = f"https://api.github.com/repos/{proj.full_name}/readme"
    headers = HEADERS.copy()
    headers["Accept"] = "application/vnd.github.v3.raw"
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return {"readme": resp.text}
        else:
            return {"error": "README not found or rate limited"}


@router.get("/api/export")
async def export_csv(type: str = Query("favorites", description="Export type: favorites or all"), db: AsyncSession = Depends(get_db)):
    from fastapi.responses import StreamingResponse
    import io
    import csv
    
    query = select(Project).where(Project.is_hidden == False)
    if type == "favorites":
        query = query.where(Project.is_favorite == True)
        
    result = await db.execute(query)
    projects = result.scalars().all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["GitHub ID", "Name", "Full Name", "URL", "Language", "Stars", "Forks", "Growth 24h", "Topics", "Created At"])
    
    for p in projects:
        writer.writerow([
            p.github_id, p.name, p.full_name, p.url, p.language, p.stars, p.forks, 
            p.star_growth_24h, p.topics, p.created_at.isoformat() if p.created_at else ""
        ])
        
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]), 
        media_type="text/csv", 
        headers={"Content-Disposition": f"attachment; filename=git_trend_{type}.csv"}
    )


def _project_to_dict(p: Project) -> dict:
    return {
        "github_id": p.github_id,
        "name": p.name,
        "full_name": p.full_name,
        "owner_avatar_url": p.owner_avatar_url,
        "description": p.description,
        "url": p.url,
        "homepage": p.homepage,
        "language": p.language,
        "stars": p.stars,
        "forks": p.forks,
        "open_issues": p.open_issues,
        "star_growth_24h": p.star_growth_24h,
        "star_growth_7d": p.star_growth_7d,
        "topics": p.topics,
        "license_name": p.license_name,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "pushed_at": p.pushed_at.isoformat() if p.pushed_at else None,
        "first_seen_at": p.first_seen_at.isoformat() if p.first_seen_at else None,
        "is_viewed": p.is_viewed,
        "is_favorite": p.is_favorite,
        "is_hidden": p.is_hidden,
        "is_trending": p.is_trending,
        "spike_detected": p.spike_detected,
    }
