from datetime import date, datetime
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings

class User(AbstractUser):
    email = models.EmailField(unique=True, verbose_name="ایمیل")
    is_vip = models.BooleanField(default=False, verbose_name="کاربر ویژه (VIP)")
    vip_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="تاریخ انقضای VIP")
    daily_usage = models.IntegerField(default=0, verbose_name="استفاده روزانه")
    last_usage_date = models.DateField(default=timezone.now, verbose_name="آخرین تاریخ استفاده")
    max_daily_quota = models.IntegerField(default=settings.GUEST_DAILY_LIMIT, verbose_name="حداکثر سهمیه روزانه")

    def check_and_reset_daily_usage(self):
        """Reset daily usage counter if the day has passed, and update VIP expiration."""
        today = timezone.localdate()
        if self.last_usage_date != today:
            self.daily_usage = 0
            self.last_usage_date = today

        # Check VIP status
        if self.is_vip:
            if self.vip_expires_at and timezone.now() > self.vip_expires_at:
                self.is_vip = False
                self.max_daily_quota = settings.GUEST_DAILY_LIMIT
            else:
                self.max_daily_quota = settings.VIP_DAILY_LIMIT
        else:
            self.max_daily_quota = settings.GUEST_DAILY_LIMIT
        self.save()

    @property
    def remaining_vip_days(self) -> int:
        if not self.is_vip or not self.vip_expires_at:
            return 0
        diff = self.vip_expires_at - timezone.now()
        return max(0, diff.days + 1)

    @property
    def remaining_quota(self) -> int:
        return max(0, self.max_daily_quota - self.daily_usage)

    def __str__(self):
        return f"{self.username} ({'VIP' if self.is_vip else 'عادی'})"

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"


class EmailOTP(models.Model):
    email = models.EmailField(verbose_name="ایمیل")
    username = models.CharField(max_length=150, verbose_name="نام کاربری درخواستی")
    password_hash = models.CharField(max_length=255, verbose_name="هش رمز عبور")
    otp_code = models.CharField(max_length=10, verbose_name="کد تایید ۶ رقمی")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    expires_at = models.DateTimeField(verbose_name="زمان انقضا")
    is_used = models.BooleanField(default=False, verbose_name="مصرف شده")

    def __str__(self):
        return f"OTP {self.otp_code} for {self.email} (Used: {self.is_used})"

    class Meta:
        verbose_name = "کد تایید ایمیل"
        verbose_name_plural = "کدهای تایید ایمیل"
        ordering = ['-created_at']
