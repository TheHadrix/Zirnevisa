from django.apps import AppConfig
from django.db.models.signals import post_migrate

def create_default_superuser(sender, **kwargs):
    """Automatically create default admin user after database migrations if none exists."""
    import os
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    admin_username = os.getenv("ADMIN_USERNAME").strip()
    admin_email = os.getenv("ADMIN_EMAIL").strip()
    admin_password = os.getenv("ADMIN_PASSWORD").strip()

    try:
        if not User.objects.filter(username=admin_username).exists() and not User.objects.filter(is_superuser=True).exists():
            User.objects.create_superuser(
                username=admin_username,
                email=admin_email,
                password=admin_password
            )
            print(f"[Zirnevisa] Default superuser automatically created from env: {admin_username} / {admin_email}")
    except Exception:
        pass

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = 'مدیریت کاربران و احراز هویت'

    def ready(self):
        post_migrate.connect(create_default_superuser, sender=self)

