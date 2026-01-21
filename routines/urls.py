from django.urls import path
from . import views

app_name = "routines"

urlpatterns = [
    path("", views.ServiceRoutineListView.as_view(), name="list"),

    path("from-quotation/<int:quotation_id>/", views.create_from_quotation, name="create_from_quotation"),

    path("<int:pk>/", views.detail, name="detail"),

    # ✅ NEW: inline month update from detail page
    path("<int:pk>/update-month/", views.update_month_due, name="update_month_due"),

    path("<int:pk>/edit/", views.ServiceRoutineUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.ServiceRoutineDeleteView.as_view(), name="delete"),
]
