from django.apps import AppConfig


class AsinsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.asins"
    label = "asins"
