# properties/views.py

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)

from .models import Property, PropertyAsset
from .forms import PropertyForm

from quotations.models import Quotation
from routines.models import ServiceRoutine

# Asset UI helpers
from codes.models import (
    DropdownList,
    DropdownOption,
    AssetCode,
    AssetField,
    EquipmentOptionalField,
)


def _safe_redirect_back(request, fallback_url_name: str, **fallback_kwargs):
    ref = request.META.get("HTTP_REFERER")
    if ref:
        return redirect(ref)
    return redirect(fallback_url_name, **fallback_kwargs)


def _extract_attributes_from_post(post_data):
    """
    Accepts:
      - attributes_json: JSON dict string (optional)
      - attr__<slug>=<value> fields
    """
    raw_json = (post_data.get("attributes_json") or "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                return {k: v for k, v in parsed.items() if v not in (None, "", [], {})}
        except Exception:
            pass

    attrs = {}
    for k, v in post_data.items():
        if not k.startswith("attr__"):
            continue
        key = k.replace("attr__", "", 1).strip()
        val = (v or "").strip() if isinstance(v, str) else v
        if key and val not in (None, "", [], {}):
            attrs[key] = val
    return attrs


def _get_dropdown_list(name_contains: str):
    qs = DropdownList.objects.filter(is_active=True)
    dl = qs.filter(name__icontains=name_contains).first()
    if dl:
        return dl
    return qs.filter(slug__icontains=name_contains.replace(" ", "-")).first()


def _build_equipment_optional_map(equipment_ids: list[int]) -> dict:
    """
    JSON-safe structure for the template:

      {
        "<equipment_id>": {
          "<field_slug>": ["Option1", "Option2", ...],  # may be []
          ...
        },
        ...
      }

    Only includes active rows + active AssetField.

    IMPORTANT:
      - If a mapping exists but has no values, we still include the field with [].
        UI should treat [] as "free-text input".
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

        cleaned: list[str] = []
        seen = set()

        for v in vals:
            s = str(v).strip()
            if not s:
                continue
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(s)

        # ✅ Always include the field, even if cleaned is empty.
        out.setdefault(eq_key, {})[field_slug] = cleaned

    return out



def _build_asset_field_payload():
    """
    Build a payload describing all AssetField rows.
    NOTE: We do NOT attach dropdown options here anymore.
          Dropdown options now come from EquipmentOptionalField (per equipment).
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


class PropertyListView(ListView):
    model = Property
    template_name = "properties/property_list.html"
    context_object_name = "items"

    def get_queryset(self):
        qs = Property.objects.select_related("customer").order_by("site_id")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(site_id__icontains=q)
                | Q(building_name__icontains=q)
                | Q(street__icontains=q)
                | Q(city__icontains=q)
                | Q(customer__customer_name__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        return context


class PropertyDetailView(DetailView):
    model = Property
    template_name = "properties/property_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "details"
        return context


class PropertyQuotationsView(DetailView):
    model = Property
    template_name = "properties/property_quotations.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "quotations"
        context["quotations"] = Quotation.objects.filter(site_id=self.object.pk).order_by("-id")
        return context


class PropertyRoutinesView(DetailView):
    model = Property
    template_name = "properties/property_routines.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "routines"
        context["routines"] = (
            ServiceRoutine.objects
            .filter(site_id=self.object.pk)
            .select_related("quotation")
            .prefetch_related("items")
            .order_by("-id")
        )
        return context


class PropertyAssetsView(DetailView):
    """
    Property -> Assets tab page (Add Asset + list existing).
    """
    model = Property
    template_name = "properties/property_assets.html"

    def get_queryset(self):
        return Property.objects.select_related("customer")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "assets"

        # Existing property assets
        context["assets"] = (
            self.object.site_assets.all()
            .order_by("asset_label", "location", "level", "block", "id")
        )

        # ContentType for AssetCode (locked)
        context["assetcode_ct_id"] = ContentType.objects.get_for_model(AssetCode).id

        # Category/Equipment dropdown lists
        categories_list = _get_dropdown_list("Asset Categories")
        equipment_list = _get_dropdown_list("Asset Equipment")

        context["categories_list"] = categories_list
        context["equipment_list"] = equipment_list

        context["asset_categories"] = (
            DropdownOption.objects.filter(dropdown_list=categories_list, is_active=True)
            .order_by("label")
            if categories_list else DropdownOption.objects.none()
        )

        context["asset_equipment"] = (
            DropdownOption.objects.filter(dropdown_list=equipment_list, is_active=True)
            .select_related("parent")
            .order_by("label")
            if equipment_list else DropdownOption.objects.none()
        )

        # Asset codes (library)
        context["asset_codes"] = (
            AssetCode.objects.filter(is_active=True)
            .select_related("category", "equipment")
            .order_by("code")
        )

        # Optional fields (all AssetFields, but values come per equipment)
        context["asset_field_payload"] = _build_asset_field_payload()

        # Equipment -> Field -> Allowed values map (from EquipmentOptionalField)
        equipment_ids = list(
            context["asset_equipment"].values_list("id", flat=True)
        ) if context["asset_equipment"] is not None else []

        context["equipment_optional_map"] = _build_equipment_optional_map(equipment_ids)

        return context


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def add_property_asset(request, pk: int):
    """
    Locked to codes.AssetCode.

    POST:
      - asset_code_ct_id (hidden, validated)
      - asset_code_id
      - barcode (optional)
      - block, level, location
      - attr__<slug> optional fields
    """
    prop = get_object_or_404(Property, pk=pk)

    asset_code_id = (request.POST.get("asset_code_id") or "").strip()
    if not asset_code_id.isdigit():
        messages.error(request, "Please select a valid Asset Code.")
        return _safe_redirect_back(request, "properties:assets", pk=prop.pk)

    ct_id = (request.POST.get("asset_code_ct_id") or "").strip()
    assetcode_ct = ContentType.objects.get_for_model(AssetCode)
    if not (ct_id.isdigit() and int(ct_id) == assetcode_ct.id):
        messages.error(request, "Invalid asset library reference.")
        return _safe_redirect_back(request, "properties:assets", pk=prop.pk)

    asset_code = get_object_or_404(AssetCode, pk=int(asset_code_id))

    barcode = (request.POST.get("barcode") or "").strip() or None
    block = (request.POST.get("block") or "").strip()
    level = (request.POST.get("level") or "").strip()
    location = (request.POST.get("location") or "").strip()
    attributes = _extract_attributes_from_post(request.POST)

    try:
        PropertyAsset.objects.create(
            property=prop,
            asset_code_content_type=assetcode_ct,
            asset_code_object_id=asset_code.pk,
            asset_label=str(asset_code),
            barcode=barcode,
            block=block,
            level=level,
            location=location,
            attributes=attributes or {},
        )
    except Exception as e:
        messages.error(request, f"Could not add asset. {e}")
        return _safe_redirect_back(request, "properties:assets", pk=prop.pk)

    messages.success(request, "Asset added to property.")
    return _safe_redirect_back(request, "properties:assets", pk=prop.pk)


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def delete_property_asset(request, pk: int, asset_id: int):
    prop = get_object_or_404(Property, pk=pk)
    asset = get_object_or_404(PropertyAsset, pk=asset_id, property=prop)

    asset.delete()
    messages.success(request, "Asset removed from property.")
    return _safe_redirect_back(request, "properties:assets", pk=prop.pk)


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def bulk_delete_routines(request, pk: int):
    """
    Bulk delete routines for a property.

    POST fields:
      - routine_ids: list of ServiceRoutine ids to delete
      - select_all: "1" if user chose Select All
    """
    prop = get_object_or_404(Property, pk=pk)

    qs = ServiceRoutine.objects.filter(site_id=prop.pk)

    select_all = (request.POST.get("select_all") or "") == "1"
    if select_all:
        to_delete = qs
    else:
        routine_ids = request.POST.getlist("routine_ids")
        routine_ids = [rid for rid in routine_ids if str(rid).strip().isdigit()]
        if not routine_ids:
            messages.warning(request, "No routines selected.")
            return redirect("properties:routines", pk=prop.pk)
        to_delete = qs.filter(pk__in=routine_ids)

    count = to_delete.count()
    to_delete.delete()

    messages.success(request, f"Deleted {count} routine(s).")
    return redirect("properties:routines", pk=prop.pk)


class PropertyCreateView(CreateView):
    model = Property
    form_class = PropertyForm
    template_name = "properties/property_form.html"
    success_url = reverse_lazy("properties:list")


class PropertyUpdateView(UpdateView):
    model = Property
    form_class = PropertyForm
    template_name = "properties/property_form.html"
    success_url = reverse_lazy("properties:list")


class PropertyDeleteView(DeleteView):
    model = Property
    template_name = "properties/property_confirm_delete.html"
    success_url = reverse_lazy("properties:list")
