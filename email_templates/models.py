from django.db import models


class EmailTemplate(models.Model):
    TEMPLATE_TYPES = [
        ("quotation", "Quotation"),
        ("customer", "Customer"),
        ("property", "Property"),
        ("general", "General"),
    ]

    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES, default="general")

    name = models.CharField(max_length=120, blank=True, default="")
    subject = models.CharField(max_length=255)
    body = models.TextField()

    to = models.CharField(max_length=500, blank=True, default="", help_text="Comma-separated emails (supports placeholders)")
    cc = models.CharField(max_length=500, blank=True, default="", help_text="Comma-separated emails (supports placeholders)")

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = (self.subject or "").strip()[:120]
        super().save(*args, **kwargs)

    def __str__(self):
        label = dict(self.TEMPLATE_TYPES).get(self.template_type, self.template_type)
        return f"{label}: {self.name}"
