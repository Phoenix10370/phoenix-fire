# routines/views.py
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Prefetch, F, Q
from django.db.models.expressions import OrderBy
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import DeleteView, ListView, UpdateView

from quotations.models import Quotation
from .forms import CreateServiceRoutinesFromQuotationForm, AddServiceRoutineItemForm
from .models import ServiceRoutine, ServiceRoutineItem
from .services import (
    create_service_routines_from_quotation,
    cascade_update_routine_months_for_quotation,
    preview_service_routines_from_quotation,
)

from job_tasks.services import create_job_task_from_routine
from properties.models import PropertyAsset


def _ordered_routine_items_qs():
    # Order by quotation position first; put marker/invoice lines (NULL source) last.
    return (
        ServiceRoutineItem.objects
        .select_related("efsm_code", "source_quotation_item")
        .order_by(
            OrderBy(F("source_quotation_item__position"), nulls_last=True),
            "id",
        )
    )


def _link_existing_property_assets_to_job_task(job_task):
    """
    If the property already has assets, link them to the job task (no duplication).
    If the property has no assets, do nothing.

    This supports:
      - Jobs created from Service Routines
      - Bulk create jobs from routines
    """
    site_id = getattr(job_task, "site_id", None)
    if not site_id:
        return 0

    asset_ids = list(
        PropertyAsset.objects
        .filter(property_id=site_id)
        .values_list("id", flat=True)
    )
    if not asset_ids:
        return 0

    # Uses the M2M through table; unique constraint prevents duplicates
    job_task.property_assets.add(*asset_ids)
    return len(asset_ids)


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def bulk_action(request):
    """
    Bulk actions for routines list.
    action:
      - delete
      - create_job_tasks
    """
    action = (request.POST.get("action") or "").strip()
    ids = request.POST.getlist("routine_ids")

    # Normalize ids to ints safely
    routine_ids = []
    for raw in ids:
        try:
            routine_ids.append(int(raw))
        except (TypeError, ValueError):
            continue

    if not routine_ids:
        messages.error(request, "No routines selected.")
        return redirect("routines:list")

    qs = (
        ServiceRoutine.objects
        .filter(pk__in=routine_ids)
        .select_related("quotation", "site", "site__customer")
        .prefetch_related(Prefetch("items", queryset=_ordered_routine_items_qs()))
        .order_by("id")
    )

    if action == "delete":
        count = qs.count()
        qs.delete()
        messages.success(request, f"Deleted {count} service routine(s).")
        return redirect("routines:list")

    if action == "create_job_tasks":
        created = 0
        for routine in qs:
            job_task = create_job_task_from_routine(routine=routine)
            _link_existing_property_assets_to_job_task(job_task)
            created += 1
        messages.success(request, f"Created {created} Job Task(s) from selected service routines.")
        return redirect("routines:list")

    messages.error(request, "Invalid bulk action.")
    return redirect("routines:list")


@login_required
@require_http_methods(["POST"])
def delete_routines_for_quotation(request, quotation_id: int):
    quotation = get_object_or_404(Quotation, pk=quotation_id)

    routine_count = ServiceRoutine.objects.filter(quotation=quotation).count()
    ServiceRoutine.objects.filter(quotation=quotation).delete()

    messages.success(request, f"Deleted {routine_count} service routine records.")

    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)

    return redirect("quotations:detail", pk=quotation.pk)


class ServiceRoutineListView(ListView):
    model = ServiceRoutine
    template_name = "routines/service_routine_list.html"
    context_object_name = "routines"

    paginate_by = None

    def _get_int_param(self, key: str):
        raw = (self.request.GET.get(key) or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _get_str_param(self, key: str):
        return (self.request.GET.get(key) or "").strip()

    def get_queryset(self):
        qs = (
            ServiceRoutine.objects
            .select_related("quotation", "site", "site__customer")
            .prefetch_related(Prefetch("items", queryset=_ordered_routine_items_qs()))
            .order_by("-created_at")
        )

        q = self._get_str_param("q")
        month = self._get_int_param("month")
        routine_type = self._get_str_param("type")

        if month is not None:
            qs = qs.filter(month_due=month)

        if routine_type:
            try:
                qs = qs.filter(routine_type=int(routine_type))
            except (TypeError, ValueError):
                qs = qs.filter(routine_type=routine_type)

        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(site__building_name__icontains=q)
                | Q(site__street__icontains=q)
                | Q(site__city__icontains=q)
                | Q(site__state__icontains=q)
                | Q(site__post_code__icontains=q)
                | Q(site__customer__customer_name__icontains=q)
                | Q(quotation__number__icontains=q)
            ).distinct()

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["month_choices"] = ServiceRoutine._meta.get_field("month_due").choices
        ctx["type_choices"] = ServiceRoutine._meta.get_field("routine_type").choices
        ctx["q_value"] = self._get_str_param("q")
        ctx["month_value"] = self.request.GET.get("month") or ""
        ctx["type_value"] = self.request.GET.get("type") or ""
        return ctx


