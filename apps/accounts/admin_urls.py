from django.urls import path

from apps.accounts import admin_views, department_views

app_name = "useradmin"

# Primary keys are MongoDB ObjectIds, so the converter is str rather than int.
urlpatterns = [
    path("users/", admin_views.user_list, name="user_list"),
    path("users/new/", admin_views.user_create, name="user_create"),
    path("users/<str:pk>/edit/", admin_views.user_edit, name="user_edit"),
    path("users/<str:pk>/password/", admin_views.user_password, name="user_password"),
    path("users/<str:pk>/toggle/", admin_views.user_toggle_active, name="user_toggle"),
    path("users/<str:pk>/delete/", admin_views.user_delete, name="user_delete"),
    path("departments/", department_views.department_list, name="department_list"),
    path("departments/new/", department_views.department_create, name="department_create"),
    path("departments/<str:pk>/edit/", department_views.department_edit, name="department_edit"),
    path("departments/<str:pk>/toggle/", department_views.department_toggle, name="department_toggle"),
    path("departments/<str:pk>/delete/", department_views.department_delete, name="department_delete"),
    path("roles/", department_views.role_list, name="role_list"),
]
