from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, UpdateView, DeleteView

from quotations.models import Quotation
from .forms import CreateServiceRoutinesFromQuotationForm
from .models import ServiceRoutine, ServiceRoutineItem
from .services import create_service_routines_from_quotation, cascade_update_routine_months_for_quotation


# =========================
# LIST VIEW (Full list for live filtering)
# =========================
class ServiceRoutineListView(LoginRequiredMixin, ListView):
    model = ServiceRoutine
    template_name = "routines/service_routine_list.html"
    context_object_name = "routines"
    paginate_by = None  # full list for client-side live filtering

    def get_queryset(self):
        return (
            ServiceRoutine.objects
            .select_related("quotation", "site", "site__customer")
            .prefetch_related("items")
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
def create_from_quotation(request, quotation_id: int):
    quotation = get_object_or_404(Quotation, pk=quotation_id)

    if quotation.status != "accepted":
        messages.error(request, "Quotation must be accepted before creating service routines.")
        return redirect("quotations:detail", pk=quotation.pk)

    if quotation.service_routines.exists():
        messages.info(request, "Service routines already exist for this quotation.")
        return redirect("quotations:detail", pk=quotation.pk)

    if request.method == "POST":
        form = CreateServiceRoutinesFromQuotationForm(request.POST)
        if form.is_valid():
            create_service_routines_from_quotation(
                quotation=quotation,
                annual_due_month=int(form.cleaned_data["annual_due_month"]),
                user=request.user,
            )
            messages.success(request, "Service routines created.")
            return redirect("quotations:detail", pk=quotation.pk)
    else:
        form = CreateServiceRoutinesFromQuotationForm()

    return render(
        request,
        "routines/create_from_quotation.html",
        {
            "quotation": quotation,
            "form": form,
        },
    )


# =========================
# DETAIL VIEW
# =========================
@login_required
def detail(request, pk: int):
    routine = get_object_or_404(
        ServiceRoutine.objects.select_related("quotation", "site", "site__customer").prefetch_related(
            Prefetch(
                "items",
                queryset=ServiceRoutineItem.objects.select_related("efsm_code"),
            )
        ),
        pk=pk,
    )

    month_choices = ServiceRoutine._meta.get_field("month_due").choices

    return render(
        request,
        "routines/detail.html",
        {
            "routine": routine,
            "month_choices": month_choices,
        },
    )


# =========================
# INLINE MONTH UPDATE (Detail page)
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
# EDIT VIEW (full edit form)
# =========================
class ServiceRoutineUpdateView(LoginRequiredMixin, UpdateView):
    model = ServiceRoutine
    fields = ["name", "month_due", "notes", "work_order_number"]
    template_name = "routines/service_routine_form.html"

    def get_success_url(self):
        messages.success(self.request, "Service routine updated.")
        return reverse_lazy("routines:detail", kwargs={"pk": self.object.pk})


# =========================
# DELETE VIEW
# =========================
class ServiceRoutineDeleteView(LoginRequiredMixin, DeleteView):
    model = ServiceRoutine
    template_name = "routines/service_routine_confirm_delete.html"
    success_url = reverse_lazy("routines:list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Service routine deleted.")
        return super().delete(request, *args, **kwargs)
