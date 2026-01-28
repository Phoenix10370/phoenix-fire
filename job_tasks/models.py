from decimal import Decimal

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
        ("open", "Open"),
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("done", "Done"),
        ("cancelled", "Cancelled"),
    ]

    # ✅ Use "site" to match the rest of your project and avoid @property conflict
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
    description = models.TextField(blank=True, default="")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")

    # ✅ 1) Service Date
    service_date = models.DateField(null=True, blank=True)

    # ✅ 2) Service Type (modifiable drop-down)
    service_type = models.ForeignKey(
        "job_tasks.JobServiceType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_tasks",
    )

    # ✅ 3) Service Technician
    service_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_tasks_primary",
    )

    # ✅ 4) Additional Technicians (multi-select)
    additional_technicians = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="job_tasks_additional",
    )

    due_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} (#{self.pk})"

    def subtotal_amount(self) -> Decimal:
        subtotal = Decimal("0.00")
        for item in self.items.all():
            subtotal += item.line_total
        return subtotal.quantize(Decimal("0.01"))

    def gst_amount(self) -> Decimal:
        return (self.subtotal_amount() * Decimal("0.10")).quantize(Decimal("0.01"))

    def total_amount(self) -> Decimal:
        return (self.subtotal_amount() + self.gst_amount()).quantize(Decimal("0.01"))


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
