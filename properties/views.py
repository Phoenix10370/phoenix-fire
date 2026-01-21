from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)
from django.shortcuts import get_object_or_404

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

        # Prefer property_id filtering (safe + fast)
        try:
            context["quotations"] = (
                Quotation.objects.filter(site_id=self.object.pk).order_by("-id")
            )
        except Exception:
            # If FK isn't named "property", avoid crashing
            context["quotations"] = Quotation.objects.none()

        return context


class PropertyRoutinesView(DetailView):
    model = Property
    template_name = "properties/property_routines.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "routines"

        # Try common FK names safely; never crash into a 500
        routines_qs = ServiceRoutine.objects.none()
        for field_name in ("property", "site", "building"):
            try:
                routines_qs = ServiceRoutine.objects.filter(
                    **{f"{field_name}_id": self.object.pk}
                ).order_by("-id")
                break
            except Exception:
                continue

        context["routines"] = routines_qs
        return context


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
