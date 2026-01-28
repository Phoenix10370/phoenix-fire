from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from django.conf.urls.static import static

from .views import dashboard


def healthcheck(request):
    return dashboard(request)


urlpatterns = [
    path("admin/", admin.site.urls),

    path("", healthcheck, name="dashboard"),
    path("dashboard/", dashboard, name="dashboard"),

    path("codes/", include("codes.urls")),
    path("customers/", include("customers.urls")),
    path("properties/", include("properties.urls")),
    path("quotations/", include("quotations.urls")),
    path("routines/", include("routines.urls")),
    path("company/", include("company.urls")),
    path("email-templates/", include("email_templates.urls")),
    path("job-tasks/", include("job_tasks.urls")),

    # ✅ QBO routes live here
    path("qbo/", include("qbo.urls")),
]

# ✅ ALWAYS serve media in production (Render + gunicorn)
urlpatterns += [
    re_path(
        r"^media/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT},
    )
]

# Optional: also serve media via static() when DEBUG (harmless if left in)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
