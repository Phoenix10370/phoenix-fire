from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Max, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from properties.models import Property, PropertyAsset
from codes.models import DropdownList, DropdownOption, AssetCode, AssetField

from .forms import JobTaskAddItemForm, JobTaskForm
from .models import JobTask, JobTaskItem


def _money_2dp(value) -> Decimal:
    if value is None:
        value = Decimal("0")
    if not isinstance(value, Decimal):
        try:
            value = Decimal(str(value))
        except Exception:
            value = Decimal("0")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _next_sort_order(job_task: JobTask) -> int:
    m = job_task.items.aggregate(m=Max("sort_order"))["m"]
    return (m or 0) + 1


def _normalize_item_sort_orders(job_task: JobTask) -> None:
    items = list(job_task.items.order_by("sort_order", "id"))
    for idx, it in enumerate(items, start=1):
        if it.sort_order != idx:
            it.sort_order = idx
            it.save(update_fields=["sort_order"])


def _edit_url_with_anchor(job_task: JobTask, anchor: str = "job-details") -> str:
    return redirect("job_tasks:edit", pk=job_task.pk).url + f"#{anchor}"


def _extract_attributes_from_post(post_data):
    """
    Matches the Property flow:
      - attributes_json: JSON dict string (optional)
      - attr__<slug>=<value> fields (preferred from dynamic UI)

    Returns a dict safe to store in PropertyAsset.attributes
    """
    raw_json = (post_data.get("attributes_json") or "").strip()
    if raw_json:
        try:
            import json

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


def _find_list_for_field(field: AssetField):
    qs = DropdownList.objects.filter(is_active=True)

    dl = qs.filter(slug=field.slug).first()
    if dl:
        return dl
    dl = qs.filter(slug__icontains=field.slug).first()
    if dl:
        return dl

    dl = qs.filter(name__iexact=field.label).first()
    if dl:
        return dl
    return qs.filter(name__icontains=field.label).first()


def _build_asset_field_payload():
    """
    Build payload describing which AssetFields exist and whether they have dropdown options.
    Used to render dynamic optional fields in the Job Task -> Property Assets tab.
    """
    payload = []
    for f in AssetField.objects.filter(is_active=True).order_by("label"):
        dl = _find_list_for_field(f)
        if dl:
            opts = list(
                DropdownOption.objects.filter(dropdown_list=dl, is_active=True)
                .order_by("label")
                .values_list("value", "label")
            )
        else:
            opts = []

        payload.append(
            {
                "slug": f.slug,
                "label": f.label,
                "has_dropdown": bool(opts),
                "options": opts,  # list of (value, label)
            }
        )
    return payload


def jobtask_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = JobTask.objects.select_related("site", "customer", "service_routine").order_by("-created_at")

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(site__full_address__icontains=q))

    return render(request, "job_tasks/jobtask_list.html", {"q": q, "job_tasks": qs})


def jobtask_list_for_property(request, property_id: int):
    property_obj = get_object_or_404(Property, pk=property_id)
    qs = (
        JobTask.objects.select_related("site", "customer", "service_routine")
        .filter(site=property_obj)
        .order_by("-created_at")
    )

    context = {
        "object": property_obj,
        "property": property_obj,
        "job_tasks": qs,
        "tab": "job_tasks",
    }
    return render(request, "job_tasks/jobtask_list_for_property.html", context)


def jobtask_detail(request, pk: int):
    job_task = get_object_or_404(
        JobTask.objects.select_related("site", "customer", "service_routine")
        .prefetch_related("items", "additional_technicians", "property_assets"),
        pk=pk,
    )

    value = Decimal("0.00")
    for it in job_task.items.all():
        value += _money_2dp(it.line_total)

    gst_rate = getattr(settings, "GST_RATE", Decimal("0.10"))
    gst = _money_2dp(value * Decimal(str(gst_rate)))
    total_value = _money_2dp(value + gst)

    # --- Property Assets tab context ---
    linked_ids = set(job_task.property_assets.values_list("id", flat=True))

    available_property_assets = []
    if job_task.site_id:
        available_property_assets = (
            PropertyAsset.objects.filter(property_id=job_task.site_id)
            .exclude(id__in=linked_ids)
            .order_by("asset_label", "location", "level", "block", "id")
        )

    # Dropdowns for adding a new asset from the job task
    categories_list = _get_dropdown_list("Asset Categories")
    equipment_list = _get_dropdown_list("Asset Equipment")

    asset_categories = (
        DropdownOption.objects.filter(dropdown_list=categories_list, is_active=True).order_by("label")
        if categories_list else DropdownOption.objects.none()
    )
    asset_equipment = (
        DropdownOption.objects.filter(dropdown_list=equipment_list, is_active=True)
        .select_related("parent")
        .order_by("label")
        if equipment_list else DropdownOption.objects.none()
    )

    asset_codes = (
        AssetCode.objects.filter(is_active=True)
        .select_related("category", "equipment")
        .order_by("code")
    )

    assetcode_ct_id = ContentType.objects.get_for_model(AssetCode).id
    asset_field_payload = _build_asset_field_payload()

    return render(
        request,
        "job_tasks/jobtask_detail.html",
        {
            "job_task": job_task,
            "value": value,
            "gst": gst,
            "total_value": total_value,

            # Property Assets tab
            "available_property_assets": available_property_assets,
            "assetcode_ct_id": assetcode_ct_id,
            "asset_categories": asset_categories,
            "asset_equipment": asset_equipment,
            "asset_codes": asset_codes,
            "asset_field_payload": asset_field_payload,
            "categories_list": categories_list,
            "equipment_list": equipment_list,
        },
    )


