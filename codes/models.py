# codes/models.py

from django.db import models, transaction
from django.db.models import Max, Q
from django.utils.text import slugify


# =========================
# EFSM Codes
# =========================

class Code(models.Model):
    code = models.CharField(max_length=50, unique=True)
    fire_safety_measure = models.CharField(max_length=255)
    visits_per_year = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["code"]
        verbose_name = "EFSM Code"
        verbose_name_plural = "EFSM Codes"

    def __str__(self):
        return f"{self.code} - {self.fire_safety_measure}"


# =========================
# Defect Codes
# =========================

class DefectCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField()

    class Meta:
        ordering = ["code"]
        verbose_name = "Defect Code"
        verbose_name_plural = "Defect Codes"

    def __str__(self):
        return self.code


# =========================
# Dropdowns (Settings)
# =========================

class DropdownList(models.Model):
    """
    A named list you can manage in Settings.
    Examples:
      - Asset Categories
      - Asset Equipment
      - Detector Types
      - Door Types
    """
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Dropdown List"
        verbose_name_plural = "Dropdown Lists"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DropdownOption(models.Model):
    """
    An option inside a DropdownList.
    Optional parent: enables dependent dropdowns (Equipment under Category).
    """
    dropdown_list = models.ForeignKey(
        DropdownList,
        on_delete=models.CASCADE,
        related_name="options",
    )
    label = models.CharField(max_length=120)
    value = models.CharField(max_length=140, blank=True, default="")

    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        help_text="Optional parent option for dependent lists.",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]
        verbose_name = "Dropdown Option"
        verbose_name_plural = "Dropdown Options"

        # ✅ Allow duplicates across different parents (dependent dropdowns),
        # while keeping top-level (parent is NULL) unique by label.
        constraints = [
            models.UniqueConstraint(
                fields=["dropdown_list", "label"],
                condition=Q(parent__isnull=True),
                name="uq_dropdownoption_list_label_parent_null",
            ),
            models.UniqueConstraint(
                fields=["dropdown_list", "parent", "label"],
                condition=Q(parent__isnull=False),
                name="uq_dropdownoption_list_parent_label_parent_not_null",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.value:
            self.value = slugify(self.label)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.label


# =========================
# Asset Fields (Dynamic fields from Excel Row 1)
# =========================

class AssetField(models.Model):
    label = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_required = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]
        verbose_name = "Asset Field"
        verbose_name_plural = "Asset Fields"

    def save(self, *args, **kwargs):
        if not self.slug:
            s = slugify(self.label).replace("-", "_")
            self.slug = s[:255]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.label


# =========================
# Asset Codes
# =========================

class AssetCode(models.Model):
    """
    Asset Code UID auto-generated: ASSET-0001, ASSET-0002, ...
    Category/Equipment come from DropdownOption tables.

    Excel-driven optional columns (defaults) are stored in `attributes` JSONField.
    """
    PREFIX = "ASSET-"
    PAD = 4

    code = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        blank=True,
        verbose_name="Asset Code UID",
    )

    category = models.ForeignKey(
        DropdownOption,
        on_delete=models.PROTECT,
        related_name="asset_categories",
    )
    equipment = models.ForeignKey(
        DropdownOption,
        on_delete=models.PROTECT,
        related_name="asset_equipment",
    )

    frequency = models.PositiveSmallIntegerField(help_text="Times per year", default=1)

    attributes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Dynamic fields imported from Excel (only non-empty values stored).",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Asset Code"
        verbose_name_plural = "Asset Codes"

    @classmethod
    def _next_code(cls):
        with transaction.atomic():
            max_code = (
                cls.objects.select_for_update()
                .filter(code__startswith=cls.PREFIX)
                .aggregate(m=Max("code"))
            )["m"]
            next_num = 1 if not max_code else int(max_code.replace(cls.PREFIX, "")) + 1
            return f"{cls.PREFIX}{next_num:0{cls.PAD}d}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._next_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code

    def get_attribute_items_display(self):
        attrs = self.attributes or {}
        if not isinstance(attrs, dict) or not attrs:
            return []

        slug_to_label = {f.slug: f.label for f in AssetField.objects.filter(is_active=True)}
        items = []

        for slug, val in attrs.items():
            if val is None:
                continue
            if isinstance(val, str) and not val.strip():
                continue

            label = slug_to_label.get(slug, slug.replace("_", " ").title())
            items.append((label, val))

        items.sort(key=lambda x: x[0])
        return items


# =========================
# Equipment → Optional Fields mapping (Imported from Excel)
# =========================

class EquipmentOptionalField(models.Model):
    """
    For a given Equipment (DropdownOption), define:
      - which optional AssetFields apply
      - which dropdown values are allowed for each field (list of strings)

    This is the "schema" coming from your Excel.
    """
    equipment = models.ForeignKey(
        DropdownOption,
        on_delete=models.CASCADE,
        related_name="optional_fields",
    )

    field = models.ForeignKey(
        AssetField,
        on_delete=models.CASCADE,
        related_name="equipment_fields",
    )

    values = models.JSONField(
        default=list,
        blank=True,
        help_text="Allowed dropdown values for this field (strings).",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Equipment Optional Field"
        verbose_name_plural = "Equipment Optional Fields"
        constraints = [
            models.UniqueConstraint(
                fields=["equipment", "field"],
                name="uq_equipment_optional_field_equipment_field",
            )
        ]

    def __str__(self):
        return f"{self.equipment} → {self.field}"
