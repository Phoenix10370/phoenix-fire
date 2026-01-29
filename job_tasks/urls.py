from django.urls import path
from . import views

app_name = "job_tasks"

urlpatterns = [
    path("", views.jobtask_list, name="list"),
    path("new/", views.jobtask_create, name="create"),
    path("<int:pk>/", views.jobtask_detail, name="detail"),
    path("<int:pk>/edit/", views.jobtask_update, name="edit"),
    path("<int:pk>/delete/", views.jobtask_delete, name="delete"),

    # Property-specific list
    path("property/<int:property_id>/", views.jobtask_list_for_property, name="list_for_property"),

    # Routine-style items actions
    path("<int:pk>/items/add/", views.jobtask_item_add, name="item_add"),
    path("<int:pk>/items/<int:item_id>/delete/", views.jobtask_item_delete, name="item_delete"),
    path("<int:pk>/items/<int:item_id>/move/<str:direction>/", views.jobtask_item_move, name="item_move"),
]
