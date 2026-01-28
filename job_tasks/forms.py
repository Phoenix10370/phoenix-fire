from django import forms
from django.contrib.auth import get_user_model

from .models import JobTask, JobServiceType

User = get_user_model()


class JobTaskForm(forms.ModelForm):
    class Meta:
        model = JobTask
        fields = [
            "title",
            "description",
            "status",
            "service_date",
            "service_type",
            "service_technician",
            "additional_technicians",
            "due_date",
            "site",            # ✅ was property
            "customer",
            "service_routine",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "service_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "service_type": forms.Select(attrs={"class": "form-select"}),
            "service_technician": forms.Select(attrs={"class": "form-select"}),
            "additional_technicians": forms.SelectMultiple(attrs={"class": "form-select", "size": 8}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "site": forms.Select(attrs={"class": "form-select"}),  # ✅ was property
            "customer": forms.Select(attrs={"class": "form-select"}),
            "service_routine": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["service_type"].queryset = JobServiceType.objects.filter(is_active=True).order_by("name")
        self.fields["service_technician"].queryset = User.objects.order_by("username")
        self.fields["additional_technicians"].queryset = User.objects.order_by("username")
        self.fields["additional_technicians"].help_text = "Hold CTRL to select multiple."
