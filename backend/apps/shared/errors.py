from rest_framework.response import Response
from rest_framework.views import exception_handler

INTERNAL_ERROR_MESSAGE = "An unexpected error occurred."


class AppError(Exception):
    def __init__(self, status_code, code, message, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class ValidationError(AppError):
    def __init__(self, form_errors, field_errors):
        details = {"formErrors": form_errors, "fieldErrors": field_errors}
        super().__init__(400, "VALIDATION_ERROR", "Request validation failed.", details)


def api_exception_handler(exc, context):
    if isinstance(exc, AppError):
        error = {"code": exc.code, "message": exc.message}

        if exc.details is not None:
            error["details"] = exc.details

        return Response({"error": error}, status=exc.status_code)

    response = exception_handler(exc, context)

    if response is not None:
        return response

    print("Unhandled error:", repr(exc))

    return Response({"error": {"code": "INTERNAL_ERROR", "message": INTERNAL_ERROR_MESSAGE}}, status=500)
