from django.urls import path
from . import views

app_name = "routines"

urlpatterns = [
    path("", views.ServiceRoutineListView.as_view(), name="list"),
    path("from-quotation/<int:quotation_id>/", views.create_from_quotation, name="create_from_quotation"),
    path("from-quotation/<int:quotation_id>/delete-existing/", views.delete_routines_for_quotation, name="delete_routines_for_quotation"),

    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/update-month/", views.update_month_due, name="update_month_due"),

    path("<int:pk>/add-item/", views.add_item, name="add_item"),
    path("<int:pk>/delete-item/<int:item_id>/", views.delete_item, name="delete_item"),

    path("<int:pk>/edit/", views.ServiceRoutineUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.ServiceRoutineDeleteView.as_view(), name="delete"),

    path("<int:pk>/create-job-task/", views.create_job_task, name="create_job_task"),

    # NEW
    path("<int:pk>/apply-monthly-notes/", views.apply_monthly_notes_to_all, name="apply_monthly_notes_to_all"),
]
