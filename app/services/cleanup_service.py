import asyncio
import os
import time
import logging
from pathlib import Path
from app.config import CLEANUP_DELAY_SECONDS, UPLOAD_DIR

logger = logging.getLogger(__name__)

async def delayed_file_cleanup(file_paths: list, delay_seconds: int = CLEANUP_DELAY_SECONDS):
    """
    Waits for delay_seconds and deletes the specified files from disk.
    """
    try:
        await asyncio.sleep(delay_seconds)
        for path_str in file_paths:
            if not path_str:
                continue
            p = Path(path_str)
            if p.exists() and p.is_file():
                try:
                    os.remove(p)
                    logger.info(f"Cleaned up temporary file: {p.name}")
                except Exception as e:
                    logger.error(f"Error removing file {p}: {e}")
    except Exception as e:
        logger.error(f"Error during delayed file cleanup: {e}")

def sweep_old_files(max_age_seconds: int = 300):
    """
    Removes leftover temporary files older than max_age_seconds on startup.
    """
    try:
        now = time.time()
        for f in UPLOAD_DIR.glob("*.*"):
            if f.is_file():
                try:
                    if now - f.stat().st_mtime > max_age_seconds:
                        f.unlink()
                        logger.info(f"Swept old temporary file: {f.name}")
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error during sweep_old_files: {e}")
