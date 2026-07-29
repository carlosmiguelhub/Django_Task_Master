from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
import datetime

from .forms import BoardCreateForm, TaskCreateForm, TaskUpdateForm
from .models import Board, Task
from django.contrib import messages

from core.stored_procedures import (
    StoredProcedureError,
    complete_task_transaction,
    create_task_transaction,
)


def _decorate_task(task, now):
    """Attach presentation-only deadline data without changing the database."""
    due_dt = None
    if task.due_date:
        due_time = task.due_time or datetime.time(23, 59)
        due_dt = datetime.datetime.combine(task.due_date, due_time)
        due_dt = timezone.make_aware(due_dt, timezone.get_current_timezone())

    task.due_at = due_dt
    task.is_overdue = bool(
        due_dt and task.status != Task.Status.DONE and due_dt < now
    )

    if task.status == Task.Status.DONE:
        task.timeline_percent = 100
    elif due_dt and due_dt > task.created_at:
        elapsed = (now - task.created_at).total_seconds()
        duration = (due_dt - task.created_at).total_seconds()
        task.timeline_percent = max(3, min(100, round((elapsed / duration) * 100)))
    else:
        task.timeline_percent = 100 if due_dt else 0

    return task

@login_required
def board_list(request):
    # Create Board (modal submits here)
    if request.method == "POST":
        form = BoardCreateForm(request.POST)
        if form.is_valid():
            board = form.save(commit=False)
            board.owner = request.user
            board.save()
            return redirect("boards:list")
    else:
        form = BoardCreateForm()

    boards = (
        Board.objects.filter(owner=request.user)
        .annotate(
            task_count=Count(
                "tasks", filter=Q(tasks__is_archived=False), distinct=True
            ),
            completed_count=Count(
                "tasks",
                filter=Q(tasks__is_archived=False, tasks__status=Task.Status.DONE),
                distinct=True,
            ),
            active_count=Count(
                "tasks",
                filter=Q(tasks__is_archived=False)
                & ~Q(tasks__status=Task.Status.DONE),
                distinct=True,
            ),
        )
        .order_by("-created_at")
    )

    boards = list(boards)
    for board in boards:
        board.progress_percent = (
            round((board.completed_count / board.task_count) * 100)
            if board.task_count
            else 0
        )

    return render(
        request,
        "boards/board_list_modern.html",
        {
            "boards": boards,
            "form": form,
            "board_count": len(boards),
            "active_task_count": sum(board.active_count for board in boards),
            "completed_task_count": sum(board.completed_count for board in boards),
        },
    )


@login_required
def board_detail(request, board_id):
    board = get_object_or_404(Board, id=board_id, owner=request.user)

    # Add Task (modal submits here)
    if request.method == "POST":
        task_form = TaskCreateForm(request.POST)
        if task_form.is_valid():
            try:
                # Stored Procedure Transaction 1:
                # MySQL validates ownership and inserts the pending task.
                create_task_transaction(
                    user_id=request.user.id,
                    board_id=board.id,
                    values=task_form.cleaned_data,
                )
            except StoredProcedureError as exc:
                task_form.add_error(None, str(exc))
            else:
                return redirect("boards:detail", board_id=board.id)
    else:
        task_form = TaskCreateForm()

    # ✅ If your runtime uses "tasks", these should also be "board.tasks"
    now = timezone.now()
    active_tasks = list(
        board.tasks.filter(is_archived=False).order_by(
            "due_date", "due_time", "-created_at"
        )
    )
    for task in active_tasks:
        _decorate_task(task, now)

    pending = [task for task in active_tasks if task.status == Task.Status.PENDING]
    progress = [
        task for task in active_tasks if task.status == Task.Status.IN_PROGRESS
    ]
    done = [task for task in active_tasks if task.status == Task.Status.DONE]

    return render(
        request,
        "boards/board_detail_modern.html",
        {
            "board": board,
            "pending": pending,
            "progress": progress,
            "done": done,
            "form": task_form,
            "total_count": len(active_tasks),
            "completed_percent": (
                round((len(done) / len(active_tasks)) * 100)
                if active_tasks
                else 0
            ),
        },
    )


@require_POST
@login_required
def task_start(request, task_id):
    task = get_object_or_404(Task, id=task_id, board__owner=request.user)

    if task.status == Task.Status.PENDING:
        task.status = Task.Status.IN_PROGRESS
        task.completed_at = None
        task.completed_late = False
        task.save(update_fields=["status", "completed_at", "completed_late"])

    return redirect("boards:detail", board_id=task.board_id)


@require_POST
@login_required
def task_complete(request, task_id):
    task = get_object_or_404(Task, id=task_id, board__owner=request.user)

    if task.status == Task.Status.IN_PROGRESS:
        try:
            # Stored Procedure Transaction 2:
            # completion metadata and unread notification cleanup commit together.
            complete_task_transaction(
                user_id=request.user.id,
                task_id=task.id,
            )
        except StoredProcedureError as exc:
            messages.error(request, str(exc))

    return redirect("boards:detail", board_id=task.board_id)


@login_required
def task_update(request, task_id):
    task = get_object_or_404(
        Task,
        id=task_id,
        board__owner=request.user,
        is_archived=False,
    )

    if request.method == "POST":
        form = TaskUpdateForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(request, "Task updated.")
            return redirect("boards:detail", board_id=task.board_id)
    else:
        form = TaskUpdateForm(instance=task)

    return render(
        request,
        "boards/task_form.html",
        {"form": form, "task": task, "board": task.board},
    )


@require_POST
@login_required
def task_delete_active(request, task_id):
    task = get_object_or_404(
        Task,
        id=task_id,
        board__owner=request.user,
        is_archived=False,
    )
    board_id = task.board_id
    task.delete()
    messages.success(request, "Task deleted.")
    return redirect("boards:detail", board_id=board_id)


@login_required
@require_POST
def board_update(request, board_id):
    board = get_object_or_404(Board, id=board_id, owner=request.user)

    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()

    if not name:
        return redirect("boards:list")

    board.name = name
    board.description = description
    board.save()

    return redirect("boards:list")


@login_required
@require_POST
def board_delete(request, board_id):
    board = get_object_or_404(Board, id=board_id, owner=request.user)
    board.delete()
    return redirect("boards:list")


@require_POST
@login_required
def task_archive(request, task_id):
    task = get_object_or_404(Task, id=task_id, board__owner=request.user)

    if task.status == Task.Status.DONE:
        task.is_archived = True
        task.save(update_fields=["is_archived"])

    return redirect("boards:detail", board_id=task.board_id)


@login_required
def archive_list(request):
    tasks = (
        Task.objects.filter(board__owner=request.user, is_archived=True)
        .select_related("board")
        .order_by("-completed_at", "-created_at")
    )
    return render(request, "boards/archive_modern.html", {"tasks": tasks})

@require_POST
@login_required
def task_delete(request, task_id):
    task = get_object_or_404(Task, id=task_id, board__owner=request.user, is_archived=True)
    task.delete()
    messages.success(request, "Task deleted permanently.")
    return redirect("boards:archive_list")
