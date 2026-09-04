from django.urls import path

from apps.accounts import admin_views

app_name = "useradmin"

urlpatterns = [
    path("users/", admin_views.user_list, name="user_list"),
    path("users/new/", admin_views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", admin_views.user_edit, name="user_edit"),
    path("users/<int:pk>/password/", admin_views.user_password, name="user_password"),
    path("users/<int:pk>/toggle/", admin_views.user_toggle_active, name="user_toggle"),
    path("users/<int:pk>/delete/", admin_views.user_delete, name="user_delete"),
]
