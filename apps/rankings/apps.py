from django.apps import AppConfig


class RankingsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.rankings"
    label = "rankings"
