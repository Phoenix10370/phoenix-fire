from django import forms

from .models import Property


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        exclude = ["site_id"]
        widgets = {
            "strata_plan": forms.TextInput(attrs={"class": "form-control"}),
            "sor_site_id": forms.TextInput(attrs={"class": "form-control"}),

            "building_name": forms.TextInput(attrs={"class": "form-control"}),
            "street": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
            "post_code": forms.TextInput(attrs={"class": "form-control"}),

            "active_status": forms.CheckboxInput(attrs={"class": "form-check-input"}),

            "customer": forms.Select(attrs={"class": "form-select"}),

            "fire_coordinator": forms.TextInput(attrs={"class": "form-control"}),
            "fire_coordinator_email": forms.EmailInput(attrs={"class": "form-control"}),
            "fire_coordinator_phone": forms.TextInput(attrs={"class": "form-control"}),

            "afss_due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),

            "levels_above_ground": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "levels_below_ground": forms.NumberInput(attrs={"class": "form-control", "min": 0}),

            "access_details": forms.Select(attrs={"class": "form-select"}),
            "access_code": forms.TextInput(attrs={"class": "form-control"}),

            "site_contact": forms.TextInput(attrs={"class": "form-control"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control"}),

            "site_notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "technician_notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }
