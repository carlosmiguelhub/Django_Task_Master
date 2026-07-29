from django.conf import settings
from django.db import models


class CalendarEvent(models.Model):
    class EventType(models.TextChoices):
        MEETING = "meeting", "Meeting"
        FOCUS = "focus", "Focus session"
        CLASS = "class", "Class"
        APPOINTMENT = "appointment", "Appointment"
        PERSONAL = "personal", "Personal"
        OTHER = "other", "Other"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_events",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
        default=EventType.MEETING,
    )
    location = models.CharField(max_length=240, blank=True)
    meeting_url = models.URLField(max_length=500, blank=True)

    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    all_day = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.start_at})"
