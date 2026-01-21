# routines/forms.py
from django import forms
from .models import MONTH_CHOICES


class CreateServiceRoutinesFromQuotationForm(forms.Form):
    annual_due_month = forms.ChoiceField(
        choices=MONTH_CHOICES,
        label="Select Annual Due Month",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
