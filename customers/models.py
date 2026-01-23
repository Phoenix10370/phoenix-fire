from django.db import models
import uuid


class Customer(models.Model):
    TYPE_STRATA = "Strata"
    TYPE_GOV = "Government"
    TYPE_HOUSING = "Housing"
    TYPE_OTHER = "Other"

    CUSTOMER_TYPE_CHOICES = [
        (TYPE_STRATA, "Strata"),
        (TYPE_GOV, "Government"),
        (TYPE_HOUSING, "Housing"),
        (TYPE_OTHER, "Other"),
    ]

    BILLING_FACTORED = "FACTORED"
    BILLING_NON_FACTORED = "NON_FACTORED"
    BILLING_CASH = "CASH"
    BILLING_BARTERCARD = "BARTERCARD"

    BILLING_TYPE_CHOICES = [
        (BILLING_FACTORED, "Factored"),
        (BILLING_NON_FACTORED, "Non Factored"),
        (BILLING_CASH, "Cash"),
        (BILLING_BARTERCARD, "Bartercard"),
    ]

    # Core
    customer_name = models.CharField(max_length=200)
    customer_address = models.TextField(blank=True, default="")

    # System / IDs (NOT unique yet)
    company_code = models.CharField(
        max_length=12,
        editable=False,
        blank=True,
        db_index=True,
        help_text="System generated unique ID created when the client is created.",
    )

    accounting_id = models.CharField(
        max_length=64,
        editable=False,
        blank=True,
        null=True,
        db_index=True,
        help_text="Unique ID created when linked to an accounting API at a later stage.",
    )

    # Billing
    billing_type = models.CharField(
        max_length=20,
        choices=BILLING_TYPE_CHOICES,
        default=BILLING_FACTORED,
        db_index=True,
    )

    # Emails
    billing_email = models.EmailField(blank=True, default="")
    add_email = models.EmailField(blank=True, default="")

    # Phones
    customer_main_phone = models.CharField(max_length=50, blank=True, default="")
    add_phone = models.CharField(max_length=50, blank=True, default="")

    # Contact + business details
    customer_contact_name = models.CharField(max_length=200, blank=True, default="")
    customer_abn_acn = models.CharField(max_length=50, blank=True, default="")
    customer_type = models.CharField(
        max_length=20,
        choices=CUSTOMER_TYPE_CHOICES,
        default=TYPE_OTHER,
    )

    # Flags/metadata
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["customer_name"]

    def __str__(self):
        return self.customer_name

    def save(self, *args, **kwargs):
        if not self.company_code:
            import uuid
            self.company_code = uuid.uuid4().hex[:12].upper()
        super().save(*args, **kwargs)



class Site(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="sites")
    site_name = models.CharField(max_length=200)
    address = models.TextField()

    class Meta:
        ordering = ["site_name"]

    def __str__(self):
        return f"{self.customer.customer_name} – {self.site_name}"


class Contact(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "name"]

    def __str__(self):
        return f"{self.name} ({self.customer.customer_name})"
