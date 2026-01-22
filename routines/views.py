from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Prefetch
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
)


# =========================
# DELETE ALL ROUTINES FOR A QUOTATION (testing/reset)
# =========================
@login_required
@require_http_methods(["POST"])
def delete_routines_for_quotation(request, quotation_id: int):
    quotation = get_object_or_404(Quotation, pk=quotation_id)

    # Count ONLY ServiceRoutine rows (not cascaded children)
    routine_count = ServiceRoutine.objects.filter(quotation=quotation).count()

    # Delete routines (cascades to items, but we do not report them)
    ServiceRoutine.objects.filter(quotation=quotation).delete()

    messages.success(request, f"Deleted {routine_count} service routine records.")

    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)

    return redirect("quotations:detail", pk=quotation.pk)


# =========================
# LIST VIEW (PUBLIC)
# =========================
class ServiceRoutineListView(ListView):
    model = ServiceRoutine
    template_name = "routines/service_routine_list.html"
    context_object_name = "routines"
    paginate_by = None

    def get_queryset(self):
        return (
            ServiceRoutine.objects
            .select_related("quotation", "site", "site__customer")
            .prefetch_related("items", "items__efsm_code")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["month_choices"] = ServiceRoutine._meta.get_field("month_due").choices
        ctx["type_choices"] = ServiceRoutine._meta.get_field("routine_type").choices
        return ctx


# =========================
# CREATE FROM QUOTATION
# =========================
@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def create_from_quotation(request, quotation_id: int):
    quotation = get_object_or_404(Quotation, pk=quotation_id)

    if quotation.status != "accepted":
        messages.error(request, "Quotation must be accepted before creating service routines.")
        return redirect("quotations:detail", pk=quotation.pk)

    routines_exist = quotation.service_routines.exists()

    if request.method == "POST":
        form = CreateServiceRoutinesFromQuotationForm(request.POST)
        if form.is_valid():
            create_service_routines_from_quotation(
                quotation=quotation,
                annual_due_month=int(form.cleaned_data["annual_due_month"]),
                invoice_frequency=form.cleaned_data["invoice_frequency"],
                user=request.user,
            )
            messages.success(request, "Service routines created or updated.")
            return redirect("quotations:detail", pk=quotation.pk)
    else:
        form = CreateServiceRoutinesFromQuotationForm()

    return render(
        request,
        "routines/create_from_quotation.html",
        {
            "quotation": quotation,
            "form": form,
            "routines_exist": routines_exist,
        },
    )


# =========================
# DETAIL VIEW
# =========================
@login_required
def detail(request, pk: int):
    routine = get_object_or_404(
        ServiceRoutine.objects
        .select_related("quotation", "site", "site__customer")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=ServiceRoutineItem.objects.select_related("efsm_code"),
            )
        ),
        pk=pk,
    )

    # Prev / Next navigation within the same quotation
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

    # Totals (Subtotal / GST / Total)
    subtotal = Decimal("0.00")
    for item in routine.items.all():
        qty = item.quantity or 0
        unit = item.unit_price or Decimal("0.00")
        subtotal += (Decimal(qty) * unit)

    subtotal = subtotal.quantize(Decimal("0.01"))
    gst = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
    total = (subtotal + gst).quantize(Decimal("0.01"))

    # Inline add-item form (routine-only)
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
            "current_index": current_index0 + 1,
            "total_count": total_count,
        },
    )


# =========================
# ADD ROUTINE ITEM (NOT LINKED TO QUOTATION)
# =========================
@login_required
@require_http_methods(["POST"])
def add_item(request, pk: int):
    routine = get_object_or_404(ServiceRoutine, pk=pk)

    form = AddServiceRoutineItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.routine = routine
        item.source_quotation_item = None  # routine-only line
        item.save()
        messages.success(request, "Item added to this service routine.")
    else:
        messages.error(request, "Could not add item. Please check the values.")

    return redirect("routines:detail", pk=routine.pk)


# =========================
# DELETE ROUTINE ITEM
# =========================
@login_required
@require_http_methods(["POST"])
def delete_item(request, pk: int, item_id: int):
    routine = get_object_or_404(ServiceRoutine, pk=pk)
    item = get_object_or_404(ServiceRoutineItem, pk=item_id, routine=routine)

    item.delete()
    messages.success(request, "Item deleted from this service routine.")
    return redirect("routines:detail", pk=routine.pk)


# =========================
# INLINE MONTH UPDATE
# =========================
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


# =========================
# EDIT VIEW
# =========================
class ServiceRoutineUpdateView(LoginRequiredMixin, UpdateView):
    model = ServiceRoutine
    fields = ["name", "month_due", "notes", "work_order_number"]
    template_name = "routines/service_routine_form.html"

    def get_success_url(self):
        messages.success(self.request, "Service routine updated.")
        return reverse_lazy("routines:detail", kwargs={"pk": self.object.pk})


# =========================
# DELETE SINGLE ROUTINE
# =========================
class ServiceRoutineDeleteView(LoginRequiredMixin, DeleteView):
    model = ServiceRoutine
    template_name = "routines/service_routine_confirm_delete.html"
    success_url = reverse_lazy("routines:list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Service routine deleted.")
        return super().delete(request, *args, **kwargs)
