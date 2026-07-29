import datetime

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone

from boards.models import Board, Task
from notifications.models import Notification
from planner.models import CalendarEvent

from .stored_procedures import (
    StoredProcedureError,
    complete_task_transaction,
    create_calendar_event_transaction,
    create_task_transaction,
)


class StoredProcedureTransactionTests(TransactionTestCase):
    """
    Integration tests for the three required MySQL transactions.

    TransactionTestCase is intentional: each stored procedure controls its own
    START TRANSACTION / COMMIT / ROLLBACK boundary inside MySQL.
    """

    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            "procedure-owner",
            password="test-pass-123",
        )
        self.other_user = user_model.objects.create_user(
            "procedure-other",
            password="test-pass-123",
        )
        self.board = Board.objects.create(owner=self.user, name="Procedure Demo")

    def test_transaction_1_creates_task_and_rolls_back_invalid_owner(self):
        values = {
            "title": "Prepare final presentation",
            "description": "Explain the stored procedures.",
            "priority": Task.Priority.HIGH,
            "estimated_minutes": 90,
            "due_date": timezone.localdate() + datetime.timedelta(days=2),
            "due_time": datetime.time(15, 30),
        }

        task_id = create_task_transaction(
            user_id=self.user.id,
            board_id=self.board.id,
            values=values,
        )

        task = Task.objects.get(id=task_id)
        self.assertEqual(task.board, self.board)
        self.assertEqual(task.status, Task.Status.PENDING)
        self.assertEqual(task.estimated_minutes, 90)

        task_count = Task.objects.count()
        with self.assertRaisesRegex(StoredProcedureError, "do not own"):
            create_task_transaction(
                user_id=self.other_user.id,
                board_id=self.board.id,
                values=values,
            )
        self.assertEqual(Task.objects.count(), task_count)

    def test_transaction_2_completes_task_and_cleans_notification(self):
        task = Task.objects.create(
            board=self.board,
            title="Finish overdue report",
            status=Task.Status.IN_PROGRESS,
            due_date=timezone.localdate() - datetime.timedelta(days=1),
            due_time=datetime.time(9, 0),
        )
        Notification.objects.create(
            user=self.user,
            task=task,
            kind=Notification.Kind.OVERDUE,
            title="Report is overdue",
            message="The deadline has passed.",
            dedupe_key=f"procedure-test:{task.id}",
        )

        completed_late = complete_task_transaction(
            user_id=self.user.id,
            task_id=task.id,
        )

        task.refresh_from_db()
        self.assertTrue(completed_late)
        self.assertEqual(task.status, Task.Status.DONE)
        self.assertIsNotNone(task.completed_at)
        self.assertTrue(task.completed_late)
        self.assertFalse(Notification.objects.filter(task=task).exists())

    def test_transaction_2_rolls_back_when_task_is_not_in_progress(self):
        task = Task.objects.create(
            board=self.board,
            title="Pending task",
            status=Task.Status.PENDING,
            due_date=timezone.localdate() + datetime.timedelta(days=1),
            due_time=datetime.time(12, 0),
        )
        notification = Notification.objects.create(
            user=self.user,
            task=task,
            kind=Notification.Kind.DUE_SOON,
            title="Task is due soon",
            message="Due within 24 hours.",
            dedupe_key=f"procedure-rollback:{task.id}",
        )

        with self.assertRaisesRegex(StoredProcedureError, "in-progress"):
            complete_task_transaction(
                user_id=self.user.id,
                task_id=task.id,
            )

        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.PENDING)
        self.assertTrue(Notification.objects.filter(id=notification.id).exists())

    def test_transaction_3_creates_event_and_rolls_back_conflict(self):
        target_date = timezone.localdate() + datetime.timedelta(days=3)
        start_at = timezone.make_aware(
            datetime.datetime.combine(target_date, datetime.time.min),
            timezone.get_current_timezone(),
        )
        end_at = timezone.make_aware(
            datetime.datetime.combine(target_date, datetime.time.max),
            timezone.get_current_timezone(),
        )
        all_day_values = {
            "title": "Final project day",
            "description": "Reserved for the presentation.",
            "event_type": CalendarEvent.EventType.CLASS,
            "location": "Main laboratory",
            "meeting_url": "",
            "start_at": start_at,
            "end_at": end_at,
            "all_day": True,
        }

        event_id = create_calendar_event_transaction(
            user_id=self.user.id,
            values=all_day_values,
        )
        self.assertTrue(CalendarEvent.objects.filter(id=event_id).exists())

        conflicting_values = {
            **all_day_values,
            "title": "Conflicting meeting",
            "event_type": CalendarEvent.EventType.MEETING,
            "start_at": start_at + datetime.timedelta(hours=10),
            "end_at": start_at + datetime.timedelta(hours=11),
            "all_day": False,
        }
        event_count = CalendarEvent.objects.count()

        with self.assertRaisesRegex(StoredProcedureError, "all-day"):
            create_calendar_event_transaction(
                user_id=self.user.id,
                values=conflicting_values,
            )

        self.assertEqual(CalendarEvent.objects.count(), event_count)
