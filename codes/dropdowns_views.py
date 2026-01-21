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

        # Parent must belong to same list
        form.fields["parent"].queryset = DropdownOption.objects.filter(
            dropdown_list=dropdown_list,
            parent__isnull=True,
        )
        form.fields["parent"].required = False
        return form

    def form_valid(self, form):
        form.instance.dropdown_list_id = self.kwargs["list_id"]
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

        form.fields["parent"].queryset = DropdownOption.objects.filter(
            dropdown_list=dropdown_list,
            parent__isnull=True,
        ).exclude(pk=self.object.pk)
        form.fields["parent"].required = False
        return form

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
