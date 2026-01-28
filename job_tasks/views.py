from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from properties.models import Property
from .forms import JobTaskForm
from .models import JobTask


def jobtask_list(request):
    q = (request.GET.get("q") or "").strip()

    qs = (
        JobTask.objects.select_related("site", "customer", "service_routine")
        .order_by("-created_at")
    )

    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(site__full_address__icontains=q)
        )

    context = {
        "q": q,
        "job_tasks": qs,
    }
    return render(request, "job_tasks/jobtask_list.html", context)


def jobtask_list_for_property(request, property_id: int):
    """
    Job Tasks filtered to a single Property.
    NOTE: JobTask uses field name `site` for the property relationship.
    """
    property_obj = get_object_or_404(Property, pk=property_id)

    qs = (
        JobTask.objects.select_related("site", "customer", "service_routine")
        .filter(site=property_obj)
        .order_by("-created_at")
    )

    context = {
        "object": property_obj,   # required by properties/property_tabs_header.html
        "property": property_obj,
        "job_tasks": qs,
        "tab": "job_tasks",       # keeps Job Tasks tab active
    }
    return render(request, "job_tasks/jobtask_list_for_property.html", context)


def jobtask_detail(request, pk: int):
    job_task = get_object_or_404(
        JobTask.objects.select_related("site", "customer", "service_routine"),
        pk=pk,
    )
    return render(request, "job_tasks/jobtask_detail.html", {"job_task": job_task})


def jobtask_create(request):
    if request.method == "POST":
        form = JobTaskForm(request.POST)
        if form.is_valid():
            job_task = form.save()
            messages.success(request, "Job Task created.")
            return redirect("job_tasks:detail", pk=job_task.pk)
    else:
        form = JobTaskForm()

    return render(request, "job_tasks/jobtask_form.html", {"form": form, "mode": "create"})


def jobtask_update(request, pk: int):
    job_task = get_object_or_404(JobTask, pk=pk)

    if request.method == "POST":
        form = JobTaskForm(request.POST, instance=job_task)
        if form.is_valid():
            job_task = form.save()
            messages.success(request, "Job Task updated.")
            return redirect("job_tasks:detail", pk=job_task.pk)
    else:
        form = JobTaskForm(instance=job_task)

    return render(
        request,
        "job_tasks/jobtask_form.html",
        {"form": form, "mode": "update", "job_task": job_task},
    )


def jobtask_delete(request, pk: int):
    job_task = get_object_or_404(JobTask, pk=pk)

    if request.method == "POST":
        job_task.delete()
        messages.success(request, "Job Task deleted.")
        return redirect("job_tasks:list")

    return render(request, "job_tasks/jobtask_confirm_delete.html", {"job_task": job_task})
