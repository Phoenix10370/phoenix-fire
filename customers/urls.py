from django.urls import path

from .views import (
    ContactCreateView,
    ContactDeleteView,
    ContactUpdateView,
    CustomerCreateView,
    CustomerDeleteView,
    CustomerDetailView,
    CustomerListView,
    CustomerUpdateView,
    SiteCreateView,
    SiteDeleteView,
    SiteUpdateView,
)

app_name = "customers"

urlpatterns = [
    # Customers
    path("", CustomerListView.as_view(), name="list"),
    path("new/", CustomerCreateView.as_view(), name="create"),
    path("<int:pk>/", CustomerDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", CustomerUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", CustomerDeleteView.as_view(), name="delete"),

    # Sites (nested)
    path("<int:customer_pk>/sites/new/", SiteCreateView.as_view(), name="site_create"),
    path("<int:customer_pk>/sites/<int:site_pk>/edit/", SiteUpdateView.as_view(), name="site_update"),
    path("<int:customer_pk>/sites/<int:site_pk>/delete/", SiteDeleteView.as_view(), name="site_delete"),

    # Contacts (nested)
    path("<int:customer_pk>/contacts/new/", ContactCreateView.as_view(), name="contact_create"),
    path("<int:customer_pk>/contacts/<int:contact_pk>/edit/", ContactUpdateView.as_view(), name="contact_update"),
    path("<int:customer_pk>/contacts/<int:contact_pk>/delete/", ContactDeleteView.as_view(), name="contact_delete"),
]
