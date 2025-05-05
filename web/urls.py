from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from . import views

def trigger_error(request):
    division_by_zero = 1 / 0

urlpatterns = [
    path("", views.tennant_list, name="home"),
    path("t/<acct>", views.index, name="index"),
    path("t/<acct>/by/country", views.country, name="country"),
    path("t/<acct>/by/company", views.company, name="company"),
    path("u/<acct>", views.profile, name="profile"),
    path("t/<acct>/stats", views.stats, name="stats"),
    path("t/<acct>/irl", views.irl_movie, name="irl"),
    path("t/<acct>/schedule", views.schedule, name="schedule"),
    path("t/<acct_uuid>/schedule.ics", views.schedule_ical, name="schedule_ical"),
    path("cinematch/<acct>/auth/<secret>", views.cinematch_auth, name="cinematch_auth"),
    path("cinematch/<acct>", views.cinematch, name="cinematch"),
    path("cinematch/<acct>/post", views.cinematch_post, name="cinematch_post"),

    path("status", views.status, name="status"),
    path("manifest.json", views.manifest, name="manifest"),
    path('sentry-debug/', trigger_error),
    path("dalle", views.dalle, name="dalle"),
    path('media/<str:path>.png', views.static_file),
    path("__debug__/", include("debug_toolbar.urls")),
]
