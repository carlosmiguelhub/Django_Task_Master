from django.urls import path
from .views import daily_plan, daily_plan_chat, dashboard

app_name = "app"

urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),  # /app/dashboard/
    path("dashboard/daily-plan/", daily_plan, name="daily_plan"),
    path("dashboard/daily-plan/chat/", daily_plan_chat, name="daily_plan_chat"),
]
