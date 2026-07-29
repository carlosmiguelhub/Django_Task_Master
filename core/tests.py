import datetime
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from boards.models import Board, Task
from planner.models import CalendarEvent


class LandingPageTests(TestCase):
    def test_modern_landing_page_does_not_render_app_navbar(self):
        response = self.client.get(reverse("core:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="tm-nav"')
        self.assertContains(response, "tm-public-theme-control")
        self.assertNotContains(response, "/static/images/task-master-logo.png")
        self.assertContains(response, "Turn busy work into")


class DashboardTests(TestCase):
    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            "dashboard-owner",
            password="test-pass-123",
        )
        self.other_user = user_model.objects.create_user(
            "other-owner",
            password="test-pass-123",
        )
        self.board = Board.objects.create(owner=self.user, name="Coursework")
        self.task = Task.objects.create(
            board=self.board,
            title="Finish dashboard report",
            priority=Task.Priority.HIGH,
            due_date=timezone.localdate() + datetime.timedelta(days=1),
            due_time=datetime.time(17, 0),
        )
        other_board = Board.objects.create(owner=self.other_user, name="Private")
        Task.objects.create(
            board=other_board,
            title="Other user's private task",
            due_date=timezone.localdate() + datetime.timedelta(days=1),
        )
        CalendarEvent.objects.create(
            user=self.user,
            title="Project review",
            description="Review the dashboard metrics and prepare feedback.",
            event_type=CalendarEvent.EventType.MEETING,
            location="Conference Room A",
            meeting_url="https://meet.example.com/project-review",
            start_at=timezone.now() + datetime.timedelta(hours=2),
            end_at=timezone.now() + datetime.timedelta(hours=3),
        )
        CalendarEvent.objects.create(
            user=self.other_user,
            title="Other user's private appointment",
            description="This must never enter another user's AI context.",
            start_at=timezone.now() + datetime.timedelta(hours=1),
            end_at=timezone.now() + datetime.timedelta(hours=2),
        )
        CalendarEvent.objects.create(
            user=self.user,
            title="End-of-month presentation",
            description="Prepare the final project presentation.",
            start_at=timezone.now() + datetime.timedelta(days=30),
            end_at=timezone.now() + datetime.timedelta(days=30, hours=1),
        )

    def test_dashboard_shows_workspace_details_without_cross_user_data(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("app:dashboard"))

        self.assertContains(response, "Today’s focus")
        self.assertContains(response, "Finish dashboard report")
        self.assertContains(response, "Project review")
        self.assertContains(response, "Board momentum")
        self.assertContains(response, "aiDailyPlanLauncher")
        self.assertContains(response, "Generate Daily Plan")
        self.assertContains(response, "Chat with AI")
        self.assertContains(response, "Talk to AI")
        self.assertContains(response, reverse("app:daily_plan_chat"))
        self.assertContains(
            response,
            f'href="{reverse("boards:detail", args=[self.board.id])}" class="tm-focus-item"',
            html=False,
        )
        self.assertNotContains(
            response,
            f'href="{reverse("boards:task_update", args=[self.task.id])}" class="tm-focus-item"',
            html=False,
        )
        self.assertNotContains(response, "Other user&#x27;s private task")

    @override_settings(OPENAI_API_KEY="")
    def test_daily_plan_explains_missing_api_key(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("app:daily_plan"),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.json()["error"])

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("core.views.build_daily_plan")
    def test_daily_plan_returns_validated_task_links(self, build_plan):
        build_plan.return_value = {
            "headline": "Start with the report",
            "summary": "Protect the nearest deadline.",
            "priorities": [
                {
                    "task_id": self.task.id,
                    "title": self.task.title,
                    "reason": "It is due soon.",
                    "action": "Draft the first section.",
                }
            ],
            "risks": ["The deadline is close."],
            "schedule": [
                {
                    "time": "2:00 PM",
                    "task": self.task.title,
                    "duration": "60 min",
                }
            ],
            "encouragement": "One focused block is enough to build momentum.",
        }
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("app:daily_plan"),
            data=json.dumps({"refresh": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        priority = response.json()["plan"]["priorities"][0]
        self.assertEqual(
            priority["url"],
            reverse("boards:task_update", args=[self.task.id]),
        )
        workspace = build_plan.call_args.args[0]
        planner_event = workspace["planner"]["events"][0]
        self.assertEqual(planner_event["title"], "Project review")
        self.assertIn("dashboard metrics", planner_event["description"])
        self.assertEqual(planner_event["source"], "planner_event")
        self.assertEqual(planner_event["event_type"], "meeting")
        self.assertEqual(planner_event["location"], "Conference Room A")
        self.assertEqual(
            planner_event["meeting_url"],
            "https://meet.example.com/project-review",
        )

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("core.views.answer_workspace_question")
    def test_workspace_chat_only_receives_signed_in_users_data(self, answer_question):
        answer_question.return_value = {
            "answer": "Start with the dashboard report—it is due tomorrow.",
            "suggestions": ["How long should I focus on it?"],
        }
        self.client.force_login(self.user)
        history_key = f"daily-plan-chat:v1:{self.user.pk}"
        cache.set(
            history_key,
            [
                {"role": "user", "content": f"Earlier question {index}"}
                for index in range(18)
            ],
            300,
        )

        response = self.client.post(
            reverse("app:daily_plan_chat"),
            data=json.dumps({"question": "What should I do first?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggestions"], ["How long should I focus on it?"])
        workspace = answer_question.call_args.args[0]
        workspace_titles = [task["title"] for task in workspace["tasks"]]
        self.assertIn("Finish dashboard report", workspace_titles)
        self.assertNotIn("Other user's private task", workspace_titles)
        planner_titles = [event["title"] for event in workspace["planner"]["events"]]
        self.assertIn("Project review", planner_titles)
        self.assertIn("End-of-month presentation", planner_titles)
        self.assertNotIn("Other user's private appointment", planner_titles)
        self.assertEqual(len(answer_question.call_args.args[1]), 18)
        self.assertEqual(len(cache.get(history_key)), 20)

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("core.views.answer_workspace_question")
    def test_workspace_chat_rejects_oversized_questions(self, answer_question):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("app:daily_plan_chat"),
            data=json.dumps({"question": "x" * 601}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        answer_question.assert_not_called()

    def test_workspace_chat_requires_login(self):
        response = self.client.post(
            reverse("app:daily_plan_chat"),
            data=json.dumps({"question": "What is due?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 302)
