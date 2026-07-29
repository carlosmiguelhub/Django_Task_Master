from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("meeting", "Meeting"),
                    ("focus", "Focus session"),
                    ("class", "Class"),
                    ("appointment", "Appointment"),
                    ("personal", "Personal"),
                    ("other", "Other"),
                ],
                default="meeting",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="calendarevent",
            name="location",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="calendarevent",
            name="meeting_url",
            field=models.URLField(blank=True, max_length=500),
        ),
    ]
