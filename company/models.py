# company/models.py
from django.db import models


class ClientProfile(models.Model):
    """
    Singleton table describing *your* business (not customers).
    """
    company_logo = models.ImageField(upload_to="company/logo/", blank=True, null=True)

    legal_company_name = models.CharField(max_length=255, blank=True)
    trading_name = models.CharField(max_length=255, blank=True)

    company_address = models.TextField(blank=True)

    company_phone = models.CharField(max_length=50, blank=True)
    company_email = models.EmailField(blank=True)

    company_abn = models.CharField(max_length=50, blank=True)
    company_acn = models.CharField(max_length=50, blank=True)

    accounts_phone = models.CharField(max_length=50, blank=True)
    accounts_email = models.EmailField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Client Profile"
        verbose_name_plural = "Client Profile"

    def __str__(self):
        return self.trading_name or self.legal_company_name or "Client Profile"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
