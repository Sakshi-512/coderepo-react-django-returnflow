from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.inventory import services as inventory_service
from apps.refunds import services as refund_service
from apps.shared.authentication import require_role, require_workspace_auth
from apps.shared.errors import AppError

from . import services
from .schema import validate_inspect, validate_list, validate_reject, validate_submit


@api_view(["GET", "POST"])
@require_workspace_auth
def return_requests(request):
    if request.method == "POST":
        if request.account["role"] != "customer":
            raise AppError(403, "ROLE_FORBIDDEN", "Only customers submit returns.")

        return Response({"data": services.submit_return(validate_submit(request.data), request.account)}, status=201)

    return Response({"data": services.list_returns(validate_list(request.query_params), request.account)})


@api_view(["GET"])
@require_workspace_auth
def return_request(request, return_id):
    return Response({"data": services.get_by_id(return_id, request.account)})


@api_view(["POST"])
@require_workspace_auth
def cancel_return(request, return_id):
    if request.account["role"] != "customer":
        raise AppError(403, "ROLE_FORBIDDEN", "Only the owning customer can cancel a return.")

    return Response({"data": services.cancel(return_id, request.account)})


@api_view(["POST"])
@require_workspace_auth
@require_role("agent", "manager")
def approve_return(request, return_id):
    return Response({"data": services.approve(return_id, request.account)})


@api_view(["POST"])
@require_workspace_auth
@require_role("agent", "manager")
def reject_return(request, return_id):
    values = validate_reject(request.data)

    return Response({"data": services.reject(return_id, request.account, values["reasonCode"], values["reasonNote"])})


@api_view(["POST"])
@require_workspace_auth
@require_role("warehouse", "manager")
def receive_return(request, return_id):
    return Response({"data": services.receive(return_id, request.account)})


@api_view(["POST"])
@require_workspace_auth
@require_role("warehouse", "manager")
def inspect_return(request, return_id):
    values = validate_inspect(request.data)

    return Response({"data": services.inspect(return_id, request.account, values["verdict"], values["notes"])})


@api_view(["POST"])
@require_workspace_auth
def refund_attempt(request, return_id):
    return_doc = services.ensure_viewable(return_id, request.account)

    return Response({"data": refund_service.advance(return_doc)})


@api_view(["POST"])
@require_workspace_auth
@require_role("manager")
def refund_retry(request, return_id):
    return_doc = services.ensure_viewable(return_id, request.account)

    return Response({"data": refund_service.retry(return_doc, request.account)})


@api_view(["GET"])
@require_workspace_auth
def refund_history(request, return_id):
    return_doc = services.ensure_viewable(return_id, request.account)

    return Response({"data": refund_service.history(return_doc)})


@api_view(["POST"])
@require_workspace_auth
@require_role("agent", "manager")
def exchange_retry(request, return_id):
    return_doc = services.ensure_viewable(return_id, request.account)

    return Response({"data": inventory_service.retry(return_doc, request.account)})


@api_view(["GET"])
@require_workspace_auth
def reservation_detail(request, return_id):
    return_doc = services.ensure_viewable(return_id, request.account)

    return Response({"data": inventory_service.reservation(return_doc)})
