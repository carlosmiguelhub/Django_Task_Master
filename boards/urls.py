from django.urls import path
from . import views

app_name = "boards"

urlpatterns = [
    # Boards
    path("", views.board_list, name="list"),
    path("<int:board_id>/", views.board_detail, name="detail"),
    path("<int:board_id>/edit/", views.board_update, name="update"),
    path("<int:board_id>/delete/", views.board_delete, name="delete"),

    # Task status actions (Start -> In Progress, Complete -> Done)
    path("task/<int:task_id>/start/", views.task_start, name="task_start"),
    path("task/<int:task_id>/complete/", views.task_complete, name="task_complete"),

    # ✅ NEW: Archive
    path("archive/", views.archive_list, name="archive_list"),
    path("task/<int:task_id>/archive/", views.task_archive, name="task_archive"),
]
