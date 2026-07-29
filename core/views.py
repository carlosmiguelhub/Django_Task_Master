import datetime
import hashlib
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from boards.models import Board
from planner.models import CalendarEvent

from .ai import DailyPlanError, answer_workspace_question, build_daily_plan

from boards.models import Task  # ✅ USE THE BOARDS TASK MODEL


def landing(request):
    return render(request, "core/landing_modern.html")


@login_required
def dashboard(request):
    now = timezone.now()
    local_now = timezone.localtime(now)
    today = local_now.date()
    week_end = today + datetime.timedelta(days=7)
    qs = Task.objects.filter(
        board__owner=request.user,
        is_archived=False,
    ).select_related("board")

    counts = qs.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=Task.Status.PENDING)),
        in_progress=Count("id", filter=Q(status=Task.Status.IN_PROGRESS)),
        done=Count("id", filter=Q(status=Task.Status.DONE)),
    )

    active_tasks = list(
        qs.exclude(status=Task.Status.DONE).order_by(
            "due_date", "due_time", "-priority", "created_at"
        )
    )
    overdue_count = 0
    due_today_count = 0
    for task in active_tasks:
        task.is_overdue = _task_is_overdue(task, local_now)
        task.is_due_today = task.due_date == today
        overdue_count += int(task.is_overdue)
        due_today_count += int(task.is_due_today)

    focus_tasks = sorted(
        active_tasks,
        key=lambda task: (
            not task.is_overdue,
            task.due_date or datetime.date.max,
            task.due_time or datetime.time.max,
            {"high": 0, "normal": 1, "low": 2}.get(task.priority, 1),
        ),
    )[:5]

    upcoming_events = list(
        CalendarEvent.objects.filter(
            user=request.user,
            start_at__gte=now,
        ).order_by("start_at")[:4]
    )

    boards = list(
        Board.objects.filter(owner=request.user)
        .annotate(
            task_count=Count(
                "tasks",
                filter=Q(tasks__is_archived=False),
                distinct=True,
            ),
            completed_count=Count(
                "tasks",
                filter=Q(
                    tasks__is_archived=False,
                    tasks__status=Task.Status.DONE,
                ),
                distinct=True,
            ),
        )
        .order_by("-created_at")[:4]
    )
    for board in boards:
        board.progress_percent = (
            round((board.completed_count / board.task_count) * 100)
            if board.task_count
            else 0
        )

    context = {
        "counts": counts,  # ✅ use counts.total / counts.pending / counts.in_progress / counts.done
    }
    context.update(
        {
            "completion_rate": (
                round((counts["done"] / counts["total"]) * 100)
                if counts["total"]
                else 0
            ),
            "overdue_count": overdue_count,
            "due_today_count": due_today_count,
            "focus_tasks": focus_tasks,
            "upcoming_events": upcoming_events,
            "boards": boards,
            "upcoming_week_count": sum(
                bool(task.due_date and today <= task.due_date <= week_end)
                for task in active_tasks
            ),
            "today": today,
        }
    )
    return render(request, "core/dashboard_modern.html", context)


def _task_due_at(task):
    if not task.due_date:
        return None
    due_time = task.due_time or datetime.time(23, 59)
    due_at = datetime.datetime.combine(task.due_date, due_time)
    return timezone.make_aware(due_at, timezone.get_current_timezone())


def _task_is_overdue(task, local_now):
    due_at = _task_due_at(task)
    return bool(due_at and due_at < local_now)


