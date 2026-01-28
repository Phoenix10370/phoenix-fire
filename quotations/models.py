# quotations/models.py
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import Max
from django.utils import timezone

from properties.models import Property
from codes.models import Code


class Quotation(models.Model):
    PREFIX = "Q-"
    PAD = 5

    number = models.CharField(max_length=20, unique=True, editable=False, blank=True)

    site = models.ForeignKey(
        Property,
        on_delete=models.PROTECT,
        related_name="quotations",
    )

    created_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quotations_accepted",
    )
    accepted_by_name = models.CharField(max_length=120, blank=True, default="")
    accepted_date = models.DateField(null=True, blank=True)

    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quotations_rejected",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)

    work_order_number = models.CharField(max_length=50, null=True, blank=True)

    calc_men_annual = models.PositiveIntegerField(default=0)
    calc_hours_annual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    calc_price_annual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    calc_visits_annual = models.PositiveIntegerField(default=1)

    calc_men_half = models.PositiveIntegerField(default=0)
    calc_hours_half = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    calc_price_half = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    calc_visits_half = models.PositiveIntegerField(default=1)

    calc_men_month = models.PositiveIntegerField(default=0)
    calc_hours_month = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    calc_price_month = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    calc_visits_month = models.PositiveIntegerField(default=12)

    calc_afss_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def _next_number(cls):
        with transaction.atomic():
            max_num = (
                cls.objects.select_for_update()
                .filter(number__startswith=cls.PREFIX)
                .aggregate(m=Max("number"))
            )["m"]
            next_int = 1 if not max_num else int(max_num.replace(cls.PREFIX, "")) + 1
            return f"{cls.PREFIX}{next_int:0{cls.PAD}d}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = self._next_number()
        super().save(*args, **kwargs)

    @property
    def customer(self):
        return self.site.customer

    def log(self, action: str, user=None, message: str = "") -> None:
        QuotationLog.objects.create(
            quotation=self,
            actor=user if getattr(user, "is_authenticated", False) else None,
            action=action,
            message=message or "",
        )

    def mark_accepted(self, user, accepted_date=None, accepted_by_name="", work_order_number=None):
        self.status = "accepted"
        self.accepted_by = user if getattr(user, "is_authenticated", False) else None
        self.accepted_date = accepted_date or timezone.localdate()
        self.accepted_by_name = (accepted_by_name or "").strip()
        self.rejected_by = None
        self.rejected_at = None
        if work_order_number is not None:
            self.work_order_number = work_order_number

    def mark_rejected(self, user):
        self.status = "rejected"
        self.rejected_by = user if getattr(user, "is_authenticated", False) else None
        self.rejected_at = timezone.now()
        self.accepted_by = None
        self.accepted_date = None
        self.accepted_by_name = ""

    def __str__(self):
        return self.number


class QuotationLog(models.Model):
    ACTION_CHOICES = [
        ("created", "Created"),
        ("modified", "Modified"),
        ("sent", "Sent"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("status_changed", "Status Changed"),
        ("note_changed", "Notes Changed"),
    ]

    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="logs",
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quotation_logs",
    )

    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        who = str(self.actor) if self.actor else "System"
        return f"{self.quotation.number} - {self.action} by {who} @ {self.created_at}"


class QuotationItem(models.Model):
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="items",
    )
    efsm_code = models.ForeignKey(Code, on_delete=models.PROTECT)

    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # ✅ Persisted UI order (so saving never re-sorts by EFSM code)
    position = models.PositiveIntegerField(default=0, db_index=True)

    class Meta:
        ordering = ["position", "id"]

    def save(self, *args, **kwargs):
        # Auto-append new lines to the end if no position supplied
        if self.quotation_id and (self.position is None or int(self.position) == 0):
            max_pos = (
                QuotationItem.objects
                .filter(quotation_id=self.quotation_id)
                .exclude(pk=self.pk)
                .aggregate(m=Max("position"))
            )["m"] or 0
            self.position = int(max_pos) + 1

        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return (self.quantity or 0) * (self.unit_price or 0)

    def __str__(self):
        return f"{self.quotation.number} - {self.efsm_code.code}"


# =========================
# COMMENTS / CORRESPONDENCE
# =========================

def quotation_correspondence_upload_to(instance: "QuotationCorrespondence", filename: str) -> str:
    # Keep it simple + sortable by date, and grouped by quotation number.
    # Example: quotation_correspondence/Q-00012/2026/01/28/mydoc.pdf
    safe_number = (instance.quotation.number or "quotation").replace("/", "-")
    today = timezone.localdate()
    return f"quotation_correspondence/{safe_number}/{today:%Y/%m/%d}/{filename}"


class QuotationComment(models.Model):
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="comments",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    comment = models.TextField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quotation_comments",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.quotation.number} comment @ {self.created_at}"


class QuotationCorrespondence(models.Model):
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="correspondence",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quotation_correspondence_uploaded",
    )

    document = models.FileField(upload_to=quotation_correspondence_upload_to)
    original_name = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.document and not self.original_name:
            # Keep the display name stable even if storage renames the file.
            self.original_name = self.document.name.split("/")[-1]
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.quotation.number} doc: {self.original_name or 'document'}"
