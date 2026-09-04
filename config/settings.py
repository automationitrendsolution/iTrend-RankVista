"""Django settings for iTrend RankVista.
Every environment-specific value is read from the process environment."""

from __future__ import annotations

import os
from pathlib import Path

from django_mongodb_backend import parse_uri
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# The encryption key lives outside .env so the credential file alone is useless.
load_dotenv(BASE_DIR / ".env.key")
load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key) or default)
    except (TypeError, ValueError):
        return default


def env_secret(key: str, default: str = "") -> str:
    """Read a credential, decrypting an `enc:` value produced by `manage.py secrets_tool`."""
    from apps.common.secrets import resolve

    return resolve(os.environ.get(key, default))


def env_list(key: str, default: str = "") -> list[str]:
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
DEBUG = env_bool("DEBUG", False)

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-local-development-key-do-not-use-in-production"
    else:
        raise RuntimeError("SECRET_KEY must be set when DEBUG is false.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

ENABLE_DJANGO_ADMIN = env_bool("ENABLE_DJANGO_ADMIN", False)

INSTALLED_APPS = [
    "config.mongo_apps.MongoAuthConfig",
    "config.mongo_apps.MongoContentTypesConfig",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_htmx",
    "apps.common",
    "apps.core",
    "apps.accounts",
    "apps.projects",
    "apps.asins",
    "apps.keywords",
    "apps.rankings",
    "apps.analytics",
    "apps.audit",
]

if ENABLE_DJANGO_ADMIN:
    INSTALLED_APPS.insert(0, "config.mongo_apps.MongoAdminConfig")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.common.context_processors.branding",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# MongoDB is the only datastore: Django ORM (auth, sessions, audit) runs on the
# official django-mongodb-backend; analytics collections use the repositories.
MONGODB_URI = env_secret("MONGODB_URI", "mongodb://127.0.0.1:27017/")
MONGODB_DATABASE = env("MONGODB_DATABASE", "rankvista")

DATABASES = {
    "default": parse_uri(MONGODB_URI, db_name=MONGODB_DATABASE),
}

DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"

# Django contrib apps ship AutoField migrations; MongoDB needs ObjectId variants.
MIGRATION_MODULES = {
    "admin": "mongo_migrations.admin",
    "auth": "mongo_migrations.auth",
    "contenttypes": "mongo_migrations.contenttypes",
}

MONGODB = {
    "URI": MONGODB_URI,
    "DATABASE": MONGODB_DATABASE,
    "TIMEOUT_MS": env_int("MONGODB_TIMEOUT_MS", 5000),
    "COLLECTIONS": {
        "projects": env("MONGODB_COLLECTION_PROJECTS", "projects"),
        "asins": env("MONGODB_COLLECTION_ASINS", "asins"),
        "keywords": env("MONGODB_COLLECTION_KEYWORDS", "keywords"),
        "rankings": env("MONGODB_COLLECTION_RANKINGS", "rankings"),
    },
}

# Read-only MySQL warehouse holding the live rank history.
SOURCE_DB = {
    "ENABLED": env_bool("SOURCE_DB_ENABLED", False),
    "HOST": env("SOURCE_DB_HOST"),
    "PORT": env_int("SOURCE_DB_PORT", 3306),
    "USER": env("SOURCE_DB_USER"),
    "PASSWORD": env_secret("SOURCE_DB_PASSWORD"),
    "NAME": env("SOURCE_DB_NAME"),
    "TIMEOUT": env_int("SOURCE_DB_TIMEOUT", 15),
    "READ_TIMEOUT": env_int("SOURCE_DB_READ_TIMEOUT", 60),
    "TABLES": {
        "ranks": env("SOURCE_DB_RANK_TABLE", "datarova_rank_history"),
        "asins": env("SOURCE_DB_ASIN_TABLE", "datarova_asin_registry"),
        "keywords": env("SOURCE_DB_KEYWORD_TABLE", "datarova_asin_keyword_summary"),
        "categories": env("SOURCE_DB_CATEGORY_TABLE", "datarova_asin_category"),
        "sync_log": env("SOURCE_DB_SYNC_TABLE", "datarova_sync_log"),
    },
}

# Cache: Redis, degrading to local memory when unreachable.
REDIS_URL = env_secret("REDIS_URL", "redis://127.0.0.1:6379/0")
CACHE_TIMEOUT_SECONDS = env_int("CACHE_TIMEOUT_SECONDS", 300)

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "TIMEOUT": CACHE_TIMEOUT_SECONDS,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "rankvista-locmem",
            "TIMEOUT": CACHE_TIMEOUT_SECONDS,
        }
    }

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/projects/"
LOGOUT_REDIRECT_URL = "/login/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------
LANGUAGE_CODE = env("LANGUAGE_CODE", "en-us")
TIME_ZONE = env("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Static files
# --------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 24 * 14)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# Logging: never emit credentials, tokens or cookies.
LOG_LEVEL = env("LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "filters": {
        "redact_sensitive": {"()": "apps.common.logging_filters.RedactSensitiveFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "filters": ["redact_sensitive"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "pymongo": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "rankvista": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
    },
}

# --------------------------------------------------------------------------
# Branding
# --------------------------------------------------------------------------
BRAND = {
    "NAME": "iTrend RankVista",
    "SHORT_NAME": "RankVista",
    "COMPANY": "iTrend Solutions",
    "TAGLINE": "Amazon Search, ASIN & Keyword Intelligence Platform",
}
