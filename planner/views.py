import datetime
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from boards.models import Board, Task
from core.stored_procedures import (
    StoredProcedureError,
    create_calendar_event_transaction,
)

from .models import CalendarEvent


def _json_body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON request.") from exc


def _aware_datetime(value, field_name):
    parsed = parse_datetime(value or "")
    if parsed is None:
        raise ValueError(f"A valid {field_name} is required.")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _event_values(data):
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("Event title is required.")

    event_type = (data.get("event_type") or CalendarEvent.EventType.MEETING).strip()
    if event_type not in CalendarEvent.EventType.values:
        raise ValueError("Choose a valid event type.")

    location = (data.get("location") or "").strip()
    if len(location) > 240:
        raise ValueError("Location must be 240 characters or fewer.")

    meeting_url = (data.get("meeting_url") or "").strip()
    if meeting_url:
        try:
            URLValidator(schemes=["http", "https"])(meeting_url)
        except ValidationError as exc:
            raise ValueError("Enter a valid http or https meeting link.") from exc

    start_at = _aware_datetime(data.get("start_at"), "start time")
    end_at = _aware_datetime(data.get("end_at"), "end time")
    if end_at <= start_at:
        raise ValueError("End time must be after the start time.")

    all_day = bool(data.get("all_day"))
    if all_day:
        local_start = timezone.localtime(start_at)
        local_end = timezone.localtime(end_at)
        start_at = timezone.make_aware(
            datetime.datetime.combine(local_start.date(), datetime.time.min),
            timezone.get_current_timezone(),
        )
        end_at = timezone.make_aware(
            datetime.datetime.combine(local_end.date(), datetime.time.max),
            timezone.get_current_timezone(),
        )

    return {
        "title": title,
        "event_type": event_type,
        "location": location,
        "meeting_url": meeting_url,
        "description": (data.get("description") or "").strip(),
        "start_at": start_at,
        "end_at": end_at,
        "all_day": all_day,
    }


def _event_conflicts_with_all_day(user, values, exclude_event_id=None):
    overlapping = CalendarEvent.objects.filter(
        user=user,
        start_at__lt=values["end_at"],
        end_at__gt=values["start_at"],
    )
    if exclude_event_id:
        overlapping = overlapping.exclude(id=exclude_event_id)
    if values["all_day"]:
        return overlapping.exists()
    return overlapping.filter(all_day=True).exists()


def _is_past_date(value):
    return timezone.localtime(value).date() < timezone.localdate()


@ensure_csrf_cookie
@login_required
def planner_view(request):
    boards = Board.objects.filter(owner=request.user).order_by("name")
    return render(request, "planner/planner.html", {"boards": boards})


@require_GET
@login_required
def planner_items(request):
    today = timezone.localdate()
    start_date = parse_date(request.GET.get("start", "")) or today.replace(day=1)
    end_date = parse_date(request.GET.get("end", "")) or (
        start_date + datetime.timedelta(days=42)
    )
    if end_date < start_date:
        return JsonResponse({"error": "Invalid date range."}, status=400)

    range_start = timezone.make_aware(
        datetime.datetime.combine(start_date, datetime.time.min),
        timezone.get_current_timezone(),
    )
    range_end = timezone.make_aware(
        datetime.datetime.combine(
            end_date + datetime.timedelta(days=1),
            datetime.time.min,
        ),
        timezone.get_current_timezone(),
    )
    tasks = (
        Task.objects.filter(
            Q(due_date__range=(start_date, end_date))
            | Q(
                scheduled_start__lt=range_end,
                scheduled_end__gte=range_start,
            ),
            board__owner=request.user,
            is_archived=False,
        )
        .select_related("board")
        .distinct()
        .order_by("due_date", "due_time", "title")
    )
    calendar_events = (
        CalendarEvent.objects.filter(
            user=request.user,
            start_at__lt=range_end,
        )
        .filter(Q(end_at__isnull=True) | Q(end_at__gte=range_start))
        .order_by("start_at")
    )

    items = []
    now = timezone.now()
    for task in tasks:
        common = {
            "item_id": task.id,
            "source": "task",
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "board_id": task.board_id,
            "board": task.board.name,
            "url": reverse("boards:task_update", args=[task.id]),
            "estimated_minutes": task.estimated_minutes,
        }
        if task.due_date and start_date <= task.due_date <= end_date:
            if task.due_time:
                task_start = timezone.make_aware(
                    datetime.datetime.combine(task.due_date, task.due_time),
                    timezone.get_current_timezone(),
                )
                start_value = timezone.localtime(task_start).isoformat()
                all_day = False
                overdue = task.status != Task.Status.DONE and task_start < now
            else:
                start_value = task.due_date.isoformat()
                all_day = True
                overdue = task.status != Task.Status.DONE and task.due_date < today
            items.append(
                {
                    **common,
                    "id": f"task-deadline-{task.id}",
                    "kind": "deadline",
                    "start": start_value,
                    "end": None,
                    "all_day": all_day,
                    "overdue": overdue,
                }
            )

        if task.scheduled_start and task.scheduled_end:
            items.append(
                {
                    **common,
                    "id": f"task-block-{task.id}",
                    "kind": "work_block",
                    "start": timezone.localtime(task.scheduled_start).isoformat(),
                    "end": timezone.localtime(task.scheduled_end).isoformat(),
                    "all_day": False,
                    "overdue": False,
                }
            )

    for event in calendar_events:
        items.append(
            {
                "id": f"event-{event.id}",
                "item_id": event.id,
                "source": "event",
                "kind": "event",
                "title": event.title,
                "description": event.description,
                "event_type": event.event_type,
                "event_type_label": event.get_event_type_display(),
                "location": event.location,
                "meeting_url": event.meeting_url,
                "start": timezone.localtime(event.start_at).isoformat(),
                "end": (
                    timezone.localtime(event.end_at).isoformat()
                    if event.end_at
                    else None
                ),
                "all_day": event.all_day,
                "status": "event",
                "priority": "",
                "board_id": None,
                "board": "Personal event",
                "overdue": False,
                "url": "",
            }
        )

    return JsonResponse({"items": items})


