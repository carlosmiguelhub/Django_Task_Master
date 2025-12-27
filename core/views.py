from django.shortcuts import render

# Create your views here.
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from tasks.models import Task

def landing(request):
    return render(request, "core/landing.html")

@login_required
def dashboard(request):
    qs = Task.objects.filter(board__owner=request.user)

    context = {
        "total_tasks": qs.count(),
        "completed_tasks": qs.filter(status=Task.Status.COMPLETED).count(),
        "inprogress_tasks": qs.filter(status=Task.Status.IN_PROGRESS).count(),
        "pending_tasks": qs.filter(status=Task.Status.PENDING).count(),
    }
    return render(request, "core/dashboard.html", context)


