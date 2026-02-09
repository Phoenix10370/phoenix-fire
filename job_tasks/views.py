# job_tasks/views.py
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Max, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.encoding import iri_to_uri

from properties.models import Property, PropertyAsset
from properties.utils import build_property_tab_counts
from codes.models import DropdownList, DropdownOption, AssetCode, AssetField, EquipmentOptionalField

from .forms import JobTaskAddItemForm, JobTaskForm, JobTaskItemFormSet
from .models import JobTask, JobTaskItem, JobTaskAssetLink, JobTaskAssetImage, JobTaskAssetResult

User = get_user_model()


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


def _detail_url_with_anchor(job_task: JobTask, anchor: str = "tab-assets") -> str:
    return redirect("job_tasks:detail", pk=job_task.pk).url + f"#{anchor}"


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


def _build_equipment_optional_map(equipment_ids: list[int]) -> dict:
    """
    JSON-safe structure for template rendering.
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

        out.setdefault(eq_key, {})[field_slug] = cleaned

    return out


def _build_asset_field_payload():
    """
    Build payload describing all AssetField rows.
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


# =========================
# BULK ACTIONS (LIST PAGE)
# =========================
@require_http_methods(["POST"])
@transaction.atomic
def bulk_action(request):
    """
    Bulk actions for job tasks list.
    action:
      - delete
    """
    action = (request.POST.get("action") or "").strip()
    ids = request.POST.getlist("job_task_ids")

    # Normalize ids to ints safely
    job_task_ids = []
    for raw in ids:
        try:
            job_task_ids.append(int(raw))
        except (TypeError, ValueError):
            continue

    if not job_task_ids:
        messages.error(request, "No job tasks selected.")
        return redirect("job_tasks:list")

    qs = JobTask.objects.filter(pk__in=job_task_ids)

    if action == "delete":
        count = qs.count()
        qs.delete()
        messages.success(request, f"Deleted {count} job task(s).")
        return redirect("job_tasks:list")

    messages.error(request, "Invalid bulk action.")
    return redirect("job_tasks:list")


def jobtask_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = JobTask.objects.select_related(
        "site",
        "customer",
        "service_routine",
        "parent_job",
    ).order_by("-created_at")

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(site__full_address__icontains=q))

    return render(request, "job_tasks/jobtask_list.html", {"q": q, "job_tasks": qs})


def jobtask_list_for_property(request, property_id: int):
    property_obj = get_object_or_404(Property, pk=property_id)
    qs = (
        JobTask.objects.select_related(
            "site",
            "customer",
            "service_routine",
            "parent_job",
        )
        .filter(site=property_obj)
        .order_by("-created_at")
    )

    context = {
        "object": property_obj,
        "property": property_obj,
        "job_tasks": qs,
        "tab": "job_tasks",
        "tab_counts": build_property_tab_counts(property_obj),
    }
    return render(request, "job_tasks/jobtask_list_for_property.html", context)


