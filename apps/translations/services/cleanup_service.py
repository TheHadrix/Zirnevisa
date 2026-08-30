import os
import time
import threading
import logging
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)

def _delete_file_safely(file_path: str):
    """Safely delete file from disk if it exists."""
    try:
        p = Path(file_path)
        if p.exists() and p.is_file():
            p.unlink()
            logger.info(f"Auto-cleanup: Deleted file {file_path}")
    except Exception as e:
        logger.error(f"Auto-cleanup failed to delete {file_path}: {e}")

def schedule_file_cleanup(file_path: str, delay_seconds: int = 120):
    """Schedule deletion of a temporary file after delay_seconds (default: 2 minutes)."""
    if not file_path:
        return

    def delayed_cleanup():
        time.sleep(delay_seconds)
        _delete_file_safely(file_path)

    cleanup_thread = threading.Thread(target=delayed_cleanup, daemon=True)
    cleanup_thread.start()
    logger.info(f"Scheduled cleanup for {file_path} in {delay_seconds} seconds")

def sweep_old_files(max_age_seconds: int = 600):
    """Clean up any leftover files in uploads/outputs directories older than max_age_seconds."""
    dirs_to_clean = [settings.UPLOAD_DIR, settings.OUTPUT_DIR]
    now = time.time()
    
    for directory in dirs_to_clean:
        if not os.path.exists(directory):
            continue
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    mtime = os.path.getmtime(item_path)
                    if (now - mtime) > max_age_seconds:
                        _delete_file_safely(item_path)
        except Exception as e:
            logger.warning(f"Error sweeping old files in {directory}: {e}")
