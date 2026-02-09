# job_tasks/models.py

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

    # ------------------------------------------------------------------
    # Parent/Child grouping (NEW)
    # ------------------------------------------------------------------
    parent_job = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='child_jobs'
    )

    # Shared across ALL related jobs (store on parent; children should read/write via parent)
    shared_site_notes = models.TextField(
        blank=True,
        default="",
        help_text="Shared site notes for this job group (stored on the parent job).",
    )

    # Per technician/day job notes (stored on each task; primarily used on child jobs)
    technician_job_notes = models.TextField(
        blank=True,
        default="",
        help_text="Technician-specific job notes (per scheduled task).",
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")  # kept for DB compatibility

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")

    # Service Date (blank unless user sets)
    service_date = models.DateField(null=True, blank=True)

    # ✅ start/finish time
    start_time = models.TimeField(null=True, blank=True)
    finish_time = models.TimeField(null=True, blank=True)
    is_all_day = models.BooleanField(default=False)

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
        through_fields=("job_task", "property_asset"),
        blank=True,
        related_name="job_tasks",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} (#{self.pk})"

    @property
    def root_job(self) -> "JobTask":
        """
        Parent job if this is a child, otherwise self.
        """
        return self.parent_job if self.parent_job_id else self

    @property
    def is_parent(self) -> bool:
        return self.parent_job_id is None

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
        - If all-day: wipe times and set display
        """
        # If all-day: wipe times and set display
        if self.is_all_day:
            self.start_time = None
            self.finish_time = None
            self.service_time = "All day"

        if self.service_date and self.status == "open":
            self.status = "scheduled"
        if not self.service_date and self.status == "scheduled":
            self.status = "open"

        # Only compute time range display when not all-day
        if not self.is_all_day:
            if self.start_time and self.finish_time:
                self.service_time = (
                    f"{self._fmt_time_dot(self.start_time)}-{self._fmt_time_dot(self.finish_time)}"
                )
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

    RESULT_CHOICES = [
        ("pass", "Pass"),
        ("fail", "Fail"),
        ("access", "Access"),
        ("no_access", "No Access"),
    ]

    result = models.CharField(max_length=20, choices=RESULT_CHOICES, blank=True, default="")
    image_urls = models.JSONField(default=list, blank=True)

    last_updated_job = models.ForeignKey(
        "job_tasks.JobTask",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asset_link_updates",
    )

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


class JobTaskAssetResult(models.Model):
    """
    Per-job result for a linked asset.
    """

    job_task = models.ForeignKey(
        "job_tasks.JobTask",
        on_delete=models.CASCADE,
        related_name="asset_results",
    )

    property_asset = models.ForeignKey(
        "properties.PropertyAsset",
        on_delete=models.CASCADE,
        related_name="job_task_results",
    )

    RESULT_CHOICES = [
        ("pass", "Pass"),
        ("fail", "Fail"),
        ("access", "Access"),
        ("no_access", "No Access"),
    ]

    result = models.CharField(max_length=20, choices=RESULT_CHOICES, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["job_task", "property_asset"],
                name="uq_jobtask_asset_result",
            )
        ]

    def __str__(self) -> str:
        return f"JobTask #{self.job_task_id} result for Asset #{self.property_asset_id}"


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


class JobTaskAssetImage(models.Model):
    """
    Uploaded images tied to a JobTaskAssetLink.
    """

    link = models.ForeignKey(
        "job_tasks.JobTaskAssetLink",
        on_delete=models.CASCADE,
        related_name="images",
    )

    image = models.ImageField(upload_to="job_tasks/assets/")

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"JobTaskAssetImage #{self.pk}"
