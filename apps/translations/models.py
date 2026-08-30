import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone

class ProviderConfig(models.Model):
    PROVIDER_CHOICES = [
        ('gemini', 'Google Gemini'),
        ('mistral', 'Mistral AI'),
    ]

    provider_name = models.CharField(max_length=50, choices=PROVIDER_CHOICES, default='gemini', verbose_name="ارائه‌دهنده")
    model_name = models.CharField(max_length=100, default='gemini/gemini-3.6-flash', verbose_name="نام مدل هوش مصنوعی")
    api_key = models.CharField(max_length=255, verbose_name="کلید API")
    priority_order = models.IntegerField(default=1, verbose_name="ترتیب اولویت")
    is_active = models.BooleanField(default=True, verbose_name="فعال است")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    def __str__(self):
        return f"{self.get_provider_name_display()} - {self.model_name} (Priority {self.priority_order})"

    class Meta:
        verbose_name = "تنظیمات ارائه‌دهنده هوش مصنوعی"
        verbose_name_plural = "تنظیمات ارائه‌دهندگان هوش مصنوعی"
        ordering = ['priority_order', 'id']


class TranslationTask(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'در انتظار'),
        ('PROCESSING', 'در حال پردازش'),
        ('COMPLETED', 'تکمیل شده'),
        ('FAILED', 'خطا در پردازش'),
    ]

    task_id = models.CharField(max_length=64, unique=True, default=uuid.uuid4, verbose_name="شناسه تسک")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks', verbose_name="کاربر")
    identifier = models.CharField(max_length=255, verbose_name="شناسه مهمان/IP")
    filename = models.CharField(max_length=255, verbose_name="نام فایل")
    char_count = models.IntegerField(default=0, verbose_name="تعداد کاراکتر")
    target_lang = models.CharField(max_length=10, default='fa', verbose_name="زبان مقصد")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name="وضعیت")
    progress = models.IntegerField(default=0, verbose_name="درصد پیشرفت")
    current_chunk = models.IntegerField(default=0, verbose_name="بخش جاری")
    total_chunks = models.IntegerField(default=0, verbose_name="مجموع بخش‌ها")
    provider_used = models.CharField(max_length=150, null=True, blank=True, verbose_name="مدل هوش مصنوعی استفاده‌شده")
    result_file_path = models.CharField(max_length=500, null=True, blank=True, verbose_name="مسیر فایل خروجی")
    error_message = models.TextField(null=True, blank=True, verbose_name="متن خطا")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخرین به‌روزرسانی")

    def __str__(self):
        return f"Task {self.task_id[:8]} - {self.filename} ({self.get_status_display()})"

    class Meta:
        verbose_name = "تسک ترجمه"
        verbose_name_plural = "تسک‌های ترجمه"
        ordering = ['-created_at']


class GuestUsage(models.Model):
    identifier = models.CharField(max_length=255, unique=True, verbose_name="شناسه مهمان")
    daily_usage = models.IntegerField(default=0, verbose_name="استفاده امروز")
    last_usage_date = models.DateField(default=timezone.now, verbose_name="تاریخ آخرین استفاده")

    def check_and_reset_daily_usage(self):
        today = timezone.localdate()
        if self.last_usage_date != today:
            self.daily_usage = 0
            self.last_usage_date = today
            self.save()

    def __str__(self):
        return f"Guest {self.identifier} ({self.daily_usage}/{settings.GUEST_DAILY_LIMIT})"

    class Meta:
        verbose_name = "استفاده کاربر مهمان"
        verbose_name_plural = "استفاده کاربران مهمان"
