from django.apps import AppConfig

class TranslationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'translations'
    verbose_name = 'مدیریت ترجمه و هوش مصنوعی'

    def ready(self):
        try:
            from translations.services.cleanup_service import sweep_old_files
            sweep_old_files()
        except Exception:
            pass
