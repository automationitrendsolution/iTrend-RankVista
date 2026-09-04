from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.common"
    label = "common"
