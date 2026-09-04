from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.audit"
    label = "audit"
