"""Django settings, configured entirely through environment variables (12-factor).

``DJANGO_ENV`` selects sane defaults: ``development`` (default) or ``production``.
See ``.env.example`` for every supported variable.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    return int(env(name, str(default)))


def env_float(name: str, default: float) -> float:
    return float(env(name, str(default)))


ENVIRONMENT = env("DJANGO_ENV", "development")
IS_PRODUCTION = ENVIRONMENT == "production"
DEBUG = env_bool("DJANGO_DEBUG", not IS_PRODUCTION)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production")
    SECRET_KEY = "insecure-development-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
# No cookies or sessions are used (stateless JSON API), so CSRF middleware has nothing to protect.
SILENCED_SYSTEM_CHECKS = ["security.W003"]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

# Stateless service: no database is needed (results are recomputed or served from cache).
DATABASES: dict = {}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# --- Static files & optional single-origin SPA hosting -------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# When set (e.g. in the Docker image) Django also serves the built React app.
FRONTEND_DIST_DIR = Path(env("FRONTEND_DIST_DIR")) if env("FRONTEND_DIST_DIR") else None
if FRONTEND_DIST_DIR and FRONTEND_DIST_DIR.is_dir():
    WHITENOISE_ROOT = FRONTEND_DIST_DIR
    WHITENOISE_INDEX_FILE = True

# --- Security ------------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "" if IS_PRODUCTION else "http://localhost:5173,http://127.0.0.1:5173"
)
if IS_PRODUCTION:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^api/health$"]  # platform health checks use plain HTTP
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 3600)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# --- Caching -------------------------------------------------------------------------------
# "default" holds many tiny weather cell-day entries; "routes" holds few, large route sets.
REDIS_URL = env("REDIS_URL")
if REDIS_URL:
    CACHES = {
        alias: {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": alias,
        }
        for alias in ("default", "routes")
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "weather",
            "OPTIONS": {"MAX_ENTRIES": 100_000, "CULL_FREQUENCY": 4},
        },
        "routes": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "routes",
            "OPTIONS": {"MAX_ENTRIES": 64},
        },
    }

# --- REST framework ------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "plan": env("THROTTLE_PLAN", "30/min"),
        "heatmap": env("THROTTLE_HEATMAP", "30/min"),
        "places": env("THROTTLE_PLACES", "120/min"),
    },
    # Number of trusted reverse proxies in front of the app, so throttling keys on the real
    # client IP rather than the load balancer's.
    "NUM_PROXIES": env_int("NUM_PROXIES", 1) if IS_PRODUCTION else None,
    "EXCEPTION_HANDLER": "api.exceptions.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Weather-Aware Truck Routing API",
    "DESCRIPTION": "Plans truck routes and ranks them by forecast weather risk and travel time.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --- Planner configuration (consumed by api.container) -------------------------------------
PLANNER = {
    "HTTP_USER_AGENT": env("HTTP_USER_AGENT", "weather-aware-truck-routing/1.0"),
    "HTTP_TIMEOUT_S": env_float("HTTP_TIMEOUT_S", 30.0),
    "ROUTING_PROVIDERS": env_list("ROUTING_PROVIDERS", "valhalla,osrm"),
    "VALHALLA_URL": env("VALHALLA_URL", "https://valhalla1.openstreetmap.de"),
    "OSRM_URL": env("OSRM_URL", "https://router.project-osrm.org"),
    "OPEN_METEO_URL": env("OPEN_METEO_URL"),
    "OPEN_METEO_API_KEY": env("OPEN_METEO_API_KEY"),
    "PHOTON_URL": env("PHOTON_URL", "https://photon.komoot.io"),
    "NOMINATIM_URL": env("NOMINATIM_URL", "https://nominatim.openstreetmap.org"),
    "WIND_BASIS": env("WIND_BASIS", "sustained"),
    "TRUCK_TARE_WEIGHT_LBS": env_float("TRUCK_TARE_WEIGHT_LBS", 35_000),
    "TRUCK_MAX_SPEED_MPH": env_float("TRUCK_MAX_SPEED_MPH", 65),
    "MAX_DEPARTURE_DAYS": env_int("MAX_DEPARTURE_DAYS", 7),
    "WEATHER_LATTICE_DEG": env_float("WEATHER_LATTICE_DEG", 0.05),
    "WEATHER_CACHE_TTL_S": env_int("WEATHER_CACHE_TTL_S", 30 * 60),
    "WEATHER_MAX_WORKERS": env_int("WEATHER_MAX_WORKERS", 4),
    "WEATHER_TIMEOUT_S": env_float("WEATHER_TIMEOUT_S", 15.0),
    "ROUTE_CACHE_TTL_S": env_int("ROUTE_CACHE_TTL_S", 60 * 60),
    "HEATMAP_MAX_CELLS": env_int("HEATMAP_MAX_CELLS", 220),
    "PLACES_CACHE_TTL_S": env_int("PLACES_CACHE_TTL_S", 24 * 60 * 60),
}

# --- Logging -------------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"django": {"level": "WARNING"}},
}
