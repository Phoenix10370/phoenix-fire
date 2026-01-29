# routines/urls.py
from django.urls import path

from . import views

app_name = "routines"

urlpatterns = [
    path("", views.ServiceRoutineListView.as_view(), name="list"),

    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/edit/", views.ServiceRoutineUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.ServiceRoutineDeleteView.as_view(), name="delete"),

    path("bulk-action/", views.bulk_action, name="bulk_action"),

    path("from-quotation/<int:quotation_id>/", views.create_from_quotation, name="create_from_quotation"),
    path("from-quotation/<int:quotation_id>/preview/", views.create_from_quotation_preview, name="create_from_quotation_preview"),

    path("delete-for-quotation/<int:quotation_id>/", views.delete_routines_for_quotation, name="delete_routines_for_quotation"),

    path("<int:pk>/apply-monthly-notes/", views.apply_monthly_notes_to_all, name="apply_monthly_notes_to_all"),
    path("<int:pk>/create-job-task/", views.create_job_task, name="create_job_task"),

    path("<int:pk>/add-item/", views.add_item, name="add_item"),
    path("<int:pk>/delete-item/<int:item_id>/", views.delete_item, name="delete_item"),

    path("<int:pk>/update-month-due/", views.update_month_due, name="update_month_due"),
]
