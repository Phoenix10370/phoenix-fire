from django import forms

from .models import Contact, Customer, Site


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "customer_name",
            "customer_type",
            "customer_address",
            "customer_contact_name",
            "customer_main_phone",
            "billing_email",
            "add_email",
            "add_phone",
            "customer_abn_acn",

            # NEW (editable)
            "billing_type",

            "is_active",
            "notes",
        ]
        widgets = {
            "customer_name": forms.TextInput(attrs={"class": "form-control"}),
            "customer_type": forms.Select(attrs={"class": "form-select"}),
            "customer_address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "customer_contact_name": forms.TextInput(attrs={"class": "form-control"}),
            "customer_main_phone": forms.TextInput(attrs={"class": "form-control"}),
            "billing_email": forms.EmailInput(attrs={"class": "form-control"}),
            "add_email": forms.EmailInput(attrs={"class": "form-control"}),
            "add_phone": forms.TextInput(attrs={"class": "form-control"}),
            "customer_abn_acn": forms.TextInput(attrs={"class": "form-control"}),

            # NEW widget
            "billing_type": forms.Select(attrs={"class": "form-select"}),

            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    # Make checkbox look right in Bootstrap
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ["site_name", "address"]
        widgets = {
            "site_name": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["name", "email", "phone", "is_primary"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
        }

    # Make checkbox look right in Bootstrap
    is_primary = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

    for field in self.fields.values():
        field.widget.attrs.setdefault("class", "")
        field.widget.attrs["class"] += " form-control"

class CustomerImportForm(forms.Form):
    file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".csv"})
    )
