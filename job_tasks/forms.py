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


def _time_choices_15min():
    """
    Values are HH:MM:SS to match Django TimeField rendering exactly.
    """
    choices = [("", "—")]
    for h in range(0, 24):
        for m in (0, 15, 30, 45):
            t = time(h, m, 0)
            value = t.strftime("%H:%M:%S")  # IMPORTANT
            choices.append((value, _time_label_12h(t)))
    return choices


TIME_CHOICES = _time_choices_15min()


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

    class Meta:
        model = JobTask
        fields = [
            "title",
            "status",
            "service_date",
            "start_time",
            "finish_time",
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

            "technician_comments",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "service_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),

            "service_type": forms.Select(attrs={"class": "form-select"}),
            "service_technician": forms.Select(attrs={"class": "form-select"}),

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

        # Ensure select shows stored values (HH:MM:SS)
        if getattr(self.instance, "start_time", None):
            self.initial["start_time"] = self.instance.start_time.strftime("%H:%M:%S")
        if getattr(self.instance, "finish_time", None):
            self.initial["finish_time"] = self.instance.finish_time.strftime("%H:%M:%S")


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
