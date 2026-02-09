from django.urls import path
from . import views

app_name = "job_tasks"

urlpatterns = [
    path("", views.jobtask_list, name="list"),
    path("new/", views.jobtask_create, name="create"),
    path("<int:pk>/", views.jobtask_detail, name="detail"),
    path("<int:pk>/edit/", views.jobtask_update, name="edit"),
    path("<int:pk>/delete/", views.jobtask_delete, name="delete"),
    path("bulk-action/", views.bulk_action, name="bulk_action"),

    # Property-specific list
    path(
        "property/<int:property_id>/",
        views.jobtask_list_for_property,
        name="list_for_property",
    ),

    # ✅ Parent/Child job grouping
    path(
        "<int:pk>/children/add/",
        views.jobtask_child_create,
        name="child_add",
    ),
    path(
        "<int:pk>/children/bulk-create/",
        views.jobtask_children_bulk_create,
        name="children_bulk_create",
    ),

    # ✅ Property Assets actions (Job Task tab)
    path(
        "<int:pk>/property-assets/link/",
        views.jobtask_link_property_assets,
        name="link_property_assets",
    ),
    path(
        "<int:pk>/property-assets/add/",
        views.jobtask_add_property_asset,
        name="add_property_asset",
    ),
    path(
        "<int:pk>/assets/<int:asset_id>/unlink/",
        views.jobtask_unlink_property_asset,
        name="unlink_property_asset",
    ),
    path(
        "<int:pk>/assets/<int:asset_id>/deactivate/",
        views.jobtask_deactivate_property_asset,
        name="deactivate_property_asset",
    ),
    path(
        "<int:pk>/assets/<int:asset_id>/update/",
        views.jobtask_update_asset_link,
        name="update_asset_link",
    ),
    path(
        "<int:pk>/assets/bulk-update/",
        views.jobtask_bulk_update_asset_links,
        name="bulk_update_asset_links",
    ),

    # Routine-style items actions
    path("<int:pk>/items/add/", views.jobtask_item_add, name="item_add"),
    path("<int:pk>/items/<int:item_id>/delete/", views.jobtask_item_delete, name="item_delete"),
    path("<int:pk>/items/<int:item_id>/move/<str:direction>/", views.jobtask_item_move, name="item_move"),
]