def _daily_plan_workspace(user):
    now = timezone.now()
    local_now = timezone.localtime(now)
    planner_window_start = now - datetime.timedelta(days=7)
    planner_window_end = now + datetime.timedelta(days=45)
    tasks = list(
        Task.objects.filter(
            board__owner=user,
            is_archived=False,
        )
        .exclude(status=Task.Status.DONE)
        .select_related("board")
        .order_by("due_date", "due_time", "-priority")[:30]
    )
    events = (
        CalendarEvent.objects.filter(
            user=user,
            start_at__lt=planner_window_end,
        )
        .filter(
            Q(start_at__gte=planner_window_start)
            | Q(end_at__gte=planner_window_start)
        )
        .order_by("start_at")[:60]
    )

    task_values = []
    for task in tasks:
        due_at = _task_due_at(task)
        task_values.append(
            {
                "id": task.id,
                "title": task.title,
                "description": task.description[:500],
                "board": task.board.name,
                "status": task.status,
                "priority": task.priority,
                "due_at": (
                    timezone.localtime(due_at).isoformat() if due_at else None
                ),
                "estimated_minutes": task.estimated_minutes,
                "scheduled_start": (
                    timezone.localtime(task.scheduled_start).isoformat()
                    if task.scheduled_start
                    else None
                ),
                "scheduled_end": (
                    timezone.localtime(task.scheduled_end).isoformat()
                    if task.scheduled_end
                    else None
                ),
                "overdue": _task_is_overdue(task, local_now),
            }
        )

    planner_events = []
    for event in events:
        event_end = event.end_at or event.start_at
        if event.start_at <= now <= event_end:
            timing = "ongoing"
        elif event_end < now:
            timing = "past"
        else:
            timing = "upcoming"
        planner_events.append(
            {
                "id": event.id,
                "source": "planner_event",
                "title": event.title,
                "description": event.description[:700],
                "event_type": event.event_type,
                "event_type_label": event.get_event_type_display(),
                "location": event.location,
                "meeting_url": event.meeting_url,
                "start_at": timezone.localtime(event.start_at).isoformat(),
                "end_at": (
                    timezone.localtime(event.end_at).isoformat()
                    if event.end_at
                    else None
                ),
                "all_day": event.all_day,
                "timing": timing,
            }
        )

    return {
        "current_time": local_now.isoformat(),
        "timezone": settings.TIME_ZONE,
        "tasks": task_values,
        "planner": {
            "window_start": timezone.localtime(planner_window_start).isoformat(),
            "window_end": timezone.localtime(planner_window_end).isoformat(),
            "events": planner_events,
        },
    }


@require_POST
@login_required
def daily_plan(request):
    try:
        request_data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request."}, status=400)

    workspace = _daily_plan_workspace(request.user)
    if not workspace["tasks"] and not workspace["planner"]["events"]:
        return JsonResponse(
            {
                "plan": {
                    "headline": "Your workspace is clear",
                    "summary": (
                        "There are no unfinished tasks or Planner events to organize "
                        "right now. Use the open space for planning, review, or recovery."
                    ),
                    "priorities": [],
                    "risks": [],
                    "schedule": [],
                    "encouragement": "You are caught up—nice work.",
                },
                "cached": False,
            }
        )

    cache_key = f"daily-plan:v2:{request.user.pk}:{timezone.localdate().isoformat()}"
    if not request_data.get("refresh"):
        cached_plan = cache.get(cache_key)
        if cached_plan:
            return JsonResponse({"plan": cached_plan, "cached": True})

    safety_identifier = hashlib.sha256(
        f"{settings.SECRET_KEY}:daily-plan:{request.user.pk}".encode()
    ).hexdigest()

    try:
        plan = build_daily_plan(workspace, safety_identifier)
    except DailyPlanError as exc:
        return JsonResponse({"error": str(exc)}, status=503)

    task_urls = {
        task["id"]: reverse("boards:task_update", args=[task["id"]])
        for task in workspace["tasks"]
    }
    for priority in plan["priorities"]:
        priority["url"] = task_urls[priority["task_id"]]

    cache.set(cache_key, plan, 600)
    return JsonResponse({"plan": plan, "cached": False})


@require_POST
@login_required
def daily_plan_chat(request):
    try:
        request_data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request."}, status=400)

    if not isinstance(request_data, dict):
        return JsonResponse({"error": "Invalid request."}, status=400)
    question = request_data.get("question", "")
    if not isinstance(question, str):
        return JsonResponse({"error": "Please enter a valid question."}, status=400)
    question = " ".join(question.split())
    if not question:
        return JsonResponse({"error": "Ask a question about your workspace."}, status=400)
    if len(question) > 600:
        return JsonResponse(
            {"error": "Keep your question under 600 characters."},
            status=400,
        )

    rate_key = (
        f"daily-plan-chat-rate:v1:{request.user.pk}:"
        f"{int(timezone.now().timestamp() // 60)}"
    )
    if cache.add(rate_key, 1, timeout=70):
        request_count = 1
    else:
        try:
            request_count = cache.incr(rate_key)
        except ValueError:
            cache.set(rate_key, 1, timeout=70)
            request_count = 1
    if request_count > 10:
        return JsonResponse(
            {"error": "You’ve reached the chat limit. Try again in a minute."},
            status=429,
        )

    workspace = _daily_plan_workspace(request.user)
    history_key = f"daily-plan-chat:v1:{request.user.pk}"
    history = cache.get(history_key, [])
    if not isinstance(history, list):
        history = []

    safety_identifier = hashlib.sha256(
        f"{settings.SECRET_KEY}:daily-plan-chat:{request.user.pk}".encode()
    ).hexdigest()
    try:
        result = answer_workspace_question(
            workspace,
            history[:],
            question,
            safety_identifier,
        )
    except DailyPlanError as exc:
        return JsonResponse({"error": str(exc)}, status=503)

    history.extend(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": result["answer"]},
        ]
    )
    cache.set(history_key, history[-20:], 7200)
    return JsonResponse(result)
