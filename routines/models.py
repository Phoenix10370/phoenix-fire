# routines/models.py
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


# =========================
# Month Choices
# =========================
MONTH_CHOICES = [
    (1, "January"),
    (2, "February"),
    (3, "March"),
    (4, "April"),
    (5, "May"),
    (6, "June"),
    (7, "July"),
    (8, "August"),
    (9, "September"),
    (10, "October"),
    (11, "November"),
    (12, "December"),
]


# =========================
# Service Routine
# =========================
class ServiceRoutine(models.Model):
    ROUTINE_TYPE_CHOICES = [
        ("annual", "Annual"),
        ("biannual", "Bi-Annual"),
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
    ]

    quotation = models.ForeignKey(
        "quotations.Quotation",
        on_delete=models.CASCADE,
        related_name="service_routines",
    )

    # If your Quotation always has a site FK, keep this in sync with your actual Site model path.
    site = models.ForeignKey(
        "properties.Property",   # <-- adjust if your site model path differs
        on_delete=models.PROTECT,
        related_name="service_routines",
    )

    routine_type = models.CharField(
        max_length=20,
        choices=ROUTINE_TYPE_CHOICES,
        default="annual",
    )

    month_due = models.PositiveSmallIntegerField(
        choices=MONTH_CHOICES,
        default=1,
    )

    name = models.CharField(max_length=255, default="", blank=True)
    notes = models.TextField(blank=True, default="")

    work_order_number = models.CharField(max_length=100, blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_service_routines",
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.name or 'Service Routine'} ({self.get_routine_type_display()})"


# =========================
# Service Routine Item
# =========================
class ServiceRoutineItem(models.Model):
    routine = models.ForeignKey(
        ServiceRoutine,
        related_name="items",
        on_delete=models.CASCADE,
    )

    # ✅ OPTIONAL EFSM code (so custom lines can exist without touching Code table)
    efsm_code = models.ForeignKey(
        "codes.Code",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_routine_items",
    )

    # ✅ user-entered description for custom items (does NOT create/change EFSM codes)
    custom_description = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # Keeps link to quotation item when generated from quotation;
    # for user-added routine-only lines, set this to None.
    source_quotation_item = models.ForeignKey(
        "quotations.QuotationItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_routine_items",
    )

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.display_code}: {self.display_description}"

    @property
    def line_total(self) -> Decimal:
        qty = self.quantity or Decimal("0.00")
        unit = self.unit_price or Decimal("0.00")
        return (qty * unit).quantize(Decimal("0.01"))

    @property
    def display_code(self) -> str:
        # Used by templates: show EFSM code if present, else "CUSTOM"
        return self.efsm_code.code if self.efsm_code else "CUSTOM"

    @property
    def display_description(self) -> str:
        # Used by templates: show EFSM description if present, else user entry
        if self.efsm_code:
            return getattr(self.efsm_code, "fire_safety_measure", "") or self.custom_description or ""
        return self.custom_description or ""
