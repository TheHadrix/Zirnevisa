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
            logger.info(f"Auto-cleanup: Deleted guest file {file_path}")
    except Exception as e:
        logger.error(f"Auto-cleanup failed to delete {file_path}: {e}")

def schedule_file_cleanup(file_path: str, delay_seconds: int = 300):
    """Schedule deletion of a temporary guest file after delay_seconds (default: 5 minutes = 300s)."""
    if not file_path:
        return

    def delayed_cleanup():
        time.sleep(delay_seconds)
        _delete_file_safely(file_path)

    cleanup_thread = threading.Thread(target=delayed_cleanup, daemon=True)
    cleanup_thread.start()
    logger.info(f"Scheduled guest cleanup for {file_path} in {delay_seconds} seconds (5 minutes)")

def sweep_old_files(max_age_seconds: int = 600):
    """Clean up old temporary guest files without deleting logged-in users' files."""
    try:
        from translations.models import TranslationTask
        # Find active output files of logged in users to protect them
        user_files = set(
            TranslationTask.objects.filter(user__isnull=False)
            .exclude(result_file_path__isnull=True)
            .values_list('result_file_path', flat=True)
        )
    except Exception:
        user_files = set()

    dirs_to_clean = [settings.UPLOAD_DIR, settings.OUTPUT_DIR]
    now = time.time()
    
    for directory in dirs_to_clean:
        if not os.path.exists(directory):
            continue
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    # Do not delete if it belongs to a registered user
                    if str(Path(item_path).resolve()) in {str(Path(f).resolve()) for f in user_files if f}:
                        continue
                    mtime = os.path.getmtime(item_path)
                    if (now - mtime) > max_age_seconds:
                        _delete_file_safely(item_path)
        except Exception as e:
            logger.warning(f"Error sweeping old files in {directory}: {e}")
