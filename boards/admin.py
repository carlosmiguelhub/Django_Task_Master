from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Board, Task

@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "created_at")
    search_fields = ("name", "owner__username", "owner__email")
    list_filter = ("created_at",)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "board", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "board__name")
