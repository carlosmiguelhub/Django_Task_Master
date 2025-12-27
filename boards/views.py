from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
import datetime

from .forms import BoardCreateForm, TaskCreateForm
from .models import Board, Task
from django.contrib import messages





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
            task_count=Count("tasks", filter=Q(tasks__is_archived=False))
        )
        .order_by("-created_at")
    )

    return render(request, "boards/board_list.html", {"boards": boards, "form": form})


@login_required
def board_detail(request, board_id):
    board = get_object_or_404(Board, id=board_id, owner=request.user)

    # Add Task (modal submits here)
    if request.method == "POST":
        task_form = TaskCreateForm(request.POST)
        if task_form.is_valid():
            task = task_form.save(commit=False)
            task.board = board
            task.status = Task.Status.PENDING
            task.save()
            return redirect("boards:detail", board_id=board.id)
        else:
            print("TASK FORM ERRORS:", task_form.errors)
    else:
        task_form = TaskCreateForm()

    # ✅ If your runtime uses "tasks", these should also be "board.tasks"
    pending = board.tasks.filter(status=Task.Status.PENDING, is_archived=False)
    progress = board.tasks.filter(status=Task.Status.IN_PROGRESS, is_archived=False)
    done = board.tasks.filter(status=Task.Status.DONE, is_archived=False)

    return render(
        request,
        "boards/board_detail.html",
        {
            "board": board,
            "pending": pending,
            "progress": progress,
            "done": done,
            "form": task_form,
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
        now = timezone.now()

        due_dt = None
        if task.due_date:
            t = task.due_time or datetime.time(23, 59)
            due_dt = datetime.datetime.combine(task.due_date, t)
            due_dt = timezone.make_aware(due_dt, timezone.get_current_timezone())

        task.status = Task.Status.DONE
        task.completed_at = now
        task.completed_late = bool(due_dt and now > due_dt)

        task.save(update_fields=["status", "completed_at", "completed_late"])

    return redirect("boards:detail", board_id=task.board_id)


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
    return render(request, "boards/archive_list.html", {"tasks": tasks})

@require_POST
@login_required
def task_delete(request, task_id):
    task = get_object_or_404(Task, id=task_id, board__owner=request.user, is_archived=True)
    task.delete()
    messages.success(request, "Task deleted permanently.")
    return redirect("boards:archive_list")