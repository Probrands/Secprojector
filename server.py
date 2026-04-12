import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import config
from database.filings import FilingsDatabase

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("server")

db = FilingsDatabase()


@asynccontextmanager
async def lifespan(app):
    from main import InsiderAlertBot
    bot = InsiderAlertBot()
    thread = threading.Thread(target=bot.start_background, daemon=True)
    thread.start()
    logger.info("Bot started in background thread")
    yield
    bot.running = False
    bot.scheduler.shutdown(wait=False)
    logger.info("Bot stopped")


app = FastAPI(title="SEC Insider Alert Map", lifespan=lifespan)


@app.get("/api/purchases")
def get_purchases(days: int = Query(default=90, ge=1, le=365)):
    """Return insider purchases with location data for the map."""
    return db.get_purchases_for_map(days=days)


WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
