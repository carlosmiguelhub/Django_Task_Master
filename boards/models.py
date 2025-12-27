from django.conf import settings
from django.db import models


class Board(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="boards",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class Task(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        DONE = "done", "Done"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"

    board = models.ForeignKey(
        Board,
        on_delete=models.CASCADE,
        related_name="tasks",  # accessor: board.tasks
        related_query_name="tasks",  # query path: Count("tasks")
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )

    due_date = models.DateField(null=True, blank=True)
    due_time = models.TimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    # ✅ completion tracking
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_late = models.BooleanField(default=False)

    # ✅ NEW: archive support
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def due_datetime(self):
        """
        Combine due_date + due_time for UI progress bar.
        If due_time is missing, assume 23:59.
        Returns None if due_date is missing.
        """
        if not self.due_date:
            return None

        import datetime
        t = self.due_time or datetime.time(23, 59)
        return datetime.datetime.combine(self.due_date, t)
