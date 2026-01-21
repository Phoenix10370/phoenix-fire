# quotations/models.py
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

    # ✅ Acceptance / rejection tracking + work order number
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quotations_accepted",
    )

    # ✅ NEW: manual display name (typed on accept screen)
    accepted_by_name = models.CharField(max_length=120, blank=True, default="")

    # ✅ CHANGED: date-only (no time)
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

    # =========================
    # Activity Log helper
    # =========================
    def log(self, action: str, user=None, message: str = "") -> None:
        QuotationLog.objects.create(
            quotation=self,
            actor=user if getattr(user, "is_authenticated", False) else None,
            action=action,
            message=message or "",
        )

    # =========================
    # State transitions
    # =========================
    def mark_accepted(self, user, accepted_date=None, accepted_by_name="", work_order_number=None):
        self.status = "accepted"
        self.accepted_by = user if getattr(user, "is_authenticated", False) else None

        # ✅ date-only
        self.accepted_date = accepted_date or timezone.localdate()

        # ✅ typed name (optional)
        self.accepted_by_name = (accepted_by_name or "").strip()

        # clear rejection fields if switching
        self.rejected_by = None
        self.rejected_at = None

        # Work order updates only if provided
        if work_order_number is not None:
            self.work_order_number = work_order_number

    def mark_rejected(self, user):
        self.status = "rejected"
        self.rejected_by = user if getattr(user, "is_authenticated", False) else None
        self.rejected_at = timezone.now()

        # clear acceptance fields if switching
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

    class Meta:
        ordering = ["efsm_code__code"]

    @property
    def line_total(self):
        return (self.quantity or 0) * (self.unit_price or 0)

    def __str__(self):
        return f"{self.quotation.number} - {self.efsm_code.code}"
