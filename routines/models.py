# routines/models.py
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Max
from django.utils import timezone


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

    site = models.ForeignKey(
        "properties.Property",
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

    # Notes split (replaces old "notes")
    quotation_notes = models.TextField(blank=True, default="")
    site_notes = models.TextField(blank=True, default="")
    technician_notes = models.TextField(blank=True, default="")

    # Values populated from quotation (single values)
    annual_men_req = models.PositiveIntegerField(null=True, blank=True)
    annual_man_hours = models.PositiveIntegerField(null=True, blank=True)

    half_yearly_men_req = models.PositiveIntegerField(null=True, blank=True)
    half_yearly_man_hours = models.PositiveIntegerField(null=True, blank=True)

    monthly_men_req = models.PositiveIntegerField(null=True, blank=True)
    monthly_man_hours = models.PositiveIntegerField(null=True, blank=True)

    # Monthly Run / Week – user entry edit boxes (often a number)
    monthly_run_notes = models.CharField(max_length=255, blank=True, default="")
    monthly_week_notes = models.CharField(max_length=255, blank=True, default="")

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


class ServiceRoutineItem(models.Model):
    routine = models.ForeignKey(
        ServiceRoutine,
        related_name="items",
        on_delete=models.CASCADE,
    )

    efsm_code = models.ForeignKey(
        "codes.Code",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_routine_items",
    )

    custom_description = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    source_quotation_item = models.ForeignKey(
        "quotations.QuotationItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_routine_items",
    )

    # ✅ Persisted row order (keeps routine items stable across saves/updates)
    position = models.PositiveIntegerField(default=0, db_index=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["position", "id"]

    def save(self, *args, **kwargs):
        """
        Auto-append new routine lines to the end when no position is supplied.
        """
        if self.routine_id and (self.position is None or int(self.position) == 0):
            max_pos = (
                ServiceRoutineItem.objects
                .filter(routine_id=self.routine_id)
                .exclude(pk=self.pk)
                .aggregate(m=Max("position"))
            )["m"] or 0
            self.position = int(max_pos) + 1

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.display_code}: {self.display_description}"

    @property
    def line_total(self) -> Decimal:
        qty = self.quantity or Decimal("0.00")
        unit = self.unit_price or Decimal("0.00")
        return (qty * unit).quantize(Decimal("0.01"))

    @property
    def display_code(self) -> str:
        return self.efsm_code.code if self.efsm_code else "CUSTOM"

    @property
    def display_description(self) -> str:
        if self.efsm_code:
            return getattr(self.efsm_code, "fire_safety_measure", "") or self.custom_description or ""
        return self.custom_description or ""
