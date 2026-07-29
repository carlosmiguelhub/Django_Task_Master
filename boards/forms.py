from django import forms
from .models import Board, Task

class BoardCreateForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["name", "description"]


class TaskCreateForm(forms.ModelForm):
    due_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date"})
    )
    due_time = forms.TimeField(
        required=True,
        widget=forms.TimeInput(attrs={"type": "time"})
    )
    estimated_minutes = forms.IntegerField(
        required=False,
        min_value=15,
        max_value=1440,
        initial=60,
        widget=forms.NumberInput(attrs={"min": 15, "max": 1440, "step": 15}),
        help_text="Planned focus time in minutes.",
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "priority",
            "estimated_minutes",
            "due_date",
            "due_time",
        ]

    def clean_title(self):
        return self.cleaned_data["title"].strip()

    def clean_estimated_minutes(self):
        return self.cleaned_data.get("estimated_minutes") or 60


class TaskUpdateForm(TaskCreateForm):
    class Meta(TaskCreateForm.Meta):
        fields = [
            "title",
            "description",
            "priority",
            "estimated_minutes",
            "due_date",
            "due_time",
        ]
