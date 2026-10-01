import os
from pathlib import Path

import mongoengine
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "returnflow-django-development-key")
DEBUG = os.getenv("NODE_ENV", "development") == "development"
ALLOWED_HOSTS = ["*"]

JWT_SECRET = os.getenv("JWT_SECRET", "returnflow-secret-jwt-key-2026")
JWT_EXPIRES_IN = os.getenv("JWT_EXPIRES_IN", "24h")
JWT_ISSUER = "returnflow-api"
JWT_AUDIENCE = "returnflow-app"

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/returnflow_db")
mongoengine.connect(host=MONGODB_URI, uuidRepresentation="standard")

INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

CORS_ALLOW_ALL_ORIGINS = True

ROOT_URLCONF = "returnflow_backend.urls"

DATABASES = {}

TEMPLATES = []

REST_FRAMEWORK = {
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "apps.shared.errors.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["apps.shared.rendering.ApiRenderer"],
}

TEST_RUNNER = "apps.shared.testing.MongoTestRunner"

USE_TZ = True
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
