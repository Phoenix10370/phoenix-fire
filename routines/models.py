from django.conf import settings
from django.db import models
from django.utils import timezone

from properties.models import Property
from quotations.models import Quotation, QuotationItem
from codes.models import Code


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
    ]

    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.PROTECT,
        related_name="service_routines",
    )

    routine_type = models.CharField(max_length=20, choices=ROUTINE_TYPE_CHOICES)

    # ✅ This IS the Service Month field (editable dropdown)
    month_due = models.PositiveSmallIntegerField(choices=MONTH_CHOICES)

    name = models.CharField(max_length=120)

    created_at = models.DateTimeField(default=timezone.now)

    site = models.ForeignKey(Property, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_routines_created",
    )

    work_order_number = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        ordering = ["quotation_id", "month_due", "routine_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["quotation", "routine_type", "month_due"],
                name="uniq_routine_type_and_month_per_quotation",
            )
        ]

    def __str__(self) -> str:
        return f"{self.quotation.number} - {self.name} ({self.get_month_due_display()})"


class ServiceRoutineItem(models.Model):
    routine = models.ForeignKey(
        ServiceRoutine,
        on_delete=models.CASCADE,
        related_name="items",
    )

    efsm_code = models.ForeignKey(Code, on_delete=models.PROTECT)

    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    source_quotation_item = models.ForeignKey(
        QuotationItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_routine_items",
    )

    class Meta:
        ordering = ["efsm_code__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["routine", "efsm_code"],
                name="uniq_code_per_routine",
            )
        ]

    @property
    def line_total(self):
        return (self.quantity or 0) * (self.unit_price or 0)

    def __str__(self) -> str:
        return f"{self.routine} - {self.efsm_code.code}"
