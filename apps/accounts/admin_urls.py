from django.urls import path

from apps.accounts import admin_views, department_views, role_views

app_name = "useradmin"

# Primary keys are MongoDB ObjectIds, so the converter is str rather than int.
urlpatterns = [
    path("users/", admin_views.user_list, name="user_list"),
    path("users/new/", admin_views.user_create, name="user_create"),
    path("users/validate/", admin_views.user_validate, name="user_validate"),
    path("users/<str:pk>/validate/", admin_views.user_edit_validate, name="user_edit_validate"),
    path("users/<str:pk>/edit/", admin_views.user_edit, name="user_edit"),
    path("users/<str:pk>/password/", admin_views.user_password, name="user_password"),
    path("users/<str:pk>/toggle/", admin_views.user_toggle_active, name="user_toggle"),
    path("users/<str:pk>/delete/", admin_views.user_delete, name="user_delete"),
    path("departments/", department_views.department_list, name="department_list"),
    path("departments/new/", department_views.department_create, name="department_create"),
    path("departments/validate/", department_views.department_validate, name="department_validate"),
    path("departments/<str:pk>/edit/", department_views.department_edit, name="department_edit"),
    path("departments/<str:pk>/toggle/", department_views.department_toggle, name="department_toggle"),
    path("departments/<str:pk>/delete/", department_views.department_delete, name="department_delete"),
    path("roles/", role_views.role_list, name="role_list"),
    path("roles/new/", role_views.role_create, name="role_create"),
    path("roles/validate/", role_views.role_validate, name="role_validate"),
    path("roles/<str:pk>/edit/", role_views.role_edit, name="role_edit"),
    path("roles/<str:pk>/permission/", role_views.role_permission_toggle, name="role_permission_toggle"),
    path("roles/<str:pk>/delete/", role_views.role_delete, name="role_delete"),
]
