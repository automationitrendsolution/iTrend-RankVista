from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.projects"
    label = "projects"
