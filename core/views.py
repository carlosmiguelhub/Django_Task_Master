from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render

from boards.models import Task  # ✅ USE THE BOARDS TASK MODEL


def landing(request):
    return render(request, "core/landing.html")


@login_required
def dashboard(request):
    qs = Task.objects.filter(board__owner=request.user, is_archived=False)

    counts = qs.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=Task.Status.PENDING)),
        in_progress=Count("id", filter=Q(status=Task.Status.IN_PROGRESS)),
        done=Count("id", filter=Q(status=Task.Status.DONE)),
    )

    context = {
        "counts": counts,  # ✅ use counts.total / counts.pending / counts.in_progress / counts.done
    }
    return render(request, "core/dashboard.html", context)
