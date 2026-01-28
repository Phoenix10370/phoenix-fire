from datetime import timedelta

from django.db import models
from django.utils import timezone


class QBOConnection(models.Model):
    realm_id = models.CharField(max_length=64, unique=True)

    access_token = models.TextField(blank=True, default="")
    refresh_token = models.TextField(blank=True, default="")

    expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_expires_in_seconds(self, expires_in: int) -> None:
        self.expires_at = timezone.now() + timedelta(seconds=int(expires_in))

    def __str__(self):
        return f"QBOConnection(realm_id={self.realm_id})"

class QBOObjectMap(models.Model):
    ENTITY_CHOICES = [
        ("Account", "Account"),
        ("Customer", "Customer"),
        ("Item", "Item"),
        ("Invoice", "Invoice"),
        ("Payment", "Payment"),
    ]

    entity_type = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    qbo_id = models.CharField(max_length=50)

    # Generic link to your local object (we'll fill this later)
    local_app = models.CharField(max_length=50, blank=True, default="")
    local_model = models.CharField(max_length=50, blank=True, default="")
    local_pk = models.CharField(max_length=50, blank=True, default="")

    # QBO concurrency token for updates (important later)
    qbo_sync_token = models.CharField(max_length=50, blank=True, default="")

    last_pulled_at = models.DateTimeField(null=True, blank=True)
    last_pushed_at = models.DateTimeField(null=True, blank=True)

    last_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity_type", "qbo_id"],
                name="uniq_qbo_object_by_type_and_id",
            )
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.qbo_id}"
