from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, Index
from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    github_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(500), nullable=False)
    full_name = Column(String(500), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    url = Column(String(1000), nullable=False)
    homepage = Column(String(1000), nullable=True)
    owner_avatar_url = Column(String(1000), nullable=True)
    language = Column(String(100), nullable=True, index=True)
    stars = Column(Integer, default=0, index=True)
    forks = Column(Integer, default=0)
    open_issues = Column(Integer, default=0)
    watchers = Column(Integer, default=0)
    star_growth_24h = Column(Float, default=0.0)
    star_growth_7d = Column(Float, default=0.0)
    topics = Column(Text, nullable=True)  # JSON array as string
    license_name = Column(String(200), nullable=True)
    created_at = Column(DateTime, nullable=True)
    pushed_at = Column(DateTime, nullable=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # User interaction
    is_viewed = Column(Boolean, default=False, index=True)
    is_favorite = Column(Boolean, default=False, index=True)
    is_hidden = Column(Boolean, default=False, index=True)
    viewed_at = Column(DateTime, nullable=True)
    user_note = Column(Text, nullable=True)

    # Trend detection
    is_trending = Column(Boolean, default=False)
    spike_detected = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_language_stars", "language", "stars"),
        Index("idx_is_hidden_is_viewed", "is_hidden", "is_viewed"),
    )


class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False, index=True)
    github_id = Column(Integer, nullable=False)
    stars = Column(Integer, nullable=False)
    forks = Column(Integer, nullable=False)
    snapshot_date = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index("idx_project_date", "project_id", "snapshot_date"),
    )


class FetchLog(Base):
    __tablename__ = "fetch_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    projects_count = Column(Integer, default=0)
    new_projects = Column(Integer, default=0)
    spikes_detected = Column(Integer, default=0)
    status = Column(String(50), default="success")
    error_message = Column(Text, nullable=True)
