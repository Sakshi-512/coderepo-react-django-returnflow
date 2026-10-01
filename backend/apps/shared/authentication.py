import functools

from apps.auth import services as auth_service

from .errors import AppError

BEARER_PREFIX = "Bearer "


def read_token(request):
    authorization = request.headers.get("Authorization", "")

    if not authorization.startswith(BEARER_PREFIX):
        raise AppError(401, "AUTH_REQUIRED", "Sign in to ReturnFlow to continue.")

    token = authorization[len(BEARER_PREFIX) :].strip()

    if not token:
        raise AppError(401, "AUTH_REQUIRED", "Sign in to ReturnFlow to continue.")

    return token


def require_workspace_auth(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        request.account, request.auth_payload = auth_service.authenticate(read_token(request))

        return view(request, *args, **kwargs)

    return wrapper


def require_role(*roles):
    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.account["role"] not in roles:
                raise AppError(403, "ROLE_FORBIDDEN", "Your role cannot perform this action.")

            return view(request, *args, **kwargs)

        return wrapper

    return decorator
