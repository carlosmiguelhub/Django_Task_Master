from django.db import OperationalError, ProgrammingError

from .models import Notification
from .services import sync_deadline_notifications


def notification_summary(request):
    if not request.user.is_authenticated:
        return {}

    try:
        sync_deadline_notifications(request.user)
        unread = Notification.objects.filter(user=request.user, read_at__isnull=True)
        return {
            "notification_unread_count": unread.count(),
            "recent_notifications": unread.select_related("task", "task__board")[:5],
        }
    except (OperationalError, ProgrammingError):
        # Keeps pages available during the brief window before migrations run.
        return {
            "notification_unread_count": 0,
            "recent_notifications": [],
        }
