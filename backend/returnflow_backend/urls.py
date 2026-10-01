from django.urls import include, path, re_path
from rest_framework.decorators import api_view

from apps.shared.authentication import require_workspace_auth
from apps.shared.views import health, not_found, route_not_found


@api_view(["GET", "POST", "PATCH", "PUT", "DELETE"])
@require_workspace_auth
def unknown_api_route(request, path):
    return route_not_found(request)


urlpatterns = [
    path("api/v1/health", health),
    path("api/v1/", include("apps.auth.urls")),
    path("api/v1/", include("apps.orders.urls")),
    path("api/v1/", include("apps.returns.urls")),
    re_path(r"^api/v1/(?P<path>.*)$", unknown_api_route),
    re_path(r"^.*$", not_found),
]
