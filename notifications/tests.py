import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boards.models import Board, Task

from .models import Notification
from .services import sync_deadline_notifications


class DeadlineNotificationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "notified-user",
            password="test-pass-123",
        )
        self.other_user = get_user_model().objects.create_user(
            "other-user",
            password="test-pass-123",
        )
        self.board = Board.objects.create(owner=self.user, name="Website")

    def create_task_due_at(self, due_at):
        local_due = timezone.localtime(due_at)
        return Task.objects.create(
            board=self.board,
            title="Review homepage",
            due_date=local_due.date(),
            due_time=local_due.time().replace(second=0, microsecond=0),
        )

    def test_due_soon_notification_is_created_once(self):
        self.create_task_due_at(timezone.now() + datetime.timedelta(hours=2))

        sync_deadline_notifications(self.user)
        sync_deadline_notifications(self.user)

        notifications = Notification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(
            notifications.get().kind,
            Notification.Kind.DUE_SOON,
        )

    def test_overdue_notification_is_created(self):
        self.create_task_due_at(timezone.now() - datetime.timedelta(hours=2))

        sync_deadline_notifications(self.user)

        self.assertEqual(
            Notification.objects.get(user=self.user).kind,
            Notification.Kind.OVERDUE,
        )

    def test_completing_task_clears_unread_deadline_notification(self):
        task = self.create_task_due_at(
            timezone.now() + datetime.timedelta(hours=2)
        )
        sync_deadline_notifications(self.user)

        task.status = Task.Status.DONE
        task.save(update_fields=["status"])
        sync_deadline_notifications(self.user)

        self.assertFalse(
            Notification.objects.filter(
                user=self.user,
                read_at__isnull=True,
            ).exists()
        )

    def test_other_user_cannot_mark_notification_read(self):
        self.create_task_due_at(timezone.now() + datetime.timedelta(hours=2))
        sync_deadline_notifications(self.user)
        notification = Notification.objects.get(user=self.user)

        self.client.force_login(self.other_user)
        response = self.client.post(
            reverse("notifications:read", args=[notification.id])
        )

        self.assertEqual(response.status_code, 404)
