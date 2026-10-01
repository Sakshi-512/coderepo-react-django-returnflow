from django.urls import path

from . import views

urlpatterns = [
    path("return-requests", views.return_requests),
    path("return-requests/<str:return_id>", views.return_request),
    path("return-requests/<str:return_id>/cancel", views.cancel_return),
    path("return-requests/<str:return_id>/approve", views.approve_return),
    path("return-requests/<str:return_id>/reject", views.reject_return),
    path("return-requests/<str:return_id>/receive", views.receive_return),
    path("return-requests/<str:return_id>/inspect", views.inspect_return),
    path("return-requests/<str:return_id>/refund/attempt", views.refund_attempt),
    path("return-requests/<str:return_id>/refund/retry", views.refund_retry),
    path("return-requests/<str:return_id>/refund", views.refund_history),
    path("return-requests/<str:return_id>/exchange/retry-reservation", views.exchange_retry),
    path("return-requests/<str:return_id>/reservation", views.reservation_detail),
]
