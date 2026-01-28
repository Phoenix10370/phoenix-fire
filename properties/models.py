from django.db import models, transaction
from django.db.models import Max
from customers.models import Customer


class Property(models.Model):
    ACCESS_CHOICES = [
        ("unrestricted", "Unrestricted"),
        ("office", "Keys Held In Office"),
        ("key", "Keys Required"),
        ("site_contact", "Site Contact"),
        ("lock_box", "Lock Box Code"),
        ("other", "Other"),
    ]

    PROPERTY_DESCRIPTION_CHOICES = [
        ("residential", "Residential"),
        ("commercial", "Commercial"),
        ("mixed", "Mixed Residential / Commercial"),
        ("industrial", "Industrial"),
        ("housing", "Housing"),
        ("medical", "Medical"),
        ("government", "Government"),
        ("rural", "Rural"),
    ]

    site_id = models.CharField(
        max_length=8,
        unique=True,
        editable=False,
        blank=True,
        db_index=True,
    )

    strata_plan = models.CharField(max_length=100, blank=True)
    sor_site_id = models.CharField(max_length=100, blank=True)

    building_name = models.CharField(max_length=200)
    street = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50, blank=True)
    post_code = models.CharField(max_length=20, blank=True)

    active_status = models.BooleanField(default=True)

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="properties",
        null=True,
        blank=True,
    )

    # ✅ NEW SECTION 2 FIELDS
    property_description = models.CharField(
        max_length=30,
        choices=PROPERTY_DESCRIPTION_CHOICES,
        blank=True,
    )
    number_of_residential = models.PositiveIntegerField(null=True, blank=True)
    number_of_commercial = models.PositiveIntegerField(null=True, blank=True)
    afss_number = models.CharField(max_length=100, blank=True)
    certification_date = models.DateField(null=True, blank=True)

    fire_coordinator = models.CharField(max_length=150, blank=True)
    fire_coordinator_email = models.EmailField(blank=True)
    fire_coordinator_phone = models.CharField(max_length=50, blank=True)

    afss_due_date = models.DateField(null=True, blank=True)

    levels_above_ground = models.PositiveIntegerField(null=True, blank=True)
    levels_below_ground = models.PositiveIntegerField(null=True, blank=True)

    access_details = models.CharField(
        max_length=50,
        choices=ACCESS_CHOICES,
        blank=True,
    )
    access_code = models.CharField(max_length=50, blank=True)

    site_contact = models.CharField(max_length=150, blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)

    site_notes = models.TextField(blank=True)
    technician_notes = models.TextField(blank=True)

    PREFIX = "PTY"
    PAD = 5

    class Meta:
        verbose_name = "Property"
        verbose_name_plural = "Properties"
        ordering = ["building_name", "city", "site_id"]

    @classmethod
    def _next_site_id(cls) -> str:
        with transaction.atomic():
            max_id = (
                cls.objects.select_for_update()
                .filter(site_id__startswith=cls.PREFIX)
                .aggregate(m=Max("site_id"))
            )["m"]

            next_num = 1 if not max_id else int(max_id[3:]) + 1
            return f"{cls.PREFIX}{next_num:0{cls.PAD}d}"

    def save(self, *args, **kwargs):
        if not self.site_id:
            self.site_id = self._next_site_id()
        super().save(*args, **kwargs)

    @property
    def full_address(self) -> str:
        parts = [self.street.strip(), self.city.strip()]

        state_pc = " ".join(
            p
            for p in [
                self.state.strip() if self.state else "",
                self.post_code.strip() if self.post_code else "",
            ]
            if p
        ).strip()

        if state_pc:
            parts.append(state_pc)

        return ", ".join([p for p in parts if p])

    @property
    def display_name(self) -> str:
        if self.site_id:
            return f"{self.building_name} ({self.site_id})"
        return self.building_name

    def __str__(self):
        return self.building_name
