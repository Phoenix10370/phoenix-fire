# C:\PhoenixFire\scheduling\urls.py

from django.urls import path
from . import views

app_name = "scheduling"

from django.urls import path
from . import views

app_name = "scheduling"

urlpatterns = [
    path("", views.scheduling_view, name="index"),
    path("api/events/", views.events_feed, name="events_feed"),
    path("api/unallocated/", views.unallocated_feed, name="unallocated_feed"),
    path("api/schedule/<int:pk>/", views.schedule_jobtask, name="schedule_jobtask"),
    path("api/update/<int:pk>/", views.update_jobtask_times, name="update_jobtask_times"),
    path("api/unschedule/<int:pk>/", views.unschedule_jobtask, name="unschedule_jobtask"),
]

