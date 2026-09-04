"""Root URL configuration.

The Django admin is mounted only when ENABLE_DJANGO_ADMIN is true, so the
route simply does not exist in production deployments.
"""

from django.conf import settings
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("projects/", include("apps.projects.urls")),
    path("administration/", include("apps.accounts.admin_urls")),
]

if settings.ENABLE_DJANGO_ADMIN:
    from django.contrib import admin

    urlpatterns.append(path("django-admin/", admin.site.urls))

handler400 = core_views.bad_request
handler403 = core_views.permission_denied
handler404 = core_views.page_not_found
handler500 = core_views.server_error
