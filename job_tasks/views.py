from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Max, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from properties.models import Property
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
        .prefetch_related("items", "additional_technicians"),
        pk=pk,
    )

    value = Decimal("0.00")
    for it in job_task.items.all():
        value += _money_2dp(it.line_total)

    gst_rate = getattr(settings, "GST_RATE", Decimal("0.10"))
    gst = _money_2dp(value * Decimal(str(gst_rate)))
    total_value = _money_2dp(value + gst)

    return render(
        request,
        "job_tasks/jobtask_detail.html",
        {"job_task": job_task, "value": value, "gst": gst, "total_value": total_value},
    )


@transaction.atomic
def jobtask_create(request):
    if request.method == "POST":
        form = JobTaskForm(request.POST)
        if form.is_valid():
            job_task = form.save()
            messages.success(request, "Job Task created. You can now add Job Details items.")
            # go to edit screen so user can add items immediately
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

            # ✅ warning if service date set but no technician
            if job_task.service_date and not job_task.service_technician:
                messages.warning(request, "You must allocate a technician for this job")

            messages.success(request, "Job Task updated.")
            # ✅ return user to Job Details area (bottom)
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
