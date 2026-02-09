# routines/forms.py
from django import forms

from job_tasks.models import JobServiceType
from .models import MONTH_CHOICES, ServiceRoutineItem


class CreateServiceRoutinesFromQuotationForm(forms.Form):
    annual_due_month = forms.ChoiceField(
        choices=MONTH_CHOICES,
        label="Select Annual Due Month",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    invoice_frequency = forms.ChoiceField(
        choices=[
            ("annual", "Annually"),
            ("bi_annual", "Bi Annually"),
            ("quarterly", "Quarterly"),
            ("monthly", "Monthly"),
            ("calculator", "As per Calculator"),
        ],
        label="Invoice Frequency",
        initial="calculator",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Controls how the quotation total is distributed across the created routines.",
    )

    # ✅ NEW: Service Type (JobServiceType)
    service_type = forms.ModelChoiceField(
        queryset=JobServiceType.objects.filter(is_active=True).order_by("name"),
        required=False,
        empty_label="— Select Service Type —",
        label="Service Type",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="This will be saved onto each created Service Routine, and copied to Job Tasks created from routines.",
    )


class AddServiceRoutineItemForm(forms.ModelForm):
    """
    Allows adding a routine item in two ways:
      1) Select an EFSM code (from Code table)
      2) OR type a custom description (does NOT create/modify EFSM codes)
    """
    class Meta:
        model = ServiceRoutineItem
        fields = ["efsm_code", "custom_description", "quantity", "unit_price"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["efsm_code"].required = False
        self.fields["custom_description"].required = False

        self.fields["efsm_code"].widget.attrs.update({"class": "form-select"})
        self.fields["custom_description"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Custom description (only if not using EFSM code)",
        })
        self.fields["quantity"].widget.attrs.update({"class": "form-control", "min": "0", "step": "1"})
        self.fields["unit_price"].widget.attrs.update({"class": "form-control", "min": "0", "step": "0.01"})

    def clean(self):
        cleaned = super().clean()
        efsm = cleaned.get("efsm_code")
        custom = (cleaned.get("custom_description") or "").strip()

        if not efsm and not custom:
            raise forms.ValidationError("Select an EFSM code OR type a custom description.")

        if efsm:
            cleaned["custom_description"] = ""

        return cleaned

    def clean_quantity(self):
        return self.cleaned_data.get("quantity") or 0
