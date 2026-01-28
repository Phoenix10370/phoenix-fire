from django.contrib import messages
from django.contrib.auth.decorators import login_required
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

from .models import Property
from .forms import PropertyForm

from quotations.models import Quotation
from routines.models import ServiceRoutine


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
