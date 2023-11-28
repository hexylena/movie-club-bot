from django.urls import path

from . import views

def trigger_error(request):
    division_by_zero = 1 / 0

urlpatterns = [
    path("", views.tennant_list, name="index"),
    path("t/<acct>", views.index, name="index"),
    path("u/<acct>", views.profile, name="profile"),
    path("status", views.status, name="status"),
    path("manifest.json", views.manifest, name="manifest"),
    path('sentry-debug/', trigger_error),
    path("dalle", views.dalle, name="dalle"),
]
