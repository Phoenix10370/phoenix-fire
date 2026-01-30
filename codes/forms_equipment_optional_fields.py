from django import forms
from .models import EquipmentOptionalField


class EquipmentOptionalFieldForm(forms.ModelForm):
    """
    Expose JSONField list `values` as one option per line.
    """
    values_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 10}),
        help_text="Enter one option per line. Blank lines are ignored.",
        label="Allowed dropdown values",
    )

    class Meta:
        model = EquipmentOptionalField
        fields = ["is_active"]  # values handled via values_text

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        existing = []
        if self.instance and isinstance(self.instance.values, list):
            existing = [str(v).strip() for v in self.instance.values if str(v).strip()]
        self.fields["values_text"].initial = "\n".join(existing)

    def clean_values_text(self):
        raw = (self.cleaned_data.get("values_text") or "").splitlines()
        cleaned = []
        seen = set()

        for line in raw:
            val = line.strip()
            if not val:
                continue
            key = val.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(val)

        return cleaned  # <-- return list

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.values = self.cleaned_data.get("values_text") or []
        if commit:
            obj.save()
        return obj