@transaction.atomic
def jobtask_link_property_assets(request, pk: int):
    """
    Link existing PropertyAssets (owned by the property) to this JobTask.

    POST:
      - asset_ids: list of PropertyAsset ids to link
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask.objects.select_related("site"), pk=pk)

    if not job_task.site_id:
        messages.error(request, "This job task has no property linked.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    asset_ids = request.POST.getlist("asset_ids")
    asset_ids = [aid for aid in asset_ids if str(aid).strip().isdigit()]
    if not asset_ids:
        messages.warning(request, "No assets selected.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    # Only allow linking assets that belong to this property
    qs = PropertyAsset.objects.filter(property_id=job_task.site_id, id__in=asset_ids)

    count = 0
    for pa in qs:
        job_task.property_assets.add(pa)
        count += 1

    messages.success(request, f"Linked {count} asset(s) to this job task.")
    return redirect("job_tasks:detail", pk=job_task.pk)


@transaction.atomic
def jobtask_unlink_property_asset(request, pk: int, asset_id: int):
    """
    Unlink a PropertyAsset from a JobTask.
    Does NOT delete the PropertyAsset.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask.objects.select_related("site"), pk=pk)

    # Ensure the asset exists and belongs to the same property (safety)
    asset = get_object_or_404(PropertyAsset, pk=asset_id)

    if job_task.site_id and asset.property_id and job_task.site_id != asset.property_id:
        messages.error(request, "That asset belongs to a different property.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    if not job_task.property_assets.filter(pk=asset_id).exists():
        messages.warning(request, "Asset not linked to this job task.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    job_task.property_assets.remove(asset_id)

    messages.success(request, "Asset unlinked from this job task.")
    return redirect("job_tasks:detail", pk=job_task.pk)


@transaction.atomic
def jobtask_add_property_asset(request, pk: int):
    """
    Add an asset from within the JobTask tab.

    Behaviour:
    - Creates a PropertyAsset (owned by the JobTask's property)
    - Links it to the JobTask

    POST (minimum):
      - asset_code_id (required)
      - asset_code_ct_id (hidden) should be codes.AssetCode CT id

    Optional:
      - block, level, location
      - attr__<slug>=value (dynamic optional fields)
      - attributes_json (fallback)
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask.objects.select_related("site"), pk=pk)

    if not job_task.site_id:
        messages.error(request, "This job task has no property linked. Link a property first.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    asset_code_id = (request.POST.get("asset_code_id") or "").strip()
    if not asset_code_id.isdigit():
        messages.error(request, "Please select a valid Asset Code.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    # Validate ContentType is AssetCode
    ct_id = (request.POST.get("asset_code_ct_id") or "").strip()
    assetcode_ct = ContentType.objects.get_for_model(AssetCode)
    if not (ct_id.isdigit() and int(ct_id) == assetcode_ct.id):
        messages.error(request, "Invalid asset library reference.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    asset_code = get_object_or_404(AssetCode, pk=int(asset_code_id))

    block = (request.POST.get("block") or "").strip()
    level = (request.POST.get("level") or "").strip()
    location = (request.POST.get("location") or "").strip()
    attributes = _extract_attributes_from_post(request.POST)

    prop_asset = PropertyAsset.objects.create(
        property=job_task.site,
        asset_code_content_type=assetcode_ct,
        asset_code_object_id=asset_code.pk,
        asset_label=str(asset_code),
        block=block,
        level=level,
        location=location,
        attributes=attributes or {},
    )

    job_task.property_assets.add(prop_asset)

    messages.success(request, "Asset added and linked to this job task.")
    return redirect("job_tasks:detail", pk=job_task.pk)


@transaction.atomic
def jobtask_create(request):
    if request.method == "POST":
        form = JobTaskForm(request.POST)
        if form.is_valid():
            job_task = form.save()
            messages.success(request, "Job Task created. You can now add Job Details items.")
            return redirect("job_tasks:edit", pk=job_task.pk)
    else:
        form = JobTaskForm()

    return render(
        request,
        "job_tasks/jobtask_form.html",
        {
            "form": form,
            "mode": "create",
            "job_task": None,
            "items": [],
            "add_item_form": JobTaskAddItemForm(),
            "value": Decimal("0.00"),
            "gst": Decimal("0.00"),
            "total_value": Decimal("0.00"),
        },
    )


@transaction.atomic
def jobtask_update(request, pk: int):
    job_task = get_object_or_404(JobTask, pk=pk)

    if request.method == "POST":
        form = JobTaskForm(request.POST, instance=job_task)
        if form.is_valid():
            job_task = form.save()

            if job_task.service_date and not job_task.service_technician:
                messages.warning(request, "You must allocate a technician for this job")

            messages.success(request, "Job Task updated.")
            return redirect(_edit_url_with_anchor(job_task))
    else:
        form = JobTaskForm(instance=job_task)

    _normalize_item_sort_orders(job_task)
    items = list(job_task.items.order_by("sort_order", "id"))

    value = Decimal("0.00")
    for it in items:
        value += _money_2dp(it.line_total)

    gst_rate = getattr(settings, "GST_RATE", Decimal("0.10"))
    gst = _money_2dp(value * Decimal(str(gst_rate)))
    total_value = _money_2dp(value + gst)

    return render(
        request,
        "job_tasks/jobtask_form.html",
        {
            "form": form,
            "mode": "update",
            "job_task": job_task,
            "items": items,
            "add_item_form": JobTaskAddItemForm(),
            "value": value,
            "gst": gst,
            "total_value": total_value,
        },
    )


def jobtask_delete(request, pk: int):
    job_task = get_object_or_404(JobTask, pk=pk)

    if request.method == "POST":
        job_task.delete()
        messages.success(request, "Job Task deleted.")
        return redirect("job_tasks:list")

    return render(request, "job_tasks/jobtask_confirm_delete.html", {"job_task": job_task})


@transaction.atomic
def jobtask_item_add(request, pk: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask, pk=pk)

    form = JobTaskAddItemForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not add item. Please check the fields.")
        return redirect(_edit_url_with_anchor(job_task))

    code = (form.cleaned_data.get("code") or "").strip()
    desc = (form.cleaned_data.get("custom_description") or "").strip()

    JobTaskItem.objects.create(
        job_task=job_task,
        sort_order=_next_sort_order(job_task),
        code=code,
        description=desc,
        quantity=form.cleaned_data["quantity"],
        unit_price=form.cleaned_data["unit_price"],
    )

    messages.success(request, "Item added.")
    return redirect(_edit_url_with_anchor(job_task))


@transaction.atomic
def jobtask_item_delete(request, pk: int, item_id: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask, pk=pk)
    item = get_object_or_404(JobTaskItem, pk=item_id, job_task=job_task)
    item.delete()
    _normalize_item_sort_orders(job_task)

    messages.success(request, "Item removed.")
    return redirect(_edit_url_with_anchor(job_task))


@transaction.atomic
def jobtask_item_move(request, pk: int, item_id: int, direction: str):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask, pk=pk)
    item = get_object_or_404(JobTaskItem, pk=item_id, job_task=job_task)

    _normalize_item_sort_orders(job_task)
    items = list(job_task.items.order_by("sort_order", "id"))

    idx = next((i for i, it in enumerate(items) if it.id == item.id), None)
    if idx is None:
        return redirect(_edit_url_with_anchor(job_task))

    if direction == "up" and idx > 0:
        other = items[idx - 1]
    elif direction == "down" and idx < len(items) - 1:
        other = items[idx + 1]
    else:
        return redirect(_edit_url_with_anchor(job_task))

    item.sort_order, other.sort_order = other.sort_order, item.sort_order
    item.save(update_fields=["sort_order"])
    other.save(update_fields=["sort_order"])

    return redirect(_edit_url_with_anchor(job_task))
