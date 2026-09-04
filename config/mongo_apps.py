"""Django contrib app configs pinned to ObjectId primary keys.
The stock configs hard-code AutoField, which MongoDB does not support."""

from __future__ import annotations

from django.contrib.admin.apps import AdminConfig
from django.contrib.auth.apps import AuthConfig
from django.contrib.contenttypes.apps import ContentTypesConfig

OBJECT_ID_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"


class MongoAdminConfig(AdminConfig):
    default_auto_field = OBJECT_ID_FIELD


class MongoAuthConfig(AuthConfig):
    default_auto_field = OBJECT_ID_FIELD


class MongoContentTypesConfig(ContentTypesConfig):
    default_auto_field = OBJECT_ID_FIELD
