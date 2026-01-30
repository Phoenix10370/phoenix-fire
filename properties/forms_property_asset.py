from django import forms
from django.contrib.contenttypes.models import ContentType

from properties.models import PropertyAsset
from codes.models import AssetCode, EquipmentOptionalField


class PropertyAssetForm(forms.ModelForm):
    """
    Property asset instance form:
    - standard fields (barcode/location)
    - choose an AssetCode (from codes app)
    - dynamic optional fields driven by EquipmentOptionalField for the AssetCode.equipment
    - values saved into PropertyAsset.attributes (per property asset)
    """

    asset_code_id = forms.ModelChoiceField(
        queryset=AssetCode.objects.filter(is_active=True).select_related("category", "equipment"),
        required=False,
        label="Asset Code",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select the asset type (drives optional fields).",
    )

    class Meta:
        model = PropertyAsset
        fields = ["barcode", "block", "level", "location", "asset_label"]
        widgets = {
            "barcode": forms.TextInput(attrs={"class": "form-control"}),
            "block": forms.TextInput(attrs={"class": "form-control"}),
            "level": forms.TextInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(attrs={"class": "form-control"}),
            "asset_label": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # if editing, prefill asset_code_id from generic FK
        if self.instance and self.instance.pk and self.instance.asset_code_content_type_id and self.instance.asset_code_object_id:
            ct = self.instance.asset_code_content_type
            if ct and ct.model == "assetcode":
                try:
                    self.fields["asset_code_id"].initial = AssetCode.objects.get(pk=self.instance.asset_code_object_id)
                except AssetCode.DoesNotExist:
                    pass

        # Determine selected AssetCode (POST first, then instance)
        selected_asset_code = None
        raw = self.data.get("asset_code_id") if self.is_bound else None
        if raw:
            try:
                selected_asset_code = AssetCode.objects.filter(pk=int(raw)).first()
            except Exception:
                selected_asset_code = None
        elif self.fields["asset_code_id"].initial:
            selected_asset_code = self.fields["asset_code_id"].initial

        self._dynamic_fields = []  # list of dicts for template display

        if selected_asset_code and selected_asset_code.equipment_id:
            mappings = (
                EquipmentOptionalField.objects
                .filter(equipment_id=selected_asset_code.equipment_id, is_active=True)
                .select_related("field")
                .order_by("field__label")
            )

            existing_attrs = self.instance.attributes if isinstance(self.instance.attributes, dict) else {}

            for m in mappings:
                slug = m.field.slug
                key = f"attr__{slug}"
                label = m.field.label
                allowed = m.values if isinstance(m.values, list) else []
                initial_val = existing_attrs.get(slug, "")

                if allowed:
                    choices = [("", "---------")] + [(v, v) for v in allowed]
                    self.fields[key] = forms.ChoiceField(
                        required=False,
                        label=label,
                        choices=choices,
                        initial=initial_val,
                        widget=forms.Select(attrs={"class": "form-select"}),
                    )
                else:
                    self.fields[key] = forms.CharField(
                        required=False,
                        label=label,
                        initial=initial_val,
                        widget=forms.TextInput(attrs={"class": "form-control"}),
                    )

                self._dynamic_fields.append(
                    {"name": key, "label": label, "allowed_values": allowed}
                )

    def dynamic_fields(self):
        """For templates: list of {'name','label','allowed_values'}."""
        return self._dynamic_fields

    def save(self, commit=True):
        obj = super().save(commit=False)

        # Write generic FK for asset_code
        ac = self.cleaned_data.get("asset_code_id")
        if ac:
            ct = ContentType.objects.get_for_model(AssetCode)
            obj.asset_code_content_type = ct
            obj.asset_code_object_id = ac.pk
            # optional: keep a label snapshot
            if not (obj.asset_label or "").strip():
                obj.asset_label = str(ac)

        # Store dynamic values into attributes (per-property-asset)
        attrs = obj.attributes if isinstance(obj.attributes, dict) else {}
        # remove old keys we control only if you want strict sync — for now we only update keys present
        for name, value in self.cleaned_data.items():
            if not name.startswith("attr__"):
                continue
            slug = name.replace("attr__", "", 1)
            if value is None or (isinstance(value, str) and not value.strip()):
                attrs.pop(slug, None)
            else:
                attrs[slug] = value

        obj.attributes = attrs

        if commit:
            obj.save()
        return obj
