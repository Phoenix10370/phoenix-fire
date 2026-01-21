# company/forms.py
from django import forms
from .models import ClientProfile


class ClientProfileForm(forms.ModelForm):
    class Meta:
        model = ClientProfile
        fields = [
            "company_logo",
            "legal_company_name",
            "trading_name",
            "company_address",
            "company_phone",
            "company_email",
            "company_abn",
            "company_acn",
            "accounts_phone",
            "accounts_email",
        ]
        widgets = {
            "legal_company_name": forms.TextInput(attrs={"class": "form-control"}),
            "trading_name": forms.TextInput(attrs={"class": "form-control"}),
            "company_address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "company_phone": forms.TextInput(attrs={"class": "form-control"}),
            "company_email": forms.EmailInput(attrs={"class": "form-control"}),
            "company_abn": forms.TextInput(attrs={"class": "form-control"}),
            "company_acn": forms.TextInput(attrs={"class": "form-control"}),
            "accounts_phone": forms.TextInput(attrs={"class": "form-control"}),
            "accounts_email": forms.EmailInput(attrs={"class": "form-control"}),
        }
