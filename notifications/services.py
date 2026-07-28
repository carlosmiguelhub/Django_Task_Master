import datetime

from django.utils import timezone

from boards.models import Task

from .models import Notification


DEADLINE_KINDS = (Notification.Kind.DUE_SOON, Notification.Kind.OVERDUE)


def task_due_datetime(task):
    if not task.due_date:
        return None

    due_time = task.due_time or datetime.time(23, 59)
    naive_due = datetime.datetime.combine(task.due_date, due_time)
    return timezone.make_aware(naive_due, timezone.get_current_timezone())


def sync_deadline_notifications(user):
    if not user or not user.is_authenticated:
        return

    now = timezone.now()
    due_soon_cutoff = now + datetime.timedelta(hours=24)
    valid_keys = set()

    tasks = (
        Task.objects.filter(
            board__owner=user,
            is_archived=False,
            due_date__isnull=False,
        )
        .exclude(status=Task.Status.DONE)
        .select_related("board")
    )

    for task in tasks:
        due_at = task_due_datetime(task)
        if due_at is None or due_at > due_soon_cutoff:
            continue

        if due_at < now:
            kind = Notification.Kind.OVERDUE
            title = f"{task.title} is overdue"
            message = f"The deadline on {task.board.name} has passed."
        else:
            kind = Notification.Kind.DUE_SOON
            title = f"{task.title} is due soon"
            message = f"Due within 24 hours on {task.board.name}."

        due_signature = due_at.astimezone(timezone.get_current_timezone()).strftime("%Y%m%d%H%M")
        dedupe_key = f"deadline:{user.pk}:{task.pk}:{kind}:{due_signature}"
        valid_keys.add(dedupe_key)

        Notification.objects.update_or_create(
            dedupe_key=dedupe_key,
            defaults={
                "user": user,
                "task": task,
                "kind": kind,
                "title": title,
                "message": message,
            },
        )

    (
        Notification.objects.filter(
            user=user,
            read_at__isnull=True,
            kind__in=DEADLINE_KINDS,
        )
        .exclude(dedupe_key__in=valid_keys)
        .delete()
    )
