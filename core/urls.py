from django.urls import path
from .views import landing, dashboard

from django.urls import path
from .views import landing
from . import views

app_name = "core"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("", landing, name="landing"),  # /
]
