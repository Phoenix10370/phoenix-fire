from decimal import Decimal
from datetime import time
import uuid

from django.conf import settings
from django.db import models


class JobServiceType(models.Model):
    """
    Modifiable drop-down list for Service Types.
    """
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class JobTask(models.Model):
    STATUS_CHOICES = [
        ("open", "Unscheduled"),
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("done", "Done"),
        ("cancelled", "Cancelled"),
    ]

    site = models.ForeignKey(
        "properties.Property",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_tasks",
    )

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_tasks",
    )

    service_routine = models.ForeignKey(
        "routines.ServiceRoutine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_tasks",
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")  # kept for DB compatibility

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")

    # Service Date (blank unless user sets)
    service_date = models.DateField(null=True, blank=True)

    # ✅ NEW: start/finish time
    start_time = models.TimeField(null=True, blank=True)
    finish_time = models.TimeField(null=True, blank=True)

    # ✅ Keep legacy display field (safe + avoids breaking old code/templates)
    # This will be auto-updated from start/finish when present.
    service_time = models.CharField(max_length=100, blank=True, default="")

    service_type = models.ForeignKey(
        "job_tasks.JobServiceType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_tasks",
    )

    service_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_tasks_primary",
    )

    additional_technicians = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="job_tasks_additional",
    )

    CLIENT_ACK_CHOICES = [
        ("yes", "Yes"),
        ("no", "No"),
    ]
    client_acknowledgement = models.CharField(
        max_length=10,
        choices=CLIENT_ACK_CHOICES,
        blank=True,
        default="",
    )
    acknowledgement_date = models.DateField(null=True, blank=True)
    work_order_no = models.CharField(max_length=100, blank=True, default="")
    admin_comments = models.TextField(blank=True, default="")

    technician_comments = models.TextField(blank=True, default="")

    # ✅ Property Assets linked to this Job Task (many-to-many)
    # The Property still "owns" assets (PropertyAsset). Job tasks link to them.
    property_assets = models.ManyToManyField(
        "properties.PropertyAsset",
        through="job_tasks.JobTaskAssetLink",
        blank=True,
        related_name="job_tasks",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} (#{self.pk})"

    @staticmethod
    def _fmt_time_dot(t: time) -> str:
        """
        Format time like 8.30am
        """
        if not t:
            return ""
        hour = t.hour % 12
        hour = 12 if hour == 0 else hour
        ampm = "am" if t.hour < 12 else "pm"
        return f"{hour}.{t.minute:02d}{ampm}"

    def save(self, *args, **kwargs):
        """
        ✅ Auto rules:
        - If service_date is set and status is Unscheduled -> Scheduled
        - If service_date is cleared and status is Scheduled -> Unscheduled
        - If start+finish exist -> update service_time display string
        """
        if self.service_date and self.status == "open":
            self.status = "scheduled"
        if not self.service_date and self.status == "scheduled":
            self.status = "open"

        if self.start_time and self.finish_time:
            self.service_time = f"{self._fmt_time_dot(self.start_time)}-{self._fmt_time_dot(self.finish_time)}"
        elif not self.start_time and not self.finish_time:
            # leave existing service_time alone (in case older data is stored there)
            pass
        else:
            # one is set but not the other
            # keep a partial display to avoid confusion
            if self.start_time and not self.finish_time:
                self.service_time = f"{self._fmt_time_dot(self.start_time)}-"
            elif self.finish_time and not self.start_time:
                self.service_time = f"-{self._fmt_time_dot(self.finish_time)}"

        super().save(*args, **kwargs)

    def subtotal_amount(self) -> Decimal:
        subtotal = Decimal("0.00")
        for item in self.items.all():
            subtotal += item.line_total
        return subtotal.quantize(Decimal("0.01"))

    def gst_amount(self) -> Decimal:
        return (self.subtotal_amount() * Decimal("0.10")).quantize(Decimal("0.01"))

    def total_amount(self) -> Decimal:
        return (self.subtotal_amount() + self.gst_amount()).quantize(Decimal("0.01"))


class JobTaskAssetLink(models.Model):
    """
    Link table between a JobTask and a PropertyAsset.

    - Prevents duplicating assets per job/task
    - Allows a PropertyAsset to appear on multiple job tasks over time
    """

    job_task = models.ForeignKey(
        "job_tasks.JobTask",
        on_delete=models.CASCADE,
        related_name="property_asset_links",
    )

    property_asset = models.ForeignKey(
        "properties.PropertyAsset",
        on_delete=models.CASCADE,
        related_name="job_task_links",
    )

    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Job Task Asset Link"
        verbose_name_plural = "Job Task Asset Links"
        constraints = [
            models.UniqueConstraint(
                fields=["job_task", "property_asset"],
                name="uq_jobtask_propertyasset_link",
            )
        ]

    def __str__(self) -> str:
        return f"JobTask #{self.job_task_id} -> PropertyAsset #{self.property_asset_id}"


class JobTaskItem(models.Model):
    """
    Snapshot copied from Service Routine Items
    """
    job_task = models.ForeignKey(
        "job_tasks.JobTask",
        on_delete=models.CASCADE,
        related_name="items",
    )

    code = models.CharField(max_length=60, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")

    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.code} {self.description}".strip()

    @property
    def line_total(self) -> Decimal:
        qty = self.quantity or Decimal("0")
        unit = self.unit_price or Decimal("0")
        return (qty * unit).quantize(Decimal("0.01"))
