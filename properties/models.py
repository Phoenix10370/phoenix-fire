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

    site_id = models.CharField(
        max_length=8,
        unique=True,
        editable=False,
        blank=True,
        db_index=True,
    )

    # ✅ NEW FIELDS
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

    def __str__(self):
        return self.building_name
