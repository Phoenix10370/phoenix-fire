from django.urls import path
from . import views

urlpatterns = [
    # Debug / diagnostics
    path("debug/", views.qbo_debug, name="qbo_debug"),

    # OAuth
    path("connect/", views.qbo_connect, name="qbo_connect"),
    path("callback/", views.qbo_callback, name="qbo_callback"),

    # QBO endpoints
    path("companyinfo/", views.qbo_companyinfo, name="companyinfo"),
    path("customers/", views.qbo_customers, name="customers"),
    path("sync/customers/", views.qbo_sync_customers, name="sync_customers"),
    path("items/", views.qbo_items, name="items"),
    path("accounts/", views.qbo_accounts, name="accounts"),
    path("invoice/create-test/", views.qbo_create_test_invoice, name="create_test_invoice"),
]
