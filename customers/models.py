from django.db import models


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

    # Core
    customer_name = models.CharField(max_length=200)
    customer_address = models.TextField(blank=True, default="")

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
