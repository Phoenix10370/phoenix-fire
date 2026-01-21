# codes/views.py
import csv
from io import TextIOWrapper

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import AssetCodeForm, CodeForm, DefectCodeForm
from .models import AssetCode, Code, DefectCode, DropdownList, DropdownOption


# =========================
# EFSM CSV IMPORT
# =========================

@require_http_methods(["GET", "POST"])
def efsm_import(request):
    """
    Upload a CSV and import EFSM Codes.
    CSV headers required: code, fire_safety_measure, visits_per_year
    """
    if request.method == "POST":
        file = request.FILES.get("file")
        update_existing = request.POST.get("update_existing") == "on"

        if not file:
            messages.error(request, "Please choose a CSV file to upload.")
            return redirect("codes:efsm_import")

        name = (file.name or "").lower()
        if not name.endswith(".csv"):
            messages.error(request, "Only .csv files are supported.")
            return redirect("codes:efsm_import")

        created = 0
        updated = 0
        skipped = 0
        errors = []

        try:
            wrapper = TextIOWrapper(file.file, encoding="utf-8-sig")
            reader = csv.DictReader(wrapper)

            required = {"code", "fire_safety_measure", "visits_per_year"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                messages.error(
                    request,
                    f"CSV must include headers: code, fire_safety_measure, visits_per_year. Found: {reader.fieldnames}",
                )
                return redirect("codes:efsm_import")

            for line_num, row in enumerate(reader, start=2):
                code_val = (row.get("code") or "").strip()
                fsm = (row.get("fire_safety_measure") or "").strip()
                vpy_raw = (row.get("visits_per_year") or "").strip()

                if not code_val or not fsm:
                    skipped += 1
                    errors.append(f"Row {line_num}: missing code or fire_safety_measure")
                    continue

                try:
                    vpy = int(vpy_raw) if vpy_raw else 1
                except ValueError:
                    skipped += 1
                    errors.append(f"Row {line_num}: invalid visits_per_year '{vpy_raw}'")
                    continue

                obj = Code.objects.filter(code=code_val).first()
                if obj:
                    if update_existing:
                        obj.fire_safety_measure = fsm
                        obj.visits_per_year = vpy
                        obj.save()
                        updated += 1
                    else:
                        skipped += 1
                else:
                    Code.objects.create(
                        code=code_val,
                        fire_safety_measure=fsm,
                        visits_per_year=vpy,
                    )
                    created += 1

        except Exception as e:
            messages.error(request, f"Import failed: {e}")
            return redirect("codes:efsm_import")

        messages.success(
            request,
            f"Import complete — created: {created}, updated: {updated}, skipped: {skipped}",
        )

        if errors:
            for msg in errors[:8]:
                messages.warning(request, msg)
            if len(errors) > 8:
                messages.warning(request, f"...and {len(errors) - 8} more row issues.")

        return redirect("codes:efsm_list")

    return render(
        request,
        "codes/efsm_import.html",
        {
            "title": "Import EFSM Codes",
            "cancel_url": reverse("codes:efsm_list"),
        },
    )


# =========================
# EFSM Codes
# =========================

class CodeListView(ListView):
    model = Code
    template_name = "codes/efsm_list.html"
    context_object_name = "items"


class CodeCreateView(CreateView):
    model = Code
    form_class = CodeForm
    template_name = "codes/add.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Add EFSM Code"
        ctx["cancel_url"] = reverse_lazy("codes:efsm_list")
        return ctx

    def get_success_url(self):
        return reverse_lazy("codes:efsm_list")


class CodeUpdateView(UpdateView):
    model = Code
    form_class = CodeForm
    template_name = "codes/edit.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Edit EFSM Code"
        ctx["cancel_url"] = reverse_lazy("codes:efsm_list")
        return ctx

    def get_success_url(self):
        return reverse_lazy("codes:efsm_list")


class CodeDeleteView(DeleteView):
    model = Code
    template_name = "codes/delete.html"
    success_url = reverse_lazy("codes:efsm_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Delete EFSM Code"
        ctx["cancel_url"] = reverse_lazy("codes:efsm_list")
        return ctx


# =========================
# Defect Codes
# =========================

class DefectCodeListView(ListView):
    model = DefectCode
    template_name = "codes/defect_list.html"
    context_object_name = "items"


class DefectCodeCreateView(CreateView):
    model = DefectCode
    form_class = DefectCodeForm
    template_name = "codes/add.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Add Defect Code"
        ctx["cancel_url"] = reverse_lazy("codes:defect_list")
        return ctx

    def get_success_url(self):
        return reverse_lazy("codes:defect_list")


class DefectCodeUpdateView(UpdateView):
    model = DefectCode
    form_class = DefectCodeForm
    template_name = "codes/edit.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Edit Defect Code"
        ctx["cancel_url"] = reverse_lazy("codes:defect_list")
        return ctx

    def get_success_url(self):
        return reverse_lazy("codes:defect_list")


class DefectCodeDeleteView(DeleteView):
    model = DefectCode
    template_name = "codes/delete.html"
    success_url = reverse_lazy("codes:defect_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Delete Defect Code"
        ctx["cancel_url"] = reverse_lazy("codes:defect_list")
        return ctx


# =========================
# Asset Codes
# =========================

class AssetCodeListView(ListView):
    model = AssetCode
    template_name = "codes/asset_list.html"
    context_object_name = "items"


class AssetCodeCreateView(CreateView):
    model = AssetCode
    form_class = AssetCodeForm
    template_name = "codes/asset_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Add Asset Code"
        ctx["cancel_url"] = reverse_lazy("codes:asset_list")
        return ctx

    def get_success_url(self):
        return reverse_lazy("codes:asset_list")


class AssetCodeUpdateView(UpdateView):
    model = AssetCode
    form_class = AssetCodeForm
    template_name = "codes/asset_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Edit Asset Code"
        ctx["cancel_url"] = reverse_lazy("codes:asset_list")
        return ctx

    def get_success_url(self):
        return reverse_lazy("codes:asset_list")


class AssetCodeDeleteView(DeleteView):
    model = AssetCode
    template_name = "codes/delete.html"
    success_url = reverse_lazy("codes:asset_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Delete Asset Code"
        ctx["cancel_url"] = reverse_lazy("codes:asset_list")
        return ctx


# =========================
# AJAX endpoint for dependent dropdown
# =========================

def asset_equipment_options(request):
    """
    Returns equipment options for a given category ID.
    Used by Asset Code form via fetch().
    """
    category_id = request.GET.get("category_id")
    eq_list = DropdownList.objects.filter(slug="asset-equipment", is_active=True).first()
    if not (category_id and eq_list):
        return JsonResponse({"results": []})

    qs = DropdownOption.objects.filter(
        dropdown_list=eq_list,
        is_active=True,
        parent_id=category_id,
    ).order_by("label")

    return JsonResponse(
        {"results": [{"id": o.id, "label": o.label} for o in qs]}
    )
