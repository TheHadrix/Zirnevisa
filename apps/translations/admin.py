from django.contrib import admin
from translations.models import ProviderConfig, TranslationTask, GuestUsage

@admin.register(ProviderConfig)
class ProviderConfigAdmin(admin.ModelAdmin):
    list_display = ('provider_name', 'model_name', 'priority_order', 'is_active', 'created_at')
    list_editable = ('priority_order', 'is_active')
    list_filter = ('is_active', 'provider_name')

@admin.register(TranslationTask)
class TranslationTaskAdmin(admin.ModelAdmin):
    list_display = ('task_id', 'filename', 'user', 'status', 'progress', 'char_count', 'created_at')
    list_filter = ('status', 'target_lang')
    search_fields = ('filename', 'task_id', 'identifier')

@admin.register(GuestUsage)
class GuestUsageAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'daily_usage', 'last_usage_date')
    search_fields = ('identifier',)
