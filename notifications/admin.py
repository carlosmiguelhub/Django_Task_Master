from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "kind", "task", "created_at", "read_at")
    list_filter = ("kind", "read_at", "created_at")
    search_fields = ("title", "message", "user__username", "task__title")
