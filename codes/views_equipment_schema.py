# codes/views_equipment_schema.py

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from .models import AssetField, DropdownOption, EquipmentOptionalField


@staff_member_required
@require_http_methods(["GET", "POST"])
def equipment_schema_manage(request, equipment_id):
    """
    Manage EquipmentOptionalField records for a specific equipment:
      - add/disable fields
      - edit allowed values list
    """
    equipment = get_object_or_404(DropdownOption, pk=equipment_id)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        # -------------------------
        # Add new field to equipment
        # -------------------------
        if action == "add_field":
            label = (request.POST.get("field_label") or "").strip()
            if not label:
                messages.error(request, "Field label is required.")
                return redirect(request.path)

            with transaction.atomic():
                field, _ = AssetField.objects.get_or_create(label=label, defaults={"is_active": True})
                EquipmentOptionalField.objects.get_or_create(
                    equipment=equipment,
                    field=field,
                    defaults={"values": [], "is_active": True},
                )

            messages.success(request, f"Added field '{label}' to {equipment.label}.")
            return redirect(request.path)

        # -------------------------
        # Toggle a field on/off
        # -------------------------
        if action == "toggle_field":
            eof_id = request.POST.get("eof_id")
            eof = get_object_or_404(EquipmentOptionalField, pk=eof_id, equipment=equipment)
            eof.is_active = not eof.is_active
            eof.save(update_fields=["is_active"])
            messages.success(request, f"{'Enabled' if eof.is_active else 'Disabled'} field '{eof.field.label}'.")
            return redirect(request.path)

        # -------------------------
        # Add a value to a field
        # -------------------------
        if action == "add_value":
            eof_id = request.POST.get("eof_id")
            value = (request.POST.get("value") or "").strip()

            eof = get_object_or_404(EquipmentOptionalField, pk=eof_id, equipment=equipment)

            if not value:
                messages.error(request, "Value cannot be blank.")
                return redirect(request.path)

            values = eof.values if isinstance(eof.values, list) else []
            # case-insensitive dedupe
            if value.lower() not in {str(v).strip().lower() for v in values if str(v).strip()}:
                values.append(value)
                eof.values = values
                eof.save(update_fields=["values"])
                messages.success(request, f"Added value '{value}' to '{eof.field.label}'.")
            else:
                messages.info(request, f"Value '{value}' already exists for '{eof.field.label}'.")

            return redirect(request.path)

        # -------------------------
        # Remove a value from a field
        # -------------------------
        if action == "remove_value":
            eof_id = request.POST.get("eof_id")
            value = (request.POST.get("value") or "").strip()

            eof = get_object_or_404(EquipmentOptionalField, pk=eof_id, equipment=equipment)
            values = eof.values if isinstance(eof.values, list) else []

            new_values = [v for v in values if str(v) != value]
            eof.values = new_values
            eof.save(update_fields=["values"])
            messages.success(request, f"Removed value '{value}' from '{eof.field.label}'.")
            return redirect(request.path)

        messages.error(request, "Unknown action.")
        return redirect(request.path)

    rows = (
        EquipmentOptionalField.objects
        .filter(equipment=equipment)
        .select_related("field")
        .order_by("field__label")
    )

    return render(
        request,
        "codes/equipment_schema/manage.html",
        {
            "title": f"Manage Fields & Values — {equipment.label}",
            "equipment": equipment,
            "rows": rows,
        },
    )
