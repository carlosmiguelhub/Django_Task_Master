import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boards.models import Board, Task

from .models import CalendarEvent


class PlannerTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user("planner-user", password="test-pass-123")
        self.other_user = user_model.objects.create_user("planner-other", password="test-pass-123")
        self.board = Board.objects.create(owner=self.user, name="Product")
        self.other_board = Board.objects.create(owner=self.other_user, name="Private")
        self.today = timezone.localdate()
        self.task = Task.objects.create(
            board=self.board,
            title="Review roadmap",
            due_date=self.today,
            due_time=datetime.time(14, 0),
        )
        Task.objects.create(
            board=self.other_board,
            title="Other user's task",
            due_date=self.today,
            due_time=datetime.time(15, 0),
        )

    def post_json(self, url, payload):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_planner_requires_login(self):
        response = self.client.get(reverse("planner:index"))
        self.assertEqual(response.status_code, 302)

    def test_item_feed_only_contains_owned_items(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("planner:items"),
            {
                "start": self.today.isoformat(),
                "end": self.today.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.json()["items"]]
        self.assertIn("Review roadmap", titles)
        self.assertNotIn("Other user's task", titles)

    def test_user_can_create_and_update_personal_event(self):
        self.client.force_login(self.user)
        start = timezone.localtime().replace(second=0, microsecond=0)
        end = start + datetime.timedelta(hours=1)
        payload = {
            "title": "Planning session",
            "description": "Quarterly priorities",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "all_day": False,
        }

        response = self.post_json(reverse("planner:event_create"), payload)
        self.assertEqual(response.status_code, 201)
        event = CalendarEvent.objects.get(id=response.json()["id"])
        self.assertEqual(event.user, self.user)

        payload["title"] = "Updated planning session"
        response = self.post_json(
            reverse("planner:event_update", args=[event.id]),
            payload,
        )
        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.title, "Updated planning session")

    def test_user_cannot_create_event_in_the_past(self):
        self.client.force_login(self.user)
        start = timezone.now() - datetime.timedelta(days=2)
        end = start + datetime.timedelta(hours=1)

        response = self.post_json(
            reverse("planner:event_create"),
            {
                "title": "Past event",
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
                "all_day": False,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(CalendarEvent.objects.filter(title="Past event").exists())

    def test_user_cannot_update_another_users_event(self):
        event = CalendarEvent.objects.create(
            user=self.other_user,
            title="Private appointment",
            start_at=timezone.now(),
            end_at=timezone.now() + datetime.timedelta(hours=1),
        )
        self.client.force_login(self.user)

        response = self.post_json(
            reverse("planner:event_update", args=[event.id]),
            {
                "title": "Changed",
                "start_at": timezone.now().isoformat(),
                "end_at": (timezone.now() + datetime.timedelta(hours=1)).isoformat(),
                "all_day": False,
            },
        )

        self.assertEqual(response.status_code, 404)

    def test_drag_reschedule_updates_owned_task(self):
        self.client.force_login(self.user)
        new_date = self.today + datetime.timedelta(days=3)

        response = self.post_json(
            reverse("planner:reschedule"),
            {
                "source": "task",
                "item_id": self.task.id,
                "date": new_date.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.due_date, new_date)

    def test_drag_reschedule_rejects_past_date(self):
        self.client.force_login(self.user)
        original_date = self.task.due_date

        response = self.post_json(
            reverse("planner:reschedule"),
            {
                "source": "task",
                "item_id": self.task.id,
                "date": (self.today - datetime.timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.due_date, original_date)
