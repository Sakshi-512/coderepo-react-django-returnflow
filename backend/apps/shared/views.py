from mongoengine.connection import get_db
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .errors import AppError


def database_state():
    try:
        get_db().command("ping")
    except Exception:
        return "disconnected"

    return "connected"


@api_view(["GET"])
def health(request):
    database = database_state()
    connected = database == "connected"

    return Response({"data": {"status": "ok" if connected else "degraded", "database": database}}, status=200 if connected else 503)


def route_not_found(request):
    raise AppError(404, "NOT_FOUND", f"Route {request.method} {request.path} was not found.")


@api_view(["GET", "POST", "PATCH", "PUT", "DELETE"])
def not_found(request):
    route_not_found(request)
