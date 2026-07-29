from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("boards", "0009_alter_task_board"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="estimated_minutes",
            field=models.PositiveIntegerField(
                default=60,
                validators=[
                    django.core.validators.MinValueValidator(15),
                    django.core.validators.MaxValueValidator(1440),
                ],
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="scheduled_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="task",
            name="scheduled_start",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
