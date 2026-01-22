from django.urls import path
from . import views

app_name = "routines"

urlpatterns = [
    path("", views.ServiceRoutineListView.as_view(), name="list"),

    # Create routines from a quotation
    path(
        "from-quotation/<int:quotation_id>/",
        views.create_from_quotation,
        name="create_from_quotation",
    ),

    # Delete ALL routines for a quotation (testing/reset)
    path(
        "from-quotation/<int:quotation_id>/delete-existing/",
        views.delete_routines_for_quotation,
        name="delete_routines_for_quotation",
    ),

    # Routine detail + actions
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/update-month/", views.update_month_due, name="update_month_due"),

    # ✅ Routine-only EFSM items (not linked to quotation)
    path("<int:pk>/add-item/", views.add_item, name="add_item"),
    path("<int:pk>/delete-item/<int:item_id>/", views.delete_item, name="delete_item"),

    # Routine edit/delete
    path("<int:pk>/edit/", views.ServiceRoutineUpdateView.as_view(), name="edit"),

    # Routine items (inline add / delete)
    path("<int:pk>/add-item/", views.add_item, name="add_item"),
    path("<int:pk>/delete-item/<int:item_id>/", views.delete_item, name="delete_item"),

]
