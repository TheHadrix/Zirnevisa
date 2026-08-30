from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from accounts.models import User, EmailOTP

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'is_vip', 'daily_usage', 'max_daily_quota', 'is_staff')
    list_filter = ('is_vip', 'is_staff', 'is_superuser')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('اطلاعات سهمیه و VIP', {'fields': ('is_vip', 'vip_expires_at', 'daily_usage', 'last_usage_date', 'max_daily_quota')}),
    )

@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'otp_code', 'expires_at', 'is_used', 'created_at')
    list_filter = ('is_used',)
    search_fields = ('email', 'username', 'otp_code')
