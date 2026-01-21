import os

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from .views import dashboard


# Render health checks often hit "/" with a non-browser user agent.
# Always return 200 OK by serving the dashboard.
def healthcheck(request):
    return dashboard(request)


urlpatterns = [
    path("admin/", admin.site.urls),

    # Root path (healthcheck + homepage)
    path("", healthcheck, name="dashboard"),

    # Explicit dashboard URL
    path("dashboard/", dashboard, name="dashboard"),

    path("codes/", include("codes.urls")),
    path("customers/", include("customers.urls")),
    path("properties/", include("properties.urls")),
    path("quotations/", include("quotations.urls")),
    path("routines/", include("routines.urls")),
    path("company/", include("company.urls")),
    path("email-templates/", include("email_templates.urls")),
]

# Serve uploaded media:
# - locally (DEBUG)
# - on Render (RENDER=true) using persistent disk
if settings.DEBUG or os.environ.get("RENDER", "").lower() == "true":
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
