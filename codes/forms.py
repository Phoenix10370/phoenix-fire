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

        # Find the lists by slug created by your seeder
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
        if self.instance and self.instance.pk and self.instance.category_id:
            if eq_list:
                self.fields["equipment"].queryset = DropdownOption.objects.filter(
                    dropdown_list=eq_list,
                    is_active=True,
                    parent_id=self.instance.category_id,
                ).order_by("label")


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
