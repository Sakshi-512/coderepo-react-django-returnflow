from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.shared.authentication import require_workspace_auth

from . import services
from .schema import validate_login


@api_view(["POST"])
def login(request):
    email, password = validate_login(request.data)

    return Response({"data": services.login(email, password)})


@api_view(["GET"])
@require_workspace_auth
def session(request):
    return Response({"data": services.session(request.account)})


@api_view(["POST"])
@require_workspace_auth
def logout(request):
    return Response(status=204)
