import os
import sys
from pathlib import Path
from django.core.wsgi import get_wsgi_application

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / 'apps'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

application = get_wsgi_application()

# Automatically run database migrations when the application boots up
try:
    from django.core.management import call_command
    call_command('migrate', interactive=False)
except Exception as e:
    import logging
    logging.getLogger('django').warning(f"Auto-migrate on startup notice: {e}")
