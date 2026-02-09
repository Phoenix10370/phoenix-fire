# properties/views.py

import json
import ssl
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)

from customers.models import Customer
from .models import Property, PropertyAsset
from .forms import PropertyForm
from .forms_property_asset import PropertyAssetForm
from .utils import build_property_tab_counts

from quotations.models import Quotation
from routines.models import ServiceRoutine
from job_tasks.models import JobTaskAssetLink

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


def _http_get_json(url: str, headers: dict | None = None, timeout: int = 12):
    """
    Small helper to GET JSON without adding external dependencies.
    """
    hdrs = headers or {}
    req = Request(url, headers=hdrs, method="GET")
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _to_decimal6(value) -> Decimal:
    """
    Convert float/str -> Decimal with 6dp precision.
    """
    d = Decimal(str(value))
    return d.quantize(Decimal("0.000001"))


def _geocode_with_google(address: str):
    """
    Returns (lat, lng) as Decimals or (None, None).
    Requires settings.GOOGLE_MAPS_API_KEY.
    """
    key = (getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "").strip()
    if not key:
        return (None, None)

    params = urlencode({"address": address, "key": key})
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"

    data = _http_get_json(url, headers={"User-Agent": "DjangoApp/1.0"})
    if not isinstance(data, dict):
        return (None, None)

    status = data.get("status")
    if status != "OK":
        return (None, None)

    results = data.get("results") or []
    if not results:
        return (None, None)

    loc = (results[0].get("geometry") or {}).get("location") or {}
    lat = loc.get("lat")
    lng = loc.get("lng")
    if lat is None or lng is None:
        return (None, None)

    try:
        return (_to_decimal6(lat), _to_decimal6(lng))
    except (InvalidOperation, ValueError):
        return (None, None)


def _geocode_with_nominatim(address: str):
    """
    Returns (lat, lng) as Decimals or (None, None).
    Uses OpenStreetMap Nominatim (no key required).
    """
    params = urlencode({"q": address, "format": "json", "limit": 1})
    url = f"https://nominatim.openstreetmap.org/search?{params}"

    headers = {"User-Agent": "DjangoApp/1.0 (contact: admin@example.com)"}
    data = _http_get_json(url, headers=headers)

    if not isinstance(data, list) or not data:
        return (None, None)

    first = data[0] or {}
    lat = first.get("lat")
    lng = first.get("lon")
    if not lat or not lng:
        return (None, None)

    try:
        return (_to_decimal6(lat), _to_decimal6(lng))
    except (InvalidOperation, ValueError):
        return (None, None)


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def validate_property_coordinates(request, pk: int):
    """
    Validate (geocode) the property's full_address and LOCK the coordinates.

    Behavior:
      - If coords_validated is True, does nothing unless POST includes force=1
      - Uses Google Geocoding if settings.GOOGLE_MAPS_API_KEY is set
      - Else tries OpenStreetMap Nominatim
      - On success: stores latitude/longitude, sets coords_validated=True, stamps validated_at/by
    """
    prop = get_object_or_404(Property, pk=pk)

    force = (request.POST.get("force") or "").strip() == "1"
    if prop.coords_validated and not force:
        messages.info(request, "Coordinates are already validated.")
        return _safe_redirect_back(request, "properties:detail", pk=prop.pk)

    address = (prop.full_address or "").strip()
    if not address:
        messages.error(request, "This property has no address to validate.")
        return _safe_redirect_back(request, "properties:detail", pk=prop.pk)

    lat = lng = None

    google_key = (getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "").strip()
    try:
        if google_key:
            lat, lng = _geocode_with_google(address)
        else:
            lat, lng = _geocode_with_nominatim(address)
    except Exception as e:
        messages.error(request, f"Could not validate address (geocoding failed). {e}")
        return _safe_redirect_back(request, "properties:detail", pk=prop.pk)

    if lat is None or lng is None:
        if google_key:
            messages.error(request, "Could not validate address using Google Geocoding.")
        else:
            messages.error(request, "Could not validate address using OpenStreetMap geocoding.")
        return _safe_redirect_back(request, "properties:detail", pk=prop.pk)

    prop.latitude = lat
    prop.longitude = lng
    prop.coords_validated = True
    prop.coords_validated_at = timezone.now()
    prop.coords_validated_by = request.user
    prop.save(update_fields=[
        "latitude",
        "longitude",
        "coords_validated",
        "coords_validated_at",
        "coords_validated_by",
    ])

    messages.success(request, "Address validated and coordinates locked.")
    return _safe_redirect_back(request, "properties:detail", pk=prop.pk)


class PropertyListView(ListView):
    model = Property
    template_name = "properties/property_list.html"
    context_object_name = "items"

    def get_queryset(self):
        qs = Property.objects.select_related("customer").order_by("site_id")

        q = (self.request.GET.get("q") or "").strip()
        validated = (self.request.GET.get("validated") or "").strip()

        if q:
            qs = qs.filter(
                Q(site_id__icontains=q)
                | Q(building_name__icontains=q)
                | Q(street__icontains=q)
                | Q(city__icontains=q)
                | Q(customer__customer_name__icontains=q)
            )

        # ✅ Validation filter:
        #   validated=1 -> only validated
        #   validated=0 -> only unvalidated
        if validated == "1":
            qs = qs.filter(coords_validated=True)
        elif validated == "0":
            qs = qs.filter(coords_validated=False)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "")
        context["validated"] = self.request.GET.get("validated", "")
        return context


