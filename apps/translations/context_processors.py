from django.conf import settings

def app_settings(request):
    """Make core application limits and configurations globally accessible in all templates."""
    char_limit = getattr(settings, "CHAR_LIMIT", 38000)
    persian_digits = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    char_limit_fa = f"{char_limit:,}".translate(persian_digits)

    return {
        "CHAR_LIMIT": char_limit,
        "CHAR_LIMIT_FA": char_limit_fa,
        "GUEST_DAILY_LIMIT": getattr(settings, "GUEST_DAILY_LIMIT", 5),
        "VIP_DAILY_LIMIT": getattr(settings, "VIP_DAILY_LIMIT", 20),
    }
