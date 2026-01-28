from django.views.generic import DetailView

from .models import Property


class PropertyAssetsView(DetailView):
    model = Property
    template_name = "properties/property_assets.html"

    def get_queryset(self):
        return Property.objects.select_related("customer")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "assets"
        return context


class PropertyKeyContactView(DetailView):
    model = Property
    template_name = "properties/property_key_contact.html"

    def get_queryset(self):
        return Property.objects.select_related("customer")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "key_contact"
        return context


class PropertyCorrespondenceView(DetailView):
    model = Property
    template_name = "properties/property_correspondence.html"

    def get_queryset(self):
        return Property.objects.select_related("customer")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tab"] = "correspondence"
        return context
