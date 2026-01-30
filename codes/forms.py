from django import forms

from .models import AssetCode, Code, DefectCode, DropdownList, DropdownOption


class CodeForm(forms.ModelForm):
    class Meta:
        model = Code
        fields = ["fire_safety_measure", "visits_per_year"]
        widgets = {
            "fire_safety_measure": forms.TextInput(attrs={"class": "form-control"}),
            "visits_per_year": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }


class DefectCodeForm(forms.ModelForm):
    class Meta:
        model = DefectCode
        fields = ["code", "description"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        }


class AssetCodeForm(forms.ModelForm):
    """
    Asset Code form (library of asset types):
      - Category (required)
      - Equipment (required, dependent on Category)
      - Frequency
      - Active

    Optional/dynamic fields are NOT configured here anymore.
    Those will be selected when adding an Asset to a Property or Job Task.
    """

    class Meta:
        model = AssetCode
        fields = ["category", "equipment", "frequency", "is_active"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select", "id": "id_category"}),
            "equipment": forms.Select(attrs={"class": "form-select", "id": "id_equipment"}),
            "frequency": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Dependent dropdown logic
        cat_list = DropdownList.objects.filter(slug="asset-categories", is_active=True).first()
        eq_list = DropdownList.objects.filter(slug="asset-equipment", is_active=True).first()

        category_qs = DropdownOption.objects.none()
        equipment_qs = DropdownOption.objects.none()

        if cat_list:
            category_qs = DropdownOption.objects.filter(
                dropdown_list=cat_list,
                is_active=True,
            ).order_by("label")

        # Default equipment: none until a category is chosen
        self.fields["category"].queryset = category_qs
        self.fields["equipment"].queryset = equipment_qs

        # If editing existing AssetCode, pre-filter equipment by the saved category
        # BUT always include the currently selected equipment option, even if inactive
        # or no longer under the expected parent, so the edit form doesn't show blank.
        if self.instance and self.instance.pk and self.instance.category_id and eq_list:
            base_qs = DropdownOption.objects.filter(
                dropdown_list=eq_list,
                is_active=True,
                parent_id=self.instance.category_id,
            )

            if self.instance.equipment_id:
                selected_qs = DropdownOption.objects.filter(pk=self.instance.equipment_id)
                self.fields["equipment"].queryset = (base_qs | selected_qs).distinct().order_by("label")
            else:
                self.fields["equipment"].queryset = base_qs.order_by("label")

        # If user posted category, filter equipment based on POST value
        if "category" in self.data:
            try:
                selected_category_id = int(self.data.get("category"))
                if eq_list:
                    self.fields["equipment"].queryset = DropdownOption.objects.filter(
                        dropdown_list=eq_list,
                        is_active=True,
                        parent_id=selected_category_id,
                    ).order_by("label")
            except (TypeError, ValueError):
                pass