class PropertyDetailView(DetailView):
    model = Property
    template_name = "properties/property_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "details"
        context["tab_counts"] = build_property_tab_counts(self.object)
        return context


class PropertyQuotationsView(DetailView):
    model = Property
    template_name = "properties/property_quotations.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "quotations"
        context["quotations"] = Quotation.objects.filter(site_id=self.object.pk).order_by("-id")
        context["tab_counts"] = build_property_tab_counts(self.object)
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
        context["tab_counts"] = build_property_tab_counts(self.object)
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
        context["tab_counts"] = build_property_tab_counts(self.object)

        assets = (
            self.object.site_assets.all()
            .order_by("asset_label", "location", "level", "block", "id")
        )
        context["assets"] = assets

        context["assetcode_ct_id"] = ContentType.objects.get_for_model(AssetCode).id

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

        context["asset_codes"] = (
            AssetCode.objects.filter(is_active=True)
            .select_related("category", "equipment")
            .order_by("code")
        )

        context["asset_field_payload"] = _build_asset_field_payload()

        equipment_ids = list(
            context["asset_equipment"].values_list("id", flat=True)
        ) if context["asset_equipment"] is not None else []

        context["equipment_optional_map"] = _build_equipment_optional_map(equipment_ids)

        # ✅ Add asset-code keyed map for optional fields
        context["asset_code_optional_map"] = {
            str(ac.id): context["equipment_optional_map"].get(str(ac.equipment_id), {})
            for ac in context["asset_codes"]
        }

        asset_ids = list(assets.values_list("id", flat=True))
        history_map: dict[str, list[dict]] = {}
        if asset_ids:
            links = (
                JobTaskAssetLink.objects
                .filter(property_asset_id__in=asset_ids)
                .select_related("job_task", "job_task__parent_job")
                .order_by("-job_task__service_date", "-created_at")
            )
            for link in links:
                jt = link.job_task
                if not jt:
                    continue
                root_job = jt.parent_job if jt.parent_job_id else jt
                service_date = root_job.service_date or jt.service_date

                rows = history_map.setdefault(str(link.property_asset_id), [])
                if any(r.get("job_task_id") == root_job.pk for r in rows):
                    continue

                rows.append(
                    {
                        "job_task_id": root_job.pk,
                        "title": root_job.title or "",
                        "service_date": service_date.isoformat() if service_date else "",
                    }
                )

        for asset in assets:
            asset.history_count = len(history_map.get(str(asset.pk), []))

        context["asset_history_map"] = history_map

        return context


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def edit_property_asset(request, pk: int, asset_id: int):
    prop = get_object_or_404(Property, pk=pk)
    asset = get_object_or_404(PropertyAsset, pk=asset_id, property=prop)

    if request.method == "POST":
        form = PropertyAssetForm(request.POST, instance=asset)
        if form.is_valid():
            form.save()
            messages.success(request, "Asset updated.")

            next_url = (request.POST.get("next") or "").strip()
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)

            return _safe_redirect_back(request, "properties:assets", pk=prop.pk)
    else:
        form = PropertyAssetForm(instance=asset)

    dynamic_field_items = []
    for f in form.dynamic_fields():
        name = f.get("name")
        label = f.get("label")
        if name and name in form.fields:
            dynamic_field_items.append({"label": label, "field": form[name]})

    context = {
        "object": prop,
        "asset": asset,
        "form": form,
        "tab": "assets",
        "tab_counts": build_property_tab_counts(prop),
        "next": (request.GET.get("next") or "").strip(),
        "dynamic_field_items": dynamic_field_items,
    }
    return render(request, "properties/property_asset_edit.html", context)


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def add_property_asset(request, pk: int):
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
    main_image = request.FILES.get("main_image")
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
            main_image=main_image,
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
def toggle_property_asset_active(request, pk: int, asset_id: int):
    prop = get_object_or_404(Property, pk=pk)
    asset = get_object_or_404(PropertyAsset, pk=asset_id, property=prop)

    is_active = (request.POST.get("is_active") or "") == "1"
    asset.is_active = is_active
    asset.save(update_fields=["is_active"])

    state = "active" if is_active else "inactive"
    messages.success(request, f"Asset marked {state}.")
    return _safe_redirect_back(request, "properties:assets", pk=prop.pk)


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def bulk_delete_routines(request, pk: int):
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

    def get_initial(self):
        initial = super().get_initial()
        customer_id = (self.request.GET.get("customer") or "").strip()

        if customer_id.isdigit():
            customer = Customer.objects.filter(pk=int(customer_id)).first()
            if customer:
                initial["customer"] = customer

        return initial

    def form_valid(self, form):
        customer_id = (self.request.GET.get("customer") or "").strip()
        if customer_id.isdigit() and not form.instance.customer_id:
            customer = Customer.objects.filter(pk=int(customer_id)).first()
            if customer:
                form.instance.customer = customer

        return super().form_valid(form)

    def get_success_url(self):
        customer_id = (self.request.GET.get("customer") or "").strip()
        if customer_id.isdigit():
            return reverse("customers:detail", args=[int(customer_id)])
        return super().get_success_url()


class PropertyUpdateView(UpdateView):
    model = Property
    form_class = PropertyForm
    template_name = "properties/property_form.html"
    success_url = reverse_lazy("properties:list")


class PropertyDeleteView(DeleteView):
    model = Property
    template_name = "properties/property_confirm_delete.html"
    success_url = reverse_lazy("properties:list")
