# quotations/forms.py
from decimal import Decimal, InvalidOperation

from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.core.exceptions import ValidationError

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


def _to_decimal(val, default=Decimal("0.00")) -> Decimal:
    try:
        if val in (None, ""):
            return default
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return default


def _to_int(val, default=0) -> int:
    try:
        if val in (None, ""):
            return default
        return int(Decimal(str(val)))
    except Exception:
        return default


class QuotationItemForm(forms.ModelForm):
    class Meta:
        model = QuotationItem
        fields = ["efsm_code", "quantity", "unit_price", "position"]
        widgets = {
            "efsm_code": forms.Select(attrs={"class": "form-select efsm-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "unit_price": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "step": "0.01"}
            ),
            "position": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        f = self.fields["efsm_code"]
        f.widget.attrs["data-autocomplete-url"] = "/quotations/autocomplete/efsm/"

        # ✅ allow blank extra row without validation errors
        self.fields["efsm_code"].required = False
        self.fields["quantity"].required = False
        self.fields["unit_price"].required = False

        # ✅ On POST, Django must validate selected IDs
        if self.is_bound:
            f.queryset = Code.objects.all()
        else:
            # ✅ On GET, keep it light
            if self.instance and self.instance.efsm_code_id:
                f.queryset = Code.objects.filter(pk=self.instance.efsm_code_id)
            else:
                f.queryset = Code.objects.none()

            # make extra rows appear blank
            if not getattr(self.instance, "pk", None):
                self.fields["quantity"].initial = ""
                self.fields["unit_price"].initial = ""

    def clean(self):
        cleaned = super().clean()

        efsm = cleaned.get("efsm_code")
        qty_raw = cleaned.get("quantity")
        unit_raw = cleaned.get("unit_price")

        qty = _to_int(qty_raw, 0)
        unit = _to_decimal(unit_raw, Decimal("0.00"))

        # No EFSM selected: allow empty row; but block "half-filled" rows
        if efsm is None:
            typed_qty = qty_raw not in (None, "", "0")
            typed_unit = unit_raw not in (None, "", "0", "0.0", "0.00")

            # If they typed a meaningful value but didn't choose an EFSM, force them to choose or delete
            meaningful = (typed_qty and qty not in (0, 1)) or (typed_unit and unit != Decimal("0.00"))
            if meaningful:
                raise ValidationError("Select an EFSM code for this row, or delete the row.")

            # treat as empty row
            cleaned["quantity"] = None
            cleaned["unit_price"] = None
            return cleaned

        # EFSM selected: ALWAYS normalize quantity/unit so DB never gets NULL
        if qty <= 0:
            cleaned["quantity"] = 1
        else:
            cleaned["quantity"] = qty

        if unit_raw in (None, ""):
            cleaned["unit_price"] = Decimal("0.00")
        else:
            cleaned["unit_price"] = unit

        return cleaned


class BaseQuotationItemFormSet(BaseInlineFormSet):
    """
    Save items in the exact order they appear in the browser by writing `position`
    sequentially in form order. Also harden against NULL quantity/unit_price.
    """

    def save(self, commit=True):
        if not self.is_valid():
            return super().save(commit=commit)

        saved_instances = []

        # 1) delete flagged rows
        if self.can_delete:
            for form in self.forms:
                if not hasattr(form, "cleaned_data"):
                    continue
                if form.cleaned_data.get("DELETE"):
                    inst = form.instance
                    if inst and getattr(inst, "pk", None):
                        inst.delete()

        # 2) save remaining rows in UI order
        pos = 1
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if self.can_delete and form.cleaned_data.get("DELETE"):
                continue

            efsm = form.cleaned_data.get("efsm_code")
            if efsm is None:
                continue  # skip empty row(s)

            inst: QuotationItem = form.save(commit=False)
            inst.quotation = self.instance
            inst.position = pos
            pos += 1

            # ✅ HARDEN: never allow NULL/blank quantity (DB is NOT NULL)
            try:
                q = inst.quantity
                if q in (None, "", 0):
                    inst.quantity = 1
                else:
                    inst.quantity = int(q)
            except Exception:
                inst.quantity = 1

            # ✅ HARDEN: never allow NULL/blank unit_price
            try:
                up = inst.unit_price
                if up in (None, ""):
                    inst.unit_price = Decimal("0.00")
                else:
                    inst.unit_price = Decimal(str(up))
            except Exception:
                inst.unit_price = Decimal("0.00")

            if commit:
                inst.save()

            saved_instances.append(inst)

        return saved_instances


QuotationItemFormSet = inlineformset_factory(
    Quotation,
    QuotationItem,
    form=QuotationItemForm,
    formset=BaseQuotationItemFormSet,
    extra=1,
    can_delete=True,
)
