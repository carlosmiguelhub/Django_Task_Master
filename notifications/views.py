from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notification
from .services import sync_deadline_notifications


@login_required
def notification_list(request):
    sync_deadline_notifications(request.user)
    notifications = (
        Notification.objects.filter(user=request.user)
        .select_related("task", "task__board")
        .order_by("-created_at")
    )
    return render(
        request,
        "notifications/notification_list.html",
        {"notifications": notifications},
    )


@require_POST
@login_required
def notification_read(request, notification_id):
    notification = get_object_or_404(
        Notification.objects.select_related("task"),
        id=notification_id,
        user=request.user,
    )
    notification.mark_read()
    return redirect("boards:detail", board_id=notification.task.board_id)


@require_POST
@login_required
def notification_read_all(request):
    Notification.objects.filter(
        user=request.user,
        read_at__isnull=True,
    ).update(read_at=timezone.now())
    return redirect("notifications:list")
