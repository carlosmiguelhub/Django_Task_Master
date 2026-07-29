from django.urls import path

from . import views

app_name = "planner"

urlpatterns = [
    path("", views.planner_view, name="index"),
    path("api/items/", views.planner_items, name="items"),
    path("api/events/create/", views.event_create, name="event_create"),
    path("api/events/<int:event_id>/update/", views.event_update, name="event_update"),
    path("api/events/<int:event_id>/delete/", views.event_delete, name="event_delete"),
    path("api/reschedule/", views.item_reschedule, name="reschedule"),
    path(
        "api/tasks/<int:task_id>/unschedule/",
        views.task_unschedule,
        name="task_unschedule",
    ),
]
