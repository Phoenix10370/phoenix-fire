# routines/forms.py
from django import forms

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


# =========================
# ADD ROUTINE ITEM (EFSM OR CUSTOM)
# =========================
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

        # Both EFSM and custom description are optional individually,
        # but one of them must be provided (enforced in clean()).
        self.fields["efsm_code"].required = False
        self.fields["custom_description"].required = False

        # Bootstrap styling
        self.fields["efsm_code"].widget.attrs.update({
            "class": "form-select",
        })
        self.fields["custom_description"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Custom description (only if not using EFSM code)",
        })
        self.fields["quantity"].widget.attrs.update({
            "class": "form-control",
            "min": "0",
            "step": "1",
        })
        self.fields["unit_price"].widget.attrs.update({
            "class": "form-control",
            "min": "0",
            "step": "0.01",
        })

    def clean(self):
        cleaned = super().clean()

        efsm = cleaned.get("efsm_code")
        custom = (cleaned.get("custom_description") or "").strip()

        # Require one of them
        if not efsm and not custom:
            raise forms.ValidationError("Select an EFSM code OR type a custom description.")

        # If EFSM is chosen, ignore any custom text to prevent confusion
        if efsm:
            cleaned["custom_description"] = ""

        return cleaned

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity")
        return qty or 0
