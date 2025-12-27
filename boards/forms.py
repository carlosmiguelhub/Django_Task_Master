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

    class Meta:
        model = Task
        fields = ["title", "priority", "due_date", "due_time"]  # EXCLUDE documents + status

    def clean_title(self):
        return self.cleaned_data["title"].strip()
