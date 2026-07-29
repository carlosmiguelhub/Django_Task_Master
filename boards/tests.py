import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Board, Task


class TaskManagementTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user("owner", password="test-pass-123")
        self.other_user = user_model.objects.create_user("other", password="test-pass-123")
        self.board = Board.objects.create(owner=self.owner, name="Launch")
        self.task = Task.objects.create(
            board=self.board,
            title="Draft release notes",
            priority=Task.Priority.NORMAL,
            due_date=datetime.date(2027, 1, 20),
            due_time=datetime.time(15, 30),
        )

    def test_owner_can_update_task(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("boards:task_update", args=[self.task.id]),
            {
                "title": "Publish release notes",
                "description": "Include the migration guide.",
                "priority": Task.Priority.HIGH,
                "due_date": "2027-01-21",
                "due_time": "16:00",
            },
        )

        self.assertRedirects(
            response,
            reverse("boards:detail", args=[self.board.id]),
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Publish release notes")
        self.assertEqual(self.task.description, "Include the migration guide.")
        self.assertEqual(self.task.priority, Task.Priority.HIGH)

    def test_non_owner_cannot_open_task_editor(self):
        self.client.force_login(self.other_user)
        response = self.client.get(
            reverse("boards:task_update", args=[self.task.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_owner_can_delete_active_task(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("boards:task_delete_active", args=[self.task.id])
        )
        self.assertRedirects(
            response,
            reverse("boards:detail", args=[self.board.id]),
        )
        self.assertFalse(Task.objects.filter(id=self.task.id).exists())

    def test_active_task_renders_live_deadline_timer(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("boards:detail", args=[self.board.id])
        )

        self.assertContains(response, "data-task-timer")
        self.assertContains(response, "data-created-at")
        self.assertContains(response, "data-due-at")
        self.assertContains(response, "data-time-left")
        self.assertContains(response, 'data-task-view="board"')
        self.assertContains(response, 'data-task-view="list"')
