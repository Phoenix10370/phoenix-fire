from django.urls import path

from .views import (
    PropertyCreateView,
    PropertyDeleteView,
    PropertyDetailView,
    PropertyListView,
    PropertyUpdateView,
    PropertyQuotationsView,
    PropertyRoutinesView,
    bulk_delete_routines,
    add_property_asset,
    delete_property_asset,
)

from .views_tabs import (
    PropertyAssetsView,
    PropertyKeyContactView,
    PropertyCorrespondenceView,
)

app_name = "properties"

urlpatterns = [
    path("", PropertyListView.as_view(), name="list"),
    path("new/", PropertyCreateView.as_view(), name="create"),

    path("<int:pk>/", PropertyDetailView.as_view(), name="detail"),
    path("<int:pk>/quotations/", PropertyQuotationsView.as_view(), name="quotations"),
    path("<int:pk>/routines/", PropertyRoutinesView.as_view(), name="routines"),

    # ✅ Bulk delete routines (from property routines tab)
    path("<int:pk>/routines/bulk-delete/", bulk_delete_routines, name="bulk_delete_routines"),

    # Tabs
    path("<int:pk>/assets/", PropertyAssetsView.as_view(), name="assets"),
    path("<int:pk>/key-contact/", PropertyKeyContactView.as_view(), name="key_contact"),
    path("<int:pk>/correspondence/", PropertyCorrespondenceView.as_view(), name="correspondence"),

    # ✅ Property Assets actions
    path("<int:pk>/assets/add/", add_property_asset, name="add_property_asset"),
    path("<int:pk>/assets/<int:asset_id>/delete/", delete_property_asset, name="delete_property_asset"),

    path("<int:pk>/edit/", PropertyUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", PropertyDeleteView.as_view(), name="delete"),
]