def jobtask_detail(request, pk: int):
    # NOTE: assets are shared across related jobs via the parent/root job.
    job_task = get_object_or_404(
        JobTask.objects.select_related(
            "site",
            "customer",
            "service_routine",
            "parent_job",
        ).prefetch_related(
            "items",
            "additional_technicians",
            "property_assets",
        ),
        pk=pk,
    )
    shared_job = job_task.root_job
    parent_job = job_task.parent_job if job_task.parent_job_id else job_task

    # --------------------------
    # Measures + invoicing rules
    # --------------------------
    # Measures should be shown for ALL associated jobs -> always use root job items
    measure_job = shared_job
    measure_items = JobTaskItem.objects.filter(job_task=measure_job).order_by("sort_order", "id")

    # Only the original/root job retains invoicing values
    is_root_job = (job_task.pk == shared_job.pk)

    value = Decimal("0.00")
    if is_root_job:
        for it in measure_items:
            value += _money_2dp(it.line_total)

    gst_rate = getattr(settings, "GST_RATE", Decimal("0.10"))
    gst = _money_2dp(value * Decimal(str(gst_rate)))
    total_value = _money_2dp(value + gst)

    # --- Property Assets tab context ---
    linked_assets_qs = list(shared_job.property_assets.all())
    asset_ids = [a.id for a in linked_assets_qs]

    # NEW: available property assets not already linked
    if job_task.site_id:
        available_property_assets = (
            PropertyAsset.objects
            .filter(property_id=job_task.site_id, is_active=True)
            .exclude(id__in=asset_ids)
            .order_by("asset_label", "location", "level", "block", "id")
        )
    else:
        available_property_assets = []

    link_qs = JobTaskAssetLink.objects.filter(
        job_task=shared_job,
        property_asset_id__in=asset_ids,
    ).select_related("property_asset")

    link_map = {l.property_asset_id: l for l in link_qs}

    def _is_access_asset(a):
        return _asset_code_value(a) == "ASSET-0065"

    linked_assets = [
        {
            "asset": a,
            "link": link_map.get(a.id),
            "is_access": _is_access_asset(a),
            "result_for_job": (link_map.get(a.id).result if link_map.get(a.id) else ""),
        }
        for a in linked_assets_qs
    ]
    inspected_count = sum(1 for row in linked_assets if row.get("result_for_job"))

    history_map = {}
    history_qs = (
        JobTaskAssetLink.objects.filter(property_asset_id__in=asset_ids)
        .select_related("job_task")
        .order_by("-job_task__service_date", "-created_at")
    )
    for l in history_qs:
        jt = l.job_task
        history_map.setdefault(str(l.property_asset_id), []).append(
            {
                "job_task_id": l.job_task_id,
                "title": jt.title if jt else "",
                "service_date": jt.service_date.isoformat() if jt and jt.service_date else "",
                "result": l.result or "",
            }
        )

    categories_list = _get_dropdown_list("Asset Categories")
    equipment_list = _get_dropdown_list("Asset Equipment")

    asset_categories = (
        DropdownOption.objects.filter(dropdown_list=categories_list, is_active=True)
        .order_by("label")
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

    equipment_ids = list(asset_equipment.values_list("id", flat=True)) if asset_equipment is not None else []
    equipment_optional_map = _build_equipment_optional_map(equipment_ids)

    asset_code_optional_map = {
        str(ac.id): equipment_optional_map.get(str(ac.equipment_id), {})
        for ac in asset_codes
    }

    technician_choices = (
        User.objects.filter(is_active=True)
        .order_by("first_name", "last_name", "username")
    )

    related_jobs = list(
        JobTask.objects.filter(Q(pk=parent_job.pk) | Q(parent_job_id=parent_job.pk))
        .select_related("parent_job")
        .order_by("service_date", "pk")
    )

    total_related_jobs = len(related_jobs)
    current_job_position = 0
    prev_job = None
    next_job = None
    first_job = None
    last_job = None

    if total_related_jobs:
        first_job = related_jobs[0]
        last_job = related_jobs[-1]
        for idx, rel_job in enumerate(related_jobs):
            if rel_job.pk == job_task.pk:
                current_job_position = idx + 1
                if idx > 0:
                    prev_job = related_jobs[idx - 1]
                if idx < total_related_jobs - 1:
                    next_job = related_jobs[idx + 1]
                break

    context = {
        "job_task": job_task,
        "shared_job": shared_job,
        "child_jobs": [],
        "measure_job": measure_job,
        "measure_items": measure_items,
        "is_root_job": is_root_job,
        "value": value,
        "gst": gst,
        "total_value": total_value,
        "available_property_assets": available_property_assets,
        "assetcode_ct_id": ContentType.objects.get_for_model(AssetCode).id,
        "asset_categories": asset_categories,
        "asset_equipment": asset_equipment,
        "asset_codes": asset_codes,
        "asset_field_payload": _build_asset_field_payload(),
        "categories_list": categories_list,
        "equipment_list": equipment_list,
        "equipment_optional_map": equipment_optional_map,
        "asset_code_optional_map": asset_code_optional_map,
        "technician_choices": technician_choices,
        "parent_job": parent_job,
        "sibling_jobs": related_jobs,
        "current_job_position": current_job_position,
        "total_sibling_jobs": total_related_jobs,
        "prev_job": prev_job,
        "next_job": next_job,
        "first_job": first_job,
        "last_job": last_job,
        "linked_assets": linked_assets,
        "asset_history_map": history_map,
        "asset_total_count": len(linked_assets_qs),
        "asset_inspected_count": inspected_count,
    }

    return render(request, "job_tasks/jobtask_detail.html", context)


@transaction.atomic
def jobtask_child_create(request, pk: int):
    """
    Create a child JobTask for a grouped job.

    - Works when called on either a parent or a child:
      it always attaches the new child to the root/parent job.
    - Copies shared fields from the root job.
    - Redirects to edit screen for the new child so user can set date/tech/time.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    base_task = get_object_or_404(
        JobTask.objects.select_related("parent_job", "site", "customer", "service_routine", "service_type"),
        pk=pk,
    )
    parent = base_task.root_job  # ensures we always attach to the true parent

    child = JobTask.objects.create(
        parent_job=parent,
        site=parent.site,
        customer=parent.customer,
        service_routine=parent.service_routine,
        service_type=parent.service_type,
        title=parent.title,
        description=parent.description,

        status="open",
        service_date=None,
        start_time=None,
        finish_time=None,
        is_all_day=False,
        service_time=parent.service_time or "",

        client_acknowledgement="",
        acknowledgement_date=None,
        work_order_no="",
        admin_comments="",

        technician_comments="",
        technician_job_notes="",
    )

    messages.success(request, "Created a new technician/day job. Allocate technician and service date.")
    return redirect("job_tasks:edit", pk=child.pk)


@require_http_methods(["POST"])
@transaction.atomic
def jobtask_children_bulk_create(request, pk: int):
    """
    Bulk-create multiple child JobTasks from the parent/root job in ONE transaction.

    Expects POST lists (same length or ragged; we zip_longest safely):
      - technician_id[]
      - service_date[]
      - start_time[] (HH:MM or HH:MM:SS)
      - finish_time[] (HH:MM or HH:MM:SS)

    Blank rows are skipped. Invalid rows are skipped with a warning count.
    """
    base_task = get_object_or_404(
        JobTask.objects.select_related("parent_job", "site", "customer", "service_routine", "service_type"),
        pk=pk,
    )
    parent = base_task.root_job

    tech_ids = request.POST.getlist("technician_id")
    dates = request.POST.getlist("service_date")
    starts = request.POST.getlist("start_time")
    finishes = request.POST.getlist("finish_time")

    # allow ragged lists safely
    from itertools import zip_longest

    created = 0
    skipped = 0

    # Preload users for validation
    valid_users = {str(u.id): u for u in User.objects.filter(id__in=[t for t in tech_ids if str(t).isdigit()])}

    # Parse date/time safely
    from datetime import datetime

    def _parse_date(v: str):
        v = (v or "").strip()
        if not v:
            return None
        try:
            # HTML date input: YYYY-MM-DD
            return datetime.strptime(v, "%Y-%m-%d").date()
        except Exception:
            return None

    def _parse_time(v: str):
        v = (v or "").strip()
        if not v:
            return None
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(v, fmt).time()
            except Exception:
                continue
        return None

    for tech_id, d, st, ft in zip_longest(tech_ids, dates, starts, finishes, fillvalue=""):
        tech_id = (tech_id or "").strip()
        d = (d or "").strip()
        st = (st or "").strip()
        ft = (ft or "").strip()

        # Skip completely empty row
        if not tech_id and not d and not st and not ft:
            continue

        technician = valid_users.get(tech_id)
        service_date = _parse_date(d)
        start_time = _parse_time(st)
        finish_time = _parse_time(ft)

        # Require technician + date (times optional)
        if not technician or not service_date:
            skipped += 1
            continue

        child = JobTask.objects.create(
            parent_job=parent,
            site=parent.site,
            customer=parent.customer,
            service_routine=parent.service_routine,
            service_type=parent.service_type,
            title=parent.title,
            description=parent.description,

            status="scheduled",
            service_date=service_date,
            start_time=start_time,
            finish_time=finish_time,
            is_all_day=False,

            # keep legacy display field for compatibility; model.save will format it
            service_time=parent.service_time or "",

            service_technician=technician,

            client_acknowledgement="",
            acknowledgement_date=None,
            work_order_no=parent.work_order_no or "",
            admin_comments=parent.admin_comments or "",

            technician_comments="",
            technician_job_notes="",
        )

        # Ensure display formatting and status rules apply
        child.save()

        created += 1

    if created:
        messages.success(request, f"Created {created} technician/day job(s).")
    if skipped:
        messages.warning(request, f"Skipped {skipped} row(s) (missing technician or date).")
    if not created and not skipped:
        messages.warning(request, "No rows provided.")

    return redirect("job_tasks:detail", pk=parent.pk)


@transaction.atomic
def jobtask_link_property_assets(request, pk: int):
    """
    Link existing PropertyAssets (owned by the property) to this JobTask.

    NOTE: Links assets to the shared/root job (parent), so related jobs share the same assets.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask.objects.select_related("site", "parent_job"), pk=pk)
    shared_job = job_task.root_job

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
        shared_job.property_assets.add(pa)
        count += 1

    messages.success(request, f"Linked {count} asset(s) to this job task.")
    return redirect(_detail_url_with_anchor(job_task, "tab-assets"))


