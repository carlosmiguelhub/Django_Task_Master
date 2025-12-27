from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import BoardCreateForm, TaskCreateForm
from .models import Board, Task


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
        .annotate(task_count=Count("tasks"))
        .order_by("-created_at")
    )

    return render(request, "boards/board_list.html", {"boards": boards, "form": form})

@login_required
def board_detail(request, board_id):
    board = get_object_or_404(Board, id=board_id, owner=request.user)

    if request.method == "POST":
        task_form = TaskCreateForm(request.POST)
        if task_form.is_valid():
            task = task_form.save(commit=False)
            task.board = board
            task.status = Task.Status.PENDING
            task.save()
            return redirect("boards:detail", board_id=board.id)
        else:
            print("TASK FORM ERRORS:", task_form.errors)  # <- shows why it didn't save
    else:
        task_form = TaskCreateForm()

    pending = board.boards_tasks.filter(status=Task.Status.PENDING)
    progress = board.boards_tasks.filter(status=Task.Status.IN_PROGRESS)
    done = board.boards_tasks.filter(status=Task.Status.DONE)

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

    # Only allow start if currently pending
    if task.status == Task.Status.PENDING:
        task.status = Task.Status.IN_PROGRESS
        task.save(update_fields=["status"])

    return redirect("boards:detail", board_id=task.board_id)


@require_POST
@login_required
def task_complete(request, task_id):
    task = get_object_or_404(Task, id=task_id, board__owner=request.user)

    # Only allow complete if currently in progress
    if task.status == Task.Status.IN_PROGRESS:
        task.status = Task.Status.DONE
        task.save(update_fields=["status"])

    return redirect("boards:detail", board_id=task.board_id)



# =========================
# NEW: UPDATE BOARD (POST)
# =========================
@login_required
@require_POST
def board_update(request, board_id):
    board = get_object_or_404(Board, id=board_id, owner=request.user)

    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()

    if not name:
        # Keep it simple: just go back if empty
        return redirect("boards:list")

    board.name = name
    board.description = description
    board.save()

    return redirect("boards:list")


# =========================
# NEW: DELETE BOARD (POST)
# =========================
@login_required
@require_POST
def board_delete(request, board_id):
    board = get_object_or_404(Board, id=board_id, owner=request.user)
    board.delete()
    return redirect("boards:list")


