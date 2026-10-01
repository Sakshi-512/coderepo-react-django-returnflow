from django.urls import path

from . import views

urlpatterns = [
    path("auth/login", views.login),
    path("auth/session", views.session),
    path("auth/logout", views.logout),
]
