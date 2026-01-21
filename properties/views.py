from django.db.models import Q
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)
from django.urls import reverse_lazy

from .models import Property
from .forms import PropertyForm

# These imports assume your models are named like this.
# If your model names differ, tell me and I'll adjust.
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
        # Used by your tabs in the template
        context["tab"] = "details"
        return context


class PropertyQuotationsView(DetailView):
    model = Property
    template_name = "properties/property_quotations.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "quotations"
        context["quotations"] = Quotation.objects.filter(property=self.object).order_by("-id")
        return context


class PropertyRoutinesView(DetailView):
    model = Property
    template_name = "properties/property_routines.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "routines"
        context["routines"] = ServiceRoutine.objects.filter(site=self.object).order_by("-id")
        return context


class PropertyCreateView(CreateView):
    model = Property
    form_class = PropertyForm
    template_name = "properties/property_form.html"
    success_url = reverse_lazy("properties:list")


# --- replace ONLY these two classes in properties/views.py ---

class PropertyQuotationsView(DetailView):
    model = Property
    template_name = "properties/property_quotations.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "quotations"

        # Safest approach: filter by property_id if field is FK named "property"
        try:
            context["quotations"] = (
                Quotation.objects.filter(property_id=self.object.pk).order_by("-id")
            )
        except Exception:
            # Fallback: if your FK isn't named "property", avoid a 500
            context["quotations"] = Quotation.objects.none()

        return context


class PropertyRoutinesView(DetailView):
    model = Property
    template_name = "properties/property_routines.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "routines"

        # Your current code uses site=self.object, which likely doesn't match your model field.
        # Try common field names safely, otherwise return empty queryset (no 500).
        for field_name in ("property", "site", "building"):
            try:
                context["routines"] = (
                    ServiceRoutine.objects.filter(**{f"{field_name}_id": self.object.pk})
                    .order_by("-id")
                )
                break
            except Exception:
                context["routines"] = ServiceRoutine.objects.none()

        return context