@login_required
@require_http_methods(["GET"])
def create_from_quotation_preview(request, quotation_id: int):
    """
    HTMX endpoint: returns ONLY the preview partial.
    No DB writes.
    """
    quotation = get_object_or_404(Quotation, pk=quotation_id)
    routines_exist = quotation.service_routines.exists()

    # If routines exist, preview is irrelevant (creation is blocked)
    if routines_exist:
        form = CreateServiceRoutinesFromQuotationForm()
        return render(
            request,
            "routines/_create_from_quotation_preview.html",
            {
                "preview": [],
                "routines_exist": True,
                "form": form,
            },
        )

    # Read querystring values from the form
    annual_due_month = request.GET.get("annual_due_month") or ""
    invoice_frequency = request.GET.get("invoice_frequency") or "calculator"

    # Fallbacks in case of weird input
    try:
        annual_due_month_int = int(annual_due_month)
    except (TypeError, ValueError):
        annual_due_month_int = 1

    preview = preview_service_routines_from_quotation(
        quotation=quotation,
        annual_due_month=annual_due_month_int,
        invoice_frequency=str(invoice_frequency),
    )

    form = CreateServiceRoutinesFromQuotationForm(initial={
        "annual_due_month": annual_due_month_int,
        "invoice_frequency": str(invoice_frequency),
    })

    return render(
        request,
        "routines/_create_from_quotation_preview.html",
        {
            "preview": preview,
            "routines_exist": False,
            "form": form,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def create_from_quotation(request, quotation_id: int):
    quotation = get_object_or_404(Quotation, pk=quotation_id)

    if quotation.status != "accepted":
        messages.error(request, "Quotation must be accepted before creating service routines.")
        return redirect("quotations:detail", pk=quotation.pk)

    routines_exist = quotation.service_routines.exists()

    # Server-side enforcement: block POST if routines already exist
    if request.method == "POST" and routines_exist:
        messages.error(
            request,
            "Service routines already exist for this quotation. Delete existing routines first to re-create them.",
        )
        return redirect("routines:create_from_quotation", quotation_id=quotation.pk)

    if request.method == "POST":
        form = CreateServiceRoutinesFromQuotationForm(request.POST)
        if form.is_valid():
            create_service_routines_from_quotation(
                quotation=quotation,
                annual_due_month=int(form.cleaned_data["annual_due_month"]),
                invoice_frequency=form.cleaned_data["invoice_frequency"],
                user=request.user,
            )
            messages.success(request, "Service routines created.")
            return redirect("quotations:detail", pk=quotation.pk)
    else:
        form = CreateServiceRoutinesFromQuotationForm()

    # Initial preview for non-HTMX first page load (optional, but nice)
    preview = []
    if not routines_exist:
        initial_month = form.initial.get("annual_due_month") or form.fields["annual_due_month"].choices[0][0]
        initial_freq = form.initial.get("invoice_frequency") or "calculator"
        try:
            initial_month_int = int(initial_month)
        except (TypeError, ValueError):
            initial_month_int = 1

        preview = preview_service_routines_from_quotation(
            quotation=quotation,
            annual_due_month=initial_month_int,
            invoice_frequency=str(initial_freq),
        )

    return render(
        request,
        "routines/create_from_quotation.html",
        {
            "quotation": quotation,
            "form": form,
            "routines_exist": routines_exist,
            "preview": preview,
        },
    )


@login_required
def detail(request, pk: int):
    routine = get_object_or_404(
        ServiceRoutine.objects
        .select_related("quotation", "site", "site__customer")
        .prefetch_related(Prefetch("items", queryset=_ordered_routine_items_qs())),
        pk=pk,
    )

    routines_qs = (
        ServiceRoutine.objects
        .filter(quotation=routine.quotation)
        .order_by("month_due", "id")
    )
    routines_list = list(routines_qs)
    total_count = len(routines_list)

    try:
        current_index0 = routines_list.index(routine)
    except ValueError:
        current_index0 = 0

    prev_routine = routines_list[current_index0 - 1] if current_index0 > 0 else None
    next_routine = routines_list[current_index0 + 1] if current_index0 < total_count - 1 else None

    first_routine = routines_list[0] if routines_list else None
    last_routine = routines_list[-1] if routines_list else None

    subtotal = Decimal("0.00")
    for item in routine.items.all():
        qty = item.quantity or 0
        unit = item.unit_price or Decimal("0.00")
        subtotal += (Decimal(qty) * unit)

    subtotal = subtotal.quantize(Decimal("0.01"))
    gst = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
    total = (subtotal + gst).quantize(Decimal("0.01"))

    add_item_form = AddServiceRoutineItemForm()

    return render(
        request,
        "routines/detail.html",
        {
            "routine": routine,
            "month_choices": ServiceRoutine._meta.get_field("month_due").choices,
            "subtotal": subtotal,
            "gst": gst,
            "total": total,
            "add_item_form": add_item_form,
            "prev_routine": prev_routine,
            "next_routine": next_routine,
            "first_routine": first_routine,
            "last_routine": last_routine,
            "current_index": current_index0 + 1,
            "total_count": total_count,
        },
    )


@login_required
@require_http_methods(["POST"])
def apply_monthly_notes_to_all(request, pk: int):
    routine = get_object_or_404(ServiceRoutine.objects.select_related("quotation"), pk=pk)

    run_val = (request.POST.get("monthly_run_notes") or "").strip()
    week_val = (request.POST.get("monthly_week_notes") or "").strip()

    ServiceRoutine.objects.filter(quotation=routine.quotation).update(
        monthly_run_notes=run_val,
        monthly_week_notes=week_val,
    )

    messages.success(request, "Monthly Run / Monthly Week applied to all related routines.")
    return redirect("routines:detail", pk=routine.pk)


@login_required
@require_http_methods(["POST"])
def create_job_task(request, pk: int):
    routine = get_object_or_404(
        ServiceRoutine.objects.select_related("quotation", "site", "site__customer"),
        pk=pk,
    )

    job_task = create_job_task_from_routine(routine=routine)

    # ✅ Auto-link property assets (if they exist)
    linked = _link_existing_property_assets_to_job_task(job_task)

    if linked:
        messages.success(
            request,
            f"Job Task #{job_task.pk} created from Service Routine #{routine.pk} (linked {linked} property asset(s)).",
        )
    else:
        messages.success(request, f"Job Task #{job_task.pk} created from Service Routine #{routine.pk}.")
    return redirect("job_tasks:detail", pk=job_task.pk)


@login_required
@require_http_methods(["POST"])
def add_item(request, pk: int):
    routine = get_object_or_404(ServiceRoutine, pk=pk)

    form = AddServiceRoutineItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.routine = routine
        item.source_quotation_item = None
        item.save()
        messages.success(request, "Item added to this service routine.")
    else:
        messages.error(request, "Could not add item. Please check the values.")

    return redirect("routines:detail", pk=routine.pk)


@login_required
@require_http_methods(["POST"])
def delete_item(request, pk: int, item_id: int):
    routine = get_object_or_404(ServiceRoutine, pk=pk)
    item = get_object_or_404(ServiceRoutineItem, pk=item_id, routine=routine)

    item.delete()
    messages.success(request, "Item deleted from this service routine.")
    return redirect("routines:detail", pk=routine.pk)


@login_required
@require_http_methods(["POST"])
def update_month_due(request, pk: int):
    routine = get_object_or_404(ServiceRoutine, pk=pk)

    new_month = int(request.POST.get("month_due") or routine.month_due)
    apply_all = (request.POST.get("apply_to_all") or "") == "1"

    old_month = routine.month_due
    if new_month != old_month:
        routine.month_due = new_month
        routine.save(update_fields=["month_due"])

        if apply_all:
            cascade_update_routine_months_for_quotation(
                quotation=routine.quotation,
                new_annual_month=new_month,
                user=request.user,
            )
            messages.success(request, "Service month updated for all related routines.")
        else:
            messages.success(request, "Service month updated.")
    else:
        messages.info(request, "No changes made.")

    return redirect("routines:detail", pk=routine.pk)


class ServiceRoutineUpdateView(LoginRequiredMixin, UpdateView):
    model = ServiceRoutine
    template_name = "routines/service_routine_form.html"

    fields = [
        "month_due",
        "work_order_number",

        "monthly_run_notes",
        "monthly_week_notes",

        "annual_men_req",
        "annual_man_hours",
        "half_yearly_men_req",
        "half_yearly_man_hours",
        "monthly_men_req",
        "monthly_man_hours",

        "quotation_notes",
        "site_notes",
        "technician_notes",
    ]

    def get_success_url(self):
        messages.success(self.request, "Service routine updated.")
        return reverse_lazy("routines:detail", kwargs={"pk": self.object.pk})


class ServiceRoutineDeleteView(LoginRequiredMixin, DeleteView):
    model = ServiceRoutine
    template_name = "routines/service_routine_confirm_delete.html"
    success_url = reverse_lazy("routines:list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Service routine deleted.")
        return super().delete(request, *args, **kwargs)
