# job_tasks/forms.py
from datetime import time

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory

from .models import JobTask, JobServiceType, JobTaskItem

User = get_user_model()


def _time_label_12h(t: time) -> str:
    """
    Windows-safe 12h label like 8:30am (no leading zero).
    """
    label = t.strftime("%I:%M%p").lower()  # 08:30am
    if label.startswith("0"):
        label = label[1:]
    return label


def _time_choices_15min(start_hour: int = 6, end_hour: int = 19):
    """
    Values are HH:MM:SS to match Django TimeField rendering exactly.
    Range limited to start_hour..end_hour (inclusive).
    """
    choices = [("", "—")]
    start = time(start_hour, 0, 0)
    end = time(end_hour, 0, 0)
    for h in range(0, 24):
        for m in (0, 15, 30, 45):
            t = time(h, m, 0)
            if t < start or t > end:
                continue
            value = t.strftime("%H:%M:%S")  # IMPORTANT
            choices.append((value, _time_label_12h(t)))
    return choices


TIME_CHOICES = _time_choices_15min(6, 19)


class JobTaskForm(forms.ModelForm):
    # These expect JobTask model fields: start_time, finish_time (TimeField null=True blank=True)
    start_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M:%S", "%H:%M"],
        widget=forms.Select(attrs={"class": "form-select"}, choices=TIME_CHOICES),
    )
    finish_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M:%S", "%H:%M"],
        widget=forms.Select(attrs={"class": "form-select"}, choices=TIME_CHOICES),
    )

    # UI-only: Shared site notes (stored on root/parent job)
    shared_site_notes_ui = forms.CharField(
        required=False,
        label="Shared Site Notes",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        help_text="Shared across all technician/day jobs in this job group.",
    )

    class Meta:
        model = JobTask
        fields = [
            "title",
            "status",
            "service_date",
            "start_time",
            "finish_time",
            "is_all_day",
            "service_type",
            "service_technician",
            "additional_technicians",

            "site",
            "customer",
            "service_routine",

            "client_acknowledgement",
            "acknowledgement_date",
            "work_order_no",
            "admin_comments",

            # Existing per-job notes (kept)
            "technician_comments",

            # NEW per-job technician/day notes
            "technician_job_notes",

            # NEW linkage (kept hidden to avoid changing current UI/flow)
            "parent_job",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "service_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),

            "service_type": forms.Select(attrs={"class": "form-select"}),
            "service_technician": forms.Select(attrs={"class": "form-select"}),

            "is_all_day": forms.CheckboxInput(attrs={"class": "form-check-input"}),

            # Checkboxes instead of CTRL multi-select
            "additional_technicians": forms.CheckboxSelectMultiple(),

            "site": forms.Select(attrs={"class": "form-select"}),
            "customer": forms.Select(attrs={"class": "form-select"}),
            "service_routine": forms.Select(attrs={"class": "form-select"}),

            "client_acknowledgement": forms.Select(attrs={"class": "form-select"}),
            "acknowledgement_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "work_order_no": forms.TextInput(attrs={"class": "form-control"}),

            "admin_comments": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "technician_comments": forms.Textarea(attrs={"class": "form-control", "rows": 5}),

            # NEW per-job notes field UI
            "technician_job_notes": forms.Textarea(attrs={"class": "form-control", "rows": 5}),

            # Hide parent linkage for now (do not alter current workflow/UI)
            "parent_job": forms.HiddenInput(),
        }
        labels = {
            "technician_job_notes": "Technician Job Notes",
            "is_all_day": "All day",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["service_type"].queryset = JobServiceType.objects.filter(is_active=True).order_by("name")
        self.fields["service_technician"].queryset = User.objects.order_by("username")
        self.fields["additional_technicians"].queryset = User.objects.order_by("username")

        # Optional fields
        self.fields["service_date"].required = False
        self.fields["service_technician"].required = False
        self.fields["additional_technicians"].required = False
        self.fields["client_acknowledgement"].required = False
        self.fields["acknowledgement_date"].required = False
        self.fields["work_order_no"].required = False
        self.fields["admin_comments"].required = False
        self.fields["technician_comments"].required = False
        self.fields["technician_job_notes"].required = False
        self.fields["parent_job"].required = False
        self.fields["is_all_day"].required = False

        # Ensure select shows stored values (HH:MM:SS)
        if getattr(self.instance, "start_time", None):
            self.initial["start_time"] = self.instance.start_time.strftime("%H:%M:%S")
        if getattr(self.instance, "finish_time", None):
            self.initial["finish_time"] = self.instance.finish_time.strftime("%H:%M:%S")

        # Shared notes initial comes from root job (parent if child)
        if getattr(self.instance, "pk", None):
            try:
                root = self.instance.root_job
                self.initial["shared_site_notes_ui"] = root.shared_site_notes
            except Exception:
                # never block the form if something odd occurs
                self.initial["shared_site_notes_ui"] = ""

    def save(self, commit=True):
        """
        Save JobTask normally, then write shared_site_notes onto the root/parent job
        using QuerySet.update() to avoid triggering model.save() side-effects.
        """
        instance: JobTask = super().save(commit=commit)

        shared_notes = (self.cleaned_data.get("shared_site_notes_ui") or "").strip()

        # Persist shared notes onto root job without calling save()
        try:
            root = instance.root_job
            JobTask.objects.filter(pk=root.pk).update(shared_site_notes=shared_notes)
        except Exception:
            # Don't break normal save if shared update fails
            pass

        return instance


class JobTaskAddItemForm(forms.Form):
    """
    Matches the routine-style ADD ITEM row.
    """
    code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "EFSM code (optional)"}),
    )
    custom_description = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Custom description (optional)"}),
    )
    quantity = forms.DecimalField(
        required=True,
        initial="1.0",
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    unit_price = forms.DecimalField(
        required=True,
        initial="0.0",
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )


class JobTaskItemForm(forms.ModelForm):
    class Meta:
        model = JobTaskItem
        fields = ["sort_order", "code", "description", "quantity", "unit_price"]
        widgets = {
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "readonly": "readonly"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "EFSM code or custom code"}),
            "description": forms.TextInput(attrs={"class": "form-control", "placeholder": "Description"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


JobTaskItemFormSet = inlineformset_factory(
    JobTask,
    JobTaskItem,
    form=JobTaskItemForm,
    extra=1,
    can_delete=True,
)
