from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, View

from .models import EquipmentOptionalField
from .forms_equipment_optional_fields import EquipmentOptionalFieldForm


@method_decorator(staff_member_required, name="dispatch")
class EquipmentOptionalFieldListView(ListView):
    model = EquipmentOptionalField
    template_name = "codes/equipment_optional_fields/list.html"
    context_object_name = "rows"
    paginate_by = 50

    def get_queryset(self):
        qs = (
            EquipmentOptionalField.objects
            .select_related("equipment", "field", "equipment__parent", "equipment__dropdown_list")
            .all()
        )

        q = (self.request.GET.get("q") or "").strip()
        show = (self.request.GET.get("show") or "active").strip()

        if show == "active":
            qs = qs.filter(is_active=True)
        elif show == "inactive":
            qs = qs.filter(is_active=False)

        if q:
            qs = qs.filter(
                Q(equipment__label__icontains=q) |
                Q(field__label__icontains=q)
            )

        return qs.order_by("equipment__label", "field__label")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        ctx["show"] = (self.request.GET.get("show") or "active").strip()
        return ctx


@method_decorator(staff_member_required, name="dispatch")
class EquipmentOptionalFieldEditView(View):
    template_name = "codes/equipment_optional_fields/edit.html"

    def get(self, request, pk):
        row = get_object_or_404(EquipmentOptionalField, pk=pk)
        form = EquipmentOptionalFieldForm(instance=row)
        return render(request, self.template_name, {"row": row, "form": form})

    def post(self, request, pk):
        row = get_object_or_404(EquipmentOptionalField, pk=pk)
        form = EquipmentOptionalFieldForm(request.POST, instance=row)
        if form.is_valid():
            form.save()
            return redirect(self._success_url(request))
        return render(request, self.template_name, {"row": row, "form": form})

    def _success_url(self, request):
        base = reverse("codes:eof_list")
        q = (request.GET.get("q") or "").strip()
        show = (request.GET.get("show") or "").strip()

        params = []
        if q:
            params.append(f"q={q}")
        if show:
            params.append(f"show={show}")
        return base + ("?" + "&".join(params) if params else "")
