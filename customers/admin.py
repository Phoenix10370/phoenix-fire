from django.contrib import admin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "customer_name",
        "billing_email",
        "customer_main_phone",
        "customer_type",
        "is_active",
    )
    search_fields = (
        "customer_name",
        "billing_email",
        "customer_main_phone",
        "customer_contact_name",
        "customer_abn_acn",
    )
    list_filter = ("customer_type", "is_active")

