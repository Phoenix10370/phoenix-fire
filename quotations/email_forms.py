from django import forms
from email_templates.models import EmailTemplate


class QuotationSendEmailForm(forms.Form):
    template = forms.ModelChoiceField(
        queryset=EmailTemplate.objects.filter(template_type="quotation", is_active=True).order_by("name"),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Email Template",
    )

    to = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="To",
        help_text="Leave blank to use the template's To field (or fallback email from the quotation).",
    )

    cc = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="CC",
        help_text="Optional override.",
    )
