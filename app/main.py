import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import HTMLResponse

from app.api.routes import router
from app.config import FETCH_INTERVAL_MINUTES, PORT
from app.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def scheduled_fetch():
    """Periodic job to fetch trending repos."""
    from app.services.github import fetch_trending_repos, store_repos
    from app.database import async_session
    from sqlalchemy import select, func
    from app.models import Project

    logger.info("Starting scheduled fetch...")
    try:
        async with async_session() as db:
            unviewed_count = await db.scalar(
                select(func.count(Project.id))
                .where(Project.is_viewed == False)
                .where(Project.is_hidden == False)
            )
            
            target_unviewed = 200
            if unviewed_count >= target_unviewed:
                repos = await fetch_trending_repos(page=1)
                stats = await store_repos(db, repos)
            else:
                page = 1
                while unviewed_count < target_unviewed and page <= 10:
                    repos = await fetch_trending_repos(page=page)
                    if not repos:
                        break
                    await store_repos(db, repos)
                    unviewed_count = await db.scalar(
                        select(func.count(Project.id))
                        .where(Project.is_viewed == False)
                        .where(Project.is_hidden == False)
                    )
                    page += 1
            await db.commit()
            logger.info("Scheduled fetch complete")
    except Exception as e:
        logger.error(f"Scheduled fetch failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialized")

    scheduler.add_job(
        scheduled_fetch,
        "interval",
        minutes=FETCH_INTERVAL_MINUTES,
        id="fetch_trending",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started (interval: {FETCH_INTERVAL_MINUTES}min)")

    # Run initial fetch
    await scheduled_fetch()

    yield

    scheduler.shutdown()
    logger.info("Scheduler stopped")


app = FastAPI(title="Git Trend Monitor", version="1.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)
