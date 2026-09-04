from django.apps import AppConfig


class KeywordsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.keywords"
    label = "keywords"
