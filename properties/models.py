from django.db import models, transaction
from django.db.models import Max
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from customers.models import Customer
import uuid


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

    # --- Coordinate lock / validation (NEW, safe + optional) ---
    # Use DecimalField for stable storage and predictable formatting.
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, db_index=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, db_index=True
    )
    coords_validated = models.BooleanField(default=False, db_index=True)
    coords_validated_at = models.DateTimeField(null=True, blank=True)

    # Optional traceability (no impact unless you use it)
    coords_validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validated_properties",
    )

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

    # --- Helpers for templates / UI ---
    @property
    def has_locked_coords(self) -> bool:
        return bool(self.coords_validated and self.latitude is not None and self.longitude is not None)

    @property
    def coords_pair(self):
        """
        Returns (lat, lng) as strings when present, else (None, None).
        Useful for building URLs safely in templates.
        """
        if self.latitude is None or self.longitude is None:
            return (None, None)
        return (str(self.latitude), str(self.longitude))

    def __str__(self):
        return self.building_name


class PropertyAsset(models.Model):
    """
    Property-owned asset instance.

    We use a GenericForeignKey so we DON'T assume the AssetCode lives in an app named "assets".
    This avoids startup/system-check errors when your AssetCode model is in a different app.
    """

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="site_assets",
        db_index=True,
    )

    # Instance identifier (separate from any library/AssetCode uid)
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    # ✅ NEW: Barcode (scanned by techs)
    # Use null=True so unique is compatible with "blank" (multiple NULLs allowed).
    barcode = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Asset barcode/QR identifier (unique if provided).",
    )

    # NEW location fields requested
    block = models.CharField(max_length=50, blank=True)
    level = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=200, blank=True)

    # Stores optional dropdown selections (varies per asset type)
    attributes = models.JSONField(default=dict, blank=True)

    # Active/inactive flag for reuse in future jobs
    is_active = models.BooleanField(default=True)

    # Shared primary image for this asset
    main_image = models.ImageField(upload_to="properties/assets/", blank=True, null=True)

    # --- "AssetCode" link (generic, no hard dependency on a specific app label) ---
    asset_code_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="property_assets",
    )
    asset_code_object_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    asset_code = GenericForeignKey("asset_code_content_type", "asset_code_object_id")

    # Optional denormalized label (handy for display if the linked record is missing later)
    asset_label = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Property Asset"
        verbose_name_plural = "Property Assets"
        ordering = ["property", "asset_label", "location", "level", "block", "id"]
        indexes = [
            models.Index(fields=["property", "asset_code_content_type", "asset_code_object_id"]),
            models.Index(fields=["property", "barcode"]),
        ]

    def get_asset_display(self) -> str:
        """
        Best-effort display name:
        - If linked AssetCode exists, use its common name fields or __str__
        - Else fallback to stored asset_label
        """
        obj = self.asset_code
        if obj is not None:
            for attr in ("name", "equipment", "title", "code"):
                val = getattr(obj, attr, None)
                if val:
                    return str(val)
            return str(obj)

        return self.asset_label or "Asset"

    def __str__(self) -> str:
        label = self.get_asset_display()
        loc_bits = [b for b in [self.block, self.level, self.location] if b]
        loc = " / ".join(loc_bits)
        bc = (self.barcode or "").strip()

        if loc and bc:
            return f"{label} @ {self.property} ({loc}) [{bc}]"
        if loc:
            return f"{label} @ {self.property} ({loc})"
        if bc:
            return f"{label} @ {self.property} [{bc}]"
        return f"{label} @ {self.property}"