@require_POST
@login_required
def event_create(request):
    try:
        values = _event_values(_json_body(request))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        # Stored Procedure Transaction 3:
        # MySQL serializes the conflict check and event insert for this user.
        event_id = create_calendar_event_transaction(
            user_id=request.user.id,
            values=values,
        )
    except StoredProcedureError as exc:
        message = str(exc)
        status = 409 if "conflict" in message.lower() else 400
        return JsonResponse({"error": message}, status=status)

    return JsonResponse({"id": event_id, "message": "Event created."}, status=201)


@require_POST
@login_required
def event_update(request, event_id):
    event = get_object_or_404(CalendarEvent, id=event_id, user=request.user)
    try:
        values = _event_values(_json_body(request))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    original_date = timezone.localtime(event.start_at).date()
    proposed_date = timezone.localtime(values["start_at"]).date()
    if proposed_date < timezone.localdate() and proposed_date != original_date:
        return JsonResponse(
            {"error": "Events cannot be moved to a past date."},
            status=400,
        )
    if _event_conflicts_with_all_day(
        request.user,
        values,
        exclude_event_id=event.id,
    ):
        return JsonResponse(
            {
                "error": (
                    "This date is reserved by an all-day event, or already contains "
                    "an event that prevents creating an all-day plan."
                )
            },
            status=409,
        )

    for field, value in values.items():
        setattr(event, field, value)
    event.save()
    return JsonResponse({"message": "Event updated."})


@require_POST
@login_required
def event_delete(request, event_id):
    event = get_object_or_404(CalendarEvent, id=event_id, user=request.user)
    event.delete()
    return JsonResponse({"message": "Event deleted."})


@require_POST
@login_required
def item_reschedule(request):
    try:
        data = _json_body(request)
        new_date = parse_date(data.get("date", ""))
        if new_date is None:
            raise ValueError("A valid target date is required.")
        if new_date < timezone.localdate():
            raise ValueError("Items cannot be rescheduled to a past date.")
        item_id = int(data.get("item_id"))
    except (TypeError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if data.get("source") == "task":
        task = get_object_or_404(
            Task,
            id=item_id,
            board__owner=request.user,
            is_archived=False,
        )
        local_start = (
            timezone.localtime(task.scheduled_start)
            if task.scheduled_start
            else timezone.make_aware(
                datetime.datetime.combine(new_date, datetime.time(9, 0)),
                timezone.get_current_timezone(),
            )
        )
        scheduled_start = timezone.make_aware(
            datetime.datetime.combine(new_date, local_start.time()),
            timezone.get_current_timezone(),
        )
        duration = datetime.timedelta(minutes=task.estimated_minutes or 60)
        task.scheduled_start = scheduled_start
        task.scheduled_end = scheduled_start + duration
        task.save(update_fields=["scheduled_start", "scheduled_end"])
    elif data.get("source") == "event":
        event = get_object_or_404(CalendarEvent, id=item_id, user=request.user)
        local_start = timezone.localtime(event.start_at)
        date_delta = new_date - local_start.date()
        event.start_at += date_delta
        if event.end_at:
            event.end_at += date_delta
        event.save(update_fields=["start_at", "end_at", "updated_at"])
    else:
        return JsonResponse({"error": "Unknown planner item."}, status=400)

    return JsonResponse({"message": "Schedule updated."})


@require_POST
@login_required
def task_unschedule(request, task_id):
    task = get_object_or_404(
        Task,
        id=task_id,
        board__owner=request.user,
        is_archived=False,
    )
    task.scheduled_start = None
    task.scheduled_end = None
    task.save(update_fields=["scheduled_start", "scheduled_end"])
    return JsonResponse(
        {"message": "Work block removed. The task and its deadline were kept."}
    )
