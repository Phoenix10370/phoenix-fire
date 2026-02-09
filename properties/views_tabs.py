# properties/views_tabs.py

import json

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.views.generic import DetailView

from .models import Property

from codes.models import (
    DropdownList,
    DropdownOption,
    AssetCode,
    AssetField,
    EquipmentOptionalField,
)
from job_tasks.models import JobTaskAssetLink, JobTaskAssetResult
from .utils import build_property_tab_counts


def _get_dropdown_list(name_contains: str):
    """
    Try to locate a DropdownList by name/slug. Keeps things resilient if names vary slightly.
    """
    qs = DropdownList.objects.filter(is_active=True)
    dl = qs.filter(name__icontains=name_contains).first()
    if dl:
        return dl
    return qs.filter(slug__icontains=name_contains.replace(" ", "-")).first()


def _build_asset_field_payload():
    """
    Used by the template to render all possible optional fields containers.
    JS will decide which ones to show based on equipmentOptionalMap.
    """
    payload = []
    for f in AssetField.objects.filter(is_active=True).order_by("label"):
        payload.append(
            {
                "slug": f.slug,
                "label": f.label,
            }
        )
    return payload


def _build_equipment_optional_map(equipment_ids: list[int]) -> dict:
    """
    Returns a JSON-safe structure:
      {
        "<equipment_id>": {
          "<field_slug>": ["Option1", "Option2", ...],
          ...
        },
        ...
      }

    Only includes active rows.
    """
    if not equipment_ids:
        return {}

    rows = (
        EquipmentOptionalField.objects
        .filter(
            is_active=True,
            equipment_id__in=equipment_ids,
            field__is_active=True,
        )
        .select_related("field")
        .order_by("equipment_id", "field__label", "id")
    )

    out: dict[str, dict[str, list[str]]] = {}
    for r in rows:
        eq_key = str(r.equipment_id)
        field_slug = r.field.slug

        vals = r.values or []
        if not isinstance(vals, list):
            vals = []

        cleaned = []
        seen = set()
        for v in vals:
            s = str(v).strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            cleaned.append(s)

        out.setdefault(eq_key, {})[field_slug] = cleaned

    return out


class PropertyAssetsView(DetailView):
    model = Property
    template_name = "properties/property_assets.html"

    def get_queryset(self):
        return Property.objects.select_related("customer")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "assets"
        context["tab_counts"] = build_property_tab_counts(self.object)

        # Existing property assets
        assets = (
            self.object.site_assets.all()
            .order_by("asset_label", "location", "level", "block", "id")
        )
        context["assets"] = assets

        # ContentType for codes.AssetCode (so the form can post asset_code_ct_id + asset_code_id)
        assetcode_ct = ContentType.objects.get_for_model(AssetCode)
        context["assetcode_ct_id"] = assetcode_ct.id

        # Category/Equipment dropdown lists
        categories_list = _get_dropdown_list("Asset Categories")
        equipment_list = _get_dropdown_list("Asset Equipment")

        context["categories_list"] = categories_list
        context["equipment_list"] = equipment_list

        if categories_list:
            context["asset_categories"] = (
                DropdownOption.objects
                .filter(dropdown_list=categories_list, is_active=True)
                .order_by("label")
            )
        else:
            context["asset_categories"] = DropdownOption.objects.none()

        if equipment_list:
            # IMPORTANT: include parent relationship (equipment.parent_id points to category id)
            context["asset_equipment"] = (
                DropdownOption.objects
                .filter(dropdown_list=equipment_list, is_active=True)
                .select_related("parent")
                .order_by("label")
            )
        else:
            context["asset_equipment"] = DropdownOption.objects.none()

        # Asset codes (library)
        context["asset_codes"] = (
            AssetCode.objects.filter(is_active=True)
            .select_related("category", "equipment")
            .order_by("code")
        )

        # Optional Fields UI scaffolding (all possible fields)
        context["asset_field_payload"] = _build_asset_field_payload()

        # Equipment Optional Field mapping for JS
        equipment_ids = list(
            context["asset_equipment"].values_list("id", flat=True)
        ) if equipment_list else []

        context["equipment_optional_map"] = _build_equipment_optional_map(equipment_ids)

        # ✅ Add asset-code keyed map for optional fields
        context["asset_code_optional_map"] = {
            str(ac.id): context["equipment_optional_map"].get(str(ac.equipment_id), {})
            for ac in context["asset_codes"]
        }

        # ✅ Add asset attributes map for modal rendering
        context["asset_attrs_map"] = {
            str(a.pk): (a.attributes or {})
            for a in assets
        }

        asset_ids = list(assets.values_list("id", flat=True))
        history_map: dict[str, list[dict]] = {}
        inspected_count = 0
        if asset_ids:
            results = (
                JobTaskAssetResult.objects
                .filter(property_asset_id__in=asset_ids)
                .exclude(result="")
                .select_related(
                    "job_task",
                    "job_task__parent_job",
                    "job_task__service_type",
                    "job_task__service_technician",
                )
                .order_by("-updated_at")
            )
            inspected_count = (
                results.values("property_asset_id").distinct().count()
            )
            for res in results:
                jt = res.job_task
                if not jt:
                    continue
                root_job = jt.parent_job if jt.parent_job_id else jt

                service_type = ""
                if root_job.service_type_id and root_job.service_type:
                    service_type = root_job.service_type.name or ""

                technician = ""
                if jt.service_technician_id and jt.service_technician:
                    full = jt.service_technician.get_full_name()
                    technician = full or jt.service_technician.username

                rows = history_map.setdefault(str(res.property_asset_id), [])
                rows.append(
                    {
                        "job_task_id": root_job.pk,
                        "service_type": service_type,
                        "result": res.result or "",
                        "child_job_id": jt.pk,
                        "child_service_date": jt.service_date.isoformat() if jt.service_date else "",
                        "child_technician": technician,
                        "child_is_parent": jt.pk == root_job.pk,
                    }
                )

        for asset in assets:
            asset.history_count = len(history_map.get(str(asset.pk), []))

        context["asset_history_map"] = history_map
        context["asset_total_count"] = assets.count()
        context["asset_inspected_count"] = inspected_count

        return context


class PropertyKeyContactView(DetailView):
    model = Property
    template_name = "properties/property_key_contact.html"

    def get_queryset(self):
        return Property.objects.select_related("customer")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "key_contact"
        context["tab_counts"] = build_property_tab_counts(self.object)
        return context


class PropertyCorrespondenceView(DetailView):
    model = Property
    template_name = "properties/property_correspondence.html"

    def get_queryset(self):
        return Property.objects.select_related("customer")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "correspondence"
        context["tab_counts"] = build_property_tab_counts(self.object)
        return context
