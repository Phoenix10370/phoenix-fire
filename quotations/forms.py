# quotations/forms.py
from django import forms
from django.forms import inlineformset_factory

from .models import Quotation, QuotationItem
from codes.models import Code


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ["status", "notes"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class QuotationItemForm(forms.ModelForm):
    class Meta:
        model = QuotationItem
        fields = ["efsm_code", "quantity", "unit_price"]
        widgets = {
            "efsm_code": forms.Select(attrs={"class": "form-select efsm-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "unit_price": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "step": "0.01"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        f = self.fields["efsm_code"]
        f.widget.attrs["data-autocomplete-url"] = "/quotations/autocomplete/efsm/"

        # ✅ CRITICAL: On POST, Django must be able to validate the selected ID.
        # This does NOT affect page load performance (only runs when saving).
        if self.is_bound:
            f.queryset = Code.objects.all()
        else:
            # GET: keep it fast (no huge dropdown)
            if self.instance and self.instance.efsm_code_id:
                f.queryset = Code.objects.filter(pk=self.instance.efsm_code_id)
            else:
                f.queryset = Code.objects.none()


QuotationItemFormSet = inlineformset_factory(
    Quotation,
    QuotationItem,
    form=QuotationItemForm,
    extra=1,
    can_delete=True,
)
