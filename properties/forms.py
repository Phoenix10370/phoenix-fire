from django import forms
from .models import Property


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        exclude = ["site_id"]

        labels = {
            "sor_site_id": "SOR Site ID",
            "active_status": "Active",
            "afss_due_date": "AFSS Due Date",
            "afss_number": "AFSS Number",
            "certification_date": "Certification Date",
            "levels_above_ground": "Levels Above Ground",
            "levels_below_ground": "Levels Below Ground",
            "number_of_residential": "Number of Residential",
            "number_of_commercial": "Number of Commercial",
            "access_details": "Access Details",
            "access_code": "Access Code / Notes",
            "site_contact": "Site Contact",
            "contact_phone": "Contact Phone",
        }

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

            "property_description": forms.Select(attrs={"class": "form-select"}),
            "number_of_residential": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "number_of_commercial": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "afss_number": forms.TextInput(attrs={"class": "form-control"}),
            "certification_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "active_status" in self.fields:
            self.fields["active_status"].required = False

        if "customer" in self.fields and self.fields["customer"].queryset is not None:
            try:
                self.fields["customer"].queryset = self.fields["customer"].queryset.order_by("customer_name")
            except Exception:
                pass

        # ✅ If a customer is preselected (via view initial or editing an existing property),
        # lock the dropdown to prevent accidental reassignment.
        locked_customer = None

        if getattr(self.instance, "pk", None) and getattr(self.instance, "customer_id", None):
            locked_customer = self.instance.customer_id
        else:
            initial_customer = self.initial.get("customer")
            if initial_customer:
                locked_customer = getattr(initial_customer, "pk", initial_customer)

        if locked_customer and "customer" in self.fields:
            self.fields["customer"].disabled = True
