# codes/dropdown_views.py  (or whatever this file is named in your app)
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
)

from .models import DropdownList, DropdownOption


# =========================
# DROPDOWN LISTS
# =========================

class DropdownListListView(ListView):
    model = DropdownList
    template_name = "codes/dropdown_list_list.html"
    context_object_name = "items"


class DropdownListCreateView(CreateView):
    model = DropdownList
    fields = ["name", "is_active"]
    template_name = "codes/dropdown_list_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Add Dropdown List"
        ctx["cancel_url"] = reverse_lazy("codes:dropdown_list_list")
        return ctx

    def get_success_url(self):
        return reverse("codes:dropdown_list_list")


class DropdownListUpdateView(UpdateView):
    model = DropdownList
    fields = ["name", "is_active"]
    template_name = "codes/dropdown_list_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Edit Dropdown List"
        ctx["cancel_url"] = reverse_lazy("codes:dropdown_list_list")
        return ctx

    def get_success_url(self):
        return reverse("codes:dropdown_list_list")


class DropdownListDeleteView(DeleteView):
    model = DropdownList
    template_name = "codes/delete.html"
    success_url = reverse_lazy("codes:dropdown_list_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Delete Dropdown List"
        ctx["cancel_url"] = reverse_lazy("codes:dropdown_list_list")
        return ctx


# =========================
# DROPDOWN OPTIONS
# =========================

def _is_categories_list(dropdown_list: DropdownList) -> bool:
    """
    True if this DropdownList is the Asset Categories list.
    """
    name = (dropdown_list.name or "").strip().lower()
    slug = (dropdown_list.slug or "").strip().lower()
    return ("asset categories" in name) or ("asset-categories" in slug)


def _is_equipment_list(dropdown_list: DropdownList) -> bool:
    """
    True if this DropdownList is the Asset Equipment list.
    """
    name = (dropdown_list.name or "").strip().lower()
    slug = (dropdown_list.slug or "").strip().lower()
    return ("asset equipment" in name) or ("asset-equipment" in slug)


def _get_categories_list() -> DropdownList | None:
    """
    Locate Asset Categories list robustly by name/slug.
    """
    qs = DropdownList.objects.filter(is_active=True)
    dl = qs.filter(name__icontains="Asset Categories").first()
    if dl:
        return dl
    return qs.filter(slug__icontains="asset-categories").first()


class DropdownOptionListView(ListView):
    model = DropdownOption
    template_name = "codes/dropdown_option_list.html"
    context_object_name = "items"

    def get_queryset(self):
        return DropdownOption.objects.filter(
            dropdown_list_id=self.kwargs["list_id"]
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["dropdown_list"] = DropdownList.objects.get(pk=self.kwargs["list_id"])
        return ctx


class DropdownOptionCreateView(CreateView):
    model = DropdownOption
    fields = ["label", "parent", "is_active"]
    template_name = "codes/dropdown_option_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        dropdown_list = DropdownList.objects.get(pk=self.kwargs["list_id"])

        # Default: no parent allowed unless explicitly supported
        form.fields["parent"].required = False

        # Asset Categories: categories are top-level, so parent should be disabled/empty
        if _is_categories_list(dropdown_list):
            form.fields["parent"].queryset = DropdownOption.objects.none()
            form.fields["parent"].disabled = True
            return form

        # Asset Equipment: parent should be chosen from Asset Categories (top-level)
        if _is_equipment_list(dropdown_list):
            cat_list = _get_categories_list()
            if cat_list:
                form.fields["parent"].queryset = DropdownOption.objects.filter(
                    dropdown_list=cat_list,
                    parent__isnull=True,
                    is_active=True,
                ).order_by("label")
            else:
                # If categories list is missing, show none (prevents wrong linkage)
                form.fields["parent"].queryset = DropdownOption.objects.none()
            form.fields["parent"].disabled = False
            return form

        # Other lists: keep your original behavior (parent from same list top-level)
        form.fields["parent"].queryset = DropdownOption.objects.filter(
            dropdown_list=dropdown_list,
            parent__isnull=True,
        ).order_by("label")
        form.fields["parent"].disabled = False
        return form

    def form_valid(self, form):
        form.instance.dropdown_list_id = self.kwargs["list_id"]

        # Enforce: categories are always top-level
        dropdown_list = DropdownList.objects.get(pk=self.kwargs["list_id"])
        if _is_categories_list(dropdown_list):
            form.instance.parent = None

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dropdown_list = DropdownList.objects.get(pk=self.kwargs["list_id"])
        ctx["dropdown_list"] = dropdown_list
        ctx["title"] = f"Add Option to {dropdown_list.name}"
        ctx["cancel_url"] = reverse_lazy(
            "codes:dropdown_option_list",
            kwargs={"list_id": dropdown_list.pk},
        )
        return ctx

    def get_success_url(self):
        return reverse(
            "codes:dropdown_option_list",
            kwargs={"list_id": self.kwargs["list_id"]},
        )


class DropdownOptionUpdateView(UpdateView):
    model = DropdownOption
    fields = ["label", "parent", "is_active"]
    template_name = "codes/dropdown_option_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        dropdown_list = self.object.dropdown_list

        form.fields["parent"].required = False

        # Asset Categories: categories are top-level, so parent should be disabled/empty
        if _is_categories_list(dropdown_list):
            form.fields["parent"].queryset = DropdownOption.objects.none()
            form.fields["parent"].disabled = True
            return form

        # Asset Equipment: parent should be chosen from Asset Categories (top-level)
        if _is_equipment_list(dropdown_list):
            cat_list = _get_categories_list()
            if cat_list:
                form.fields["parent"].queryset = DropdownOption.objects.filter(
                    dropdown_list=cat_list,
                    parent__isnull=True,
                    is_active=True,
                ).exclude(pk=self.object.pk).order_by("label")
            else:
                form.fields["parent"].queryset = DropdownOption.objects.none()
            form.fields["parent"].disabled = False
            return form

        # Other lists: keep original behavior
        form.fields["parent"].queryset = DropdownOption.objects.filter(
            dropdown_list=dropdown_list,
            parent__isnull=True,
        ).exclude(pk=self.object.pk).order_by("label")
        form.fields["parent"].disabled = False
        return form

    def form_valid(self, form):
        # Enforce: categories are always top-level
        if _is_categories_list(self.object.dropdown_list):
            form.instance.parent = None
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dropdown_list = self.object.dropdown_list
        ctx["dropdown_list"] = dropdown_list
        ctx["title"] = f"Edit Option in {dropdown_list.name}"
        ctx["cancel_url"] = reverse_lazy(
            "codes:dropdown_option_list",
            kwargs={"list_id": dropdown_list.pk},
        )
        return ctx

    def get_success_url(self):
        return reverse(
            "codes:dropdown_option_list",
            kwargs={"list_id": self.object.dropdown_list.pk},
        )


class DropdownOptionDeleteView(DeleteView):
    model = DropdownOption
    template_name = "codes/delete.html"

    def get_success_url(self):
        return reverse(
            "codes:dropdown_option_list",
            kwargs={"list_id": self.object.dropdown_list.pk},
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Delete Dropdown Option"
        ctx["cancel_url"] = reverse_lazy(
            "codes:dropdown_option_list",
            kwargs={"list_id": self.object.dropdown_list.pk},
        )
        return ctx