@transaction.atomic
def jobtask_unlink_property_asset(request, pk: int, asset_id: int):
    """
    Unlink a PropertyAsset from a JobTask.
    Does NOT delete the PropertyAsset.

    NOTE: Unlinks from the shared/root job (parent), so related jobs share the same assets.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask.objects.select_related("site", "parent_job"), pk=pk)
    shared_job = job_task.root_job

    asset = get_object_or_404(PropertyAsset, pk=asset_id)

    if job_task.site_id and asset.property_id and job_task.site_id != asset.property_id:
        messages.error(request, "That asset belongs to a different property.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    if not shared_job.property_assets.filter(pk=asset_id).exists():
        messages.warning(request, "Asset not linked to this job task.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    shared_job.property_assets.remove(asset_id)

    messages.success(request, "Asset unlinked from this job task.")
    return redirect(_detail_url_with_anchor(job_task))


@transaction.atomic
def jobtask_deactivate_property_asset(request, pk: int, asset_id: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask.objects.select_related("site", "parent_job"), pk=pk)
    shared_job = job_task.root_job

    asset = get_object_or_404(PropertyAsset, pk=asset_id)

    if job_task.site_id and asset.property_id and job_task.site_id != asset.property_id:
        messages.error(request, "That asset belongs to a different property.")
        return redirect(_detail_url_with_anchor(job_task))

    asset.is_active = False
    asset.save(update_fields=["is_active"])

    if shared_job.property_assets.filter(pk=asset_id).exists():
        shared_job.property_assets.remove(asset_id)

    messages.success(request, "Asset marked inactive and removed from this job task.")
    return redirect(_detail_url_with_anchor(job_task, "tab-assets"))


@transaction.atomic
def jobtask_add_property_asset(request, pk: int):
    """
    Add an asset from within the JobTask tab.

    Behaviour:
    - Creates a PropertyAsset (owned by the JobTask's property)
    - Links it to the JobTask (shared/root job for sharing)

    NOTE: Links asset to the shared/root job (parent), so related jobs share the same assets.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask.objects.select_related("site", "parent_job"), pk=pk)
    shared_job = job_task.root_job

    if not job_task.site_id:
        messages.error(request, "This job task has no property linked. Link a property first.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    asset_code_id = (request.POST.get("asset_code_id") or "").strip()
    if not asset_code_id.isdigit():
        messages.error(request, "Please select a valid Asset Code.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    ct_id = (request.POST.get("asset_code_ct_id") or "").strip()
    assetcode_ct = ContentType.objects.get_for_model(AssetCode)
    if not (ct_id.isdigit() and int(ct_id) == assetcode_ct.id):
        messages.error(request, "Invalid asset library reference.")
        return redirect("job_tasks:detail", pk=job_task.pk)

    asset_code = get_object_or_404(AssetCode, pk=int(asset_code_id))

    barcode = (request.POST.get("barcode") or "").strip() or None
    main_image = request.FILES.get("main_image")
    block = (request.POST.get("block") or "").strip()
    level = (request.POST.get("level") or "").strip()
    location = (request.POST.get("location") or "").strip()
    attributes = _extract_attributes_from_post(request.POST)

    try:
        prop_asset = PropertyAsset.objects.create(
            property=job_task.site,
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
    except Exception as exc:
        messages.error(request, f"Could not add asset. {exc}")
        return redirect(_detail_url_with_anchor(job_task))

    shared_job.property_assets.add(prop_asset)

    messages.success(request, "Asset added and linked to this job task.")
    return redirect(_detail_url_with_anchor(job_task))


@transaction.atomic
def jobtask_create(request):
    if request.method == "POST":
        form = JobTaskForm(request.POST)
        if form.is_valid():
            job_task = form.save()
            messages.success(request, "Job Task created.")

            next_url = (request.POST.get("next") or "").strip()
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(iri_to_uri(next_url))
            return redirect("job_tasks:detail", pk=job_task.pk)
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
    job_task = get_object_or_404(JobTask.objects.select_related("parent_job"), pk=pk)

    # Always edit shared/root job measures
    item_owner = job_task.root_job

    if request.method == "POST":
        form = JobTaskForm(request.POST, instance=job_task)
        item_formset = JobTaskItemFormSet(request.POST, instance=item_owner, prefix="items")

        has_formset_data = f"{item_formset.prefix}-TOTAL_FORMS" in request.POST

        if form.is_valid() and (not has_formset_data or item_formset.is_valid()):
            job_task = form.save()

            if has_formset_data:
                item_formset.save()
                _normalize_item_sort_orders(item_owner)

            if job_task.service_date and not job_task.service_technician:
                messages.warning(request, "You must allocate a technician for this job")

            messages.success(request, "Job Task updated.")

            next_url = (request.POST.get("next") or "").strip()
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(iri_to_uri(next_url))
            return redirect("job_tasks:detail", pk=job_task.pk)
    else:
        form = JobTaskForm(instance=job_task)
        item_formset = JobTaskItemFormSet(instance=item_owner, prefix="items")

    _normalize_item_sort_orders(item_owner)
    items = list(item_owner.items.order_by("sort_order", "id"))

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
            "item_formset": item_formset,
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


@transaction.atomic
def jobtask_update_asset_link(request, pk: int, asset_id: int):
    job_task = get_object_or_404(JobTask.objects.select_related("site", "parent_job"), pk=pk)
    shared_job = job_task.root_job

    asset = get_object_or_404(PropertyAsset, pk=asset_id)

    link, _ = JobTaskAssetLink.objects.get_or_create(
        job_task=shared_job,
        property_asset=asset,
    )

    result = (request.POST.get("result") or "").strip()
    if result not in {"pass", "fail", "access", "no_access"}:
        result = ""

    link.result = result
    link.last_updated_job = job_task
    link.save(update_fields=["result", "last_updated_job"])

    if result:
        JobTaskAssetResult.objects.update_or_create(
            job_task=job_task,
            property_asset=asset,
            defaults={"result": result},
        )
    else:
        JobTaskAssetResult.objects.filter(
            job_task=job_task,
            property_asset=asset,
        ).delete()

    remove_ids = [i for i in request.POST.getlist("remove_image_ids") if str(i).isdigit()]
    if remove_ids:
        JobTaskAssetImage.objects.filter(link=link, id__in=remove_ids).delete()

    replace_main = (request.POST.get("replace_main_image") or "") == "1"
    main_image = request.FILES.get("main_image")
    if replace_main and main_image:
        asset.main_image = main_image
        asset.save(update_fields=["main_image"])

    choice = (request.POST.get("main_image_choice") or "").strip().lower()
    uploads = request.FILES.getlist("images")
    if choice == "main" and uploads:
        asset.main_image = uploads[0]
        asset.save(update_fields=["main_image"])
        uploads = uploads[1:]

    for upload in uploads:
        JobTaskAssetImage.objects.create(link=link, image=upload)

    messages.success(request, "Asset results updated.")
    return redirect(_detail_url_with_anchor(job_task))


@transaction.atomic
def jobtask_bulk_update_asset_links(request, pk: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    job_task = get_object_or_404(JobTask.objects.select_related("site", "parent_job"), pk=pk)
    shared_job = job_task.root_job

    assets = list(shared_job.property_assets.all())
    if not assets:
        messages.info(request, "No assets to update.")
        return redirect(_detail_url_with_anchor(job_task))

    link_qs = JobTaskAssetLink.objects.filter(job_task=shared_job, property_asset_id__in=[a.id for a in assets])
    link_map = {l.property_asset_id: l for l in link_qs}

    for asset in assets:
        link = link_map.get(asset.id)
        if not link:
            link = JobTaskAssetLink.objects.create(job_task=shared_job, property_asset=asset)

        result = (request.POST.get(f"result_{asset.id}") or "").strip()
        if result not in {"pass", "fail", "access", "no_access"}:
            result = ""
        dirty = (request.POST.get(f"result_dirty_{asset.id}") or "") == "1"
        changed = False
        if dirty and link.result != result:
            link.result = result
            changed = True

        remove_ids = [i for i in request.POST.getlist(f"remove_image_ids_{asset.id}") if str(i).isdigit()]
        if remove_ids:
            JobTaskAssetImage.objects.filter(link=link, id__in=remove_ids).delete()
            changed = True

        replace_main = (request.POST.get(f"replace_main_image_{asset.id}") or "") == "1"
        main_image = request.FILES.get(f"main_image_{asset.id}")
        if replace_main and main_image:
            asset.main_image = main_image
            asset.save(update_fields=["main_image"])
            changed = True

        choice = (request.POST.get(f"main_image_choice_{asset.id}") or "").strip().lower()
        uploads = request.FILES.getlist(f"images_{asset.id}")
        if choice == "main" and uploads:
            asset.main_image = uploads[0]
            asset.save(update_fields=["main_image"])
            changed = True
            uploads = uploads[1:]

        for upload in uploads:
            JobTaskAssetImage.objects.create(link=link, image=upload)
        if uploads:
            changed = True

        if dirty:
            if result:
                JobTaskAssetResult.objects.update_or_create(
                    job_task=job_task,
                    property_asset=asset,
                    defaults={"result": result},
                )
            else:
                JobTaskAssetResult.objects.filter(
                    job_task=job_task,
                    property_asset=asset,
                ).delete()

        if changed:
            link.last_updated_job = job_task
            update_fields = ["last_updated_job"]
            if dirty:
                update_fields.append("result")
            link.save(update_fields=update_fields)

    messages.success(request, "Asset results updated.")
    return redirect(_detail_url_with_anchor(job_task))


def _asset_code_value(asset):
    for attr in ("asset_code_object", "asset_code"):
        obj = getattr(asset, attr, None)
        if obj:
            code = getattr(obj, "code", None)
            if code:
                return str(code).strip().upper()
    return ""
