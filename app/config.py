import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR}/git_trend.db")

# GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API_BASE = "https://api.github.com"

# Scheduler
FETCH_INTERVAL_MINUTES = int(os.getenv("FETCH_INTERVAL_MINUTES", "60"))

# Server
PORT = int(os.getenv("PORT", "8000"))

# Trend detection thresholds
STAR_SPIKE_THRESHOLD = 1.5  # 50% increase in 24h triggers alert
