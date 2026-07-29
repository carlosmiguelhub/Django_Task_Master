import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from boards.models import Board, Task

from .models import CalendarEvent


class PlannerTests(TransactionTestCase):
    # Event creation now runs inside a MySQL stored procedure that owns its
    # COMMIT/ROLLBACK boundary, so these integration tests cannot use the outer
    # atomic transaction automatically created by Django's TestCase.
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
            "event_type": CalendarEvent.EventType.MEETING,
            "location": "Conference Room A",
            "meeting_url": "https://meet.example.com/planning",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "all_day": False,
        }

        response = self.post_json(reverse("planner:event_create"), payload)
        self.assertEqual(response.status_code, 201)
        event = CalendarEvent.objects.get(id=response.json()["id"])
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.event_type, CalendarEvent.EventType.MEETING)
        self.assertEqual(event.location, "Conference Room A")
        self.assertEqual(event.meeting_url, "https://meet.example.com/planning")
        feed_response = self.client.get(
            reverse("planner:items"),
            {
                "start": timezone.localtime(start).date().isoformat(),
                "end": timezone.localtime(end).date().isoformat(),
            },
        )
        event_item = next(
            item
            for item in feed_response.json()["items"]
            if item["id"] == f"event-{event.id}"
        )
        self.assertEqual(event_item["event_type_label"], "Meeting")
        self.assertEqual(event_item["location"], "Conference Room A")
        self.assertEqual(
            event_item["meeting_url"],
            "https://meet.example.com/planning",
        )

        payload["title"] = "Updated planning session"
        payload["location"] = "Online"
        response = self.post_json(
            reverse("planner:event_update", args=[event.id]),
            payload,
        )
        self.assertEqual(response.status_code, 200)
        event.refresh_from_db()
        self.assertEqual(event.title, "Updated planning session")
        self.assertEqual(event.location, "Online")

    def test_event_rejects_unsafe_meeting_link(self):
        self.client.force_login(self.user)
        start = timezone.now() + datetime.timedelta(days=1)

        response = self.post_json(
            reverse("planner:event_create"),
            {
                "title": "Suspicious meeting",
                "meeting_url": "javascript:alert(1)",
                "start_at": start.isoformat(),
                "end_at": (start + datetime.timedelta(hours=1)).isoformat(),
                "all_day": False,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("valid http or https", response.json()["error"])
        self.assertFalse(
            CalendarEvent.objects.filter(title="Suspicious meeting").exists()
        )

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

    def test_all_day_event_blocks_other_events_on_that_date(self):
        self.client.force_login(self.user)
        target = self.today + datetime.timedelta(days=1)
        start = timezone.make_aware(
            datetime.datetime.combine(target, datetime.time(0, 0)),
            timezone.get_current_timezone(),
        )
        end = timezone.make_aware(
            datetime.datetime.combine(target, datetime.time(23, 59)),
            timezone.get_current_timezone(),
        )
        all_day_response = self.post_json(
            reverse("planner:event_create"),
            {
                "title": "Conference day",
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
                "all_day": True,
            },
        )
        self.assertEqual(all_day_response.status_code, 201)

        timed_response = self.post_json(
            reverse("planner:event_create"),
            {
                "title": "Overlapping meeting",
                "start_at": (start + datetime.timedelta(hours=10)).isoformat(),
                "end_at": (start + datetime.timedelta(hours=11)).isoformat(),
                "all_day": False,
            },
        )

        self.assertEqual(timed_response.status_code, 409)
        self.assertIn("all-day", timed_response.json()["error"])

    def test_all_day_event_cannot_replace_existing_timed_event(self):
        self.client.force_login(self.user)
        target = self.today + datetime.timedelta(days=2)
        start = timezone.make_aware(
            datetime.datetime.combine(target, datetime.time(10, 0)),
            timezone.get_current_timezone(),
        )
        CalendarEvent.objects.create(
            user=self.user,
            title="Existing meeting",
            start_at=start,
            end_at=start + datetime.timedelta(hours=1),
        )

        response = self.post_json(
            reverse("planner:event_create"),
            {
                "title": "Reserved day",
                "start_at": start.replace(hour=0).isoformat(),
                "end_at": start.replace(hour=23, minute=59).isoformat(),
                "all_day": True,
            },
        )

        self.assertEqual(response.status_code, 409)

    def test_planner_page_contains_day_details_dialog(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("planner:index"))

        self.assertContains(response, 'id="plannerDayDialog"')
        self.assertContains(response, 'id="plannerDayDetails"')
        self.assertContains(response, 'id="plannerEventType"')
        self.assertContains(response, 'id="plannerEventLocation"')
        self.assertContains(response, 'id="plannerEventMeetingUrl"')
        self.assertContains(response, "Add event")

    def test_drag_schedules_owned_task_without_changing_deadline(self):
        self.client.force_login(self.user)
        new_date = self.today + datetime.timedelta(days=3)
        original_deadline = self.task.due_date

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
        self.assertEqual(self.task.due_date, original_deadline)
        self.assertEqual(timezone.localtime(self.task.scheduled_start).date(), new_date)
        self.assertEqual(
            self.task.scheduled_end - self.task.scheduled_start,
            datetime.timedelta(minutes=60),
        )

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
        self.assertIsNone(self.task.scheduled_start)

    def test_feed_separates_deadline_from_scheduled_work_block(self):
        start = timezone.make_aware(
            datetime.datetime.combine(self.today, datetime.time(9, 0)),
            timezone.get_current_timezone(),
        )
        self.task.scheduled_start = start
        self.task.scheduled_end = start + datetime.timedelta(minutes=60)
        self.task.save(update_fields=["scheduled_start", "scheduled_end"])
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("planner:items"),
            {"start": self.today.isoformat(), "end": self.today.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        task_items = [
            item for item in response.json()["items"]
            if item["source"] == "task"
        ]
        self.assertEqual(
            {item["kind"] for item in task_items},
            {"deadline", "work_block"},
        )

    def test_owner_can_remove_work_block_without_deleting_task_or_deadline(self):
        start = timezone.now() + datetime.timedelta(days=1)
        self.task.scheduled_start = start
        self.task.scheduled_end = start + datetime.timedelta(minutes=60)
        original_deadline = self.task.due_date
        self.task.save(update_fields=["scheduled_start", "scheduled_end"])
        self.client.force_login(self.user)

        response = self.post_json(
            reverse("planner:task_unschedule", args=[self.task.id]),
            {},
        )

        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertIsNone(self.task.scheduled_start)
        self.assertIsNone(self.task.scheduled_end)
        self.assertEqual(self.task.due_date, original_deadline)
        self.assertTrue(Task.objects.filter(id=self.task.id).exists())

    def test_user_cannot_remove_another_users_work_block(self):
        other_task = Task.objects.get(board=self.other_board)
        self.client.force_login(self.user)

        response = self.post_json(
            reverse("planner:task_unschedule", args=[other_task.id]),
            {},
        )

        self.assertEqual(response.status_code, 404)
