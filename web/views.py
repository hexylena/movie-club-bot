from django.shortcuts import render
import re
from django.conf import settings
import collections
from .forms import *
from .models import MovieSuggestion, TelegramGroup, Event
from django.template import loader
import requests
import datetime
import time
import glob
import os
import statistics
import collections
import datetime
import copy
import pytz
from django.http import HttpResponse
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

START_TIME = time.time()


def tennant_list(request):
    template = loader.get_template("home.html")
    groups = TelegramGroup.objects.all()

    # tennant_ids = MovieSuggestion.objects.values("tennant_id").distinct()
    # tennant_ids = [x['tennant_id'] for x in tennant_ids]

    context = {"groups": groups}
    return HttpResponse(template.render(context, request))


def index(request, acct):
    template = loader.get_template("list.html")
    try:
        tg = TelegramGroup.objects.get(tennant_id=str(acct))
    except:
        tg = "¿NO SE?"
        pass
    suggestions = MovieSuggestion.objects.filter(tennant_id=str(acct), status=0) \
        .select_related('suggested_by') \
        .prefetch_related('buffs') \
        .prefetch_related('interest_set').prefetch_related('interest_set__user') \

    watched = MovieSuggestion.objects.filter(
            tennant_id=str(acct), status=1
        ) \
        .select_related('suggested_by') \
        .prefetch_related('buffs') \
        .prefetch_related('interest_set').prefetch_related('interest_set__user') \
        .prefetch_related('criticrating_set') \
        .prefetch_related('criticrating_set__user') \
        .order_by("-status_changed_date")

    context = {
        "unwatched": sorted(
            suggestions,
            key=lambda x: -x.get_score,
        ),
        "watched": watched,
        "tennant_id": acct,
        "tg": tg,
    }
    return HttpResponse(template.render(context, request))


def dalle(request):
    images = glob.glob("/store/*.png")
    # Remove the thumbs
    images = [i for i in images if '.256.png' not in i]
    # Just the basename
    images = sorted([
        settings.MEDIA_URL + os.path.basename(x)
        for x in images
    ])[::-1]
    template = loader.get_template("dalle.html")
    return HttpResponse(template.render({'images': images}, request))


def irl_movie(request, acct):
    if request.method == "POST":
        form = InPersonMovieSuggestionForm(request.POST)
        print(form, form.is_valid())
        if form.is_valid():
            model = form.save()
            model.update_from_imdb()
            return redirect('schedule', acct=acct)
    else:
        form = InPersonMovieSuggestionForm()

    return render(request, "add_irl.html", {"form": form, 'acct': acct,})

@login_required
def schedule(request, acct):
    suggestions = InPersonMovieSuggestion.objects.filter(tennant_id=str(acct)) \
        .order_by("-theater_datetime") \
        .prefetch_related('attendees')

    return render(request, "schedule.html", {"suggestions": suggestions, 'acct': acct, 'acct_uuid': TelegramGroup.objects.get(tennant_id=acct).uuid})


# 'secret' url
def schedule_ical(request, acct_uuid):
    tg = TelegramGroup.objects.get(uuid=acct_uuid)
    suggestions = InPersonMovieSuggestion.objects.filter(tennant_id=tg.tennant_id) \
        .order_by("-theater_datetime") \
        .prefetch_related('attendees')

    template = loader.get_template("schedule.ics")
    content = template.render({"suggestions": suggestions}, request)
    return HttpResponse(content, content_type='text/calendar')


def profile(request, acct):
    template = loader.get_template("profile.html")
    u = User.objects.get(username=acct)
    suggested = u.suggestion.all().order_by("-added")

    genres = collections.Counter()

    for s in suggested:
        g = s.genre
        if g is None:
            continue

        if g.startswith("["):
            genre_list = eval(g)
            # TODO: remove later.
            s.genre = ",".join(genre_list)
            s.save()
        else:
            genre_list = g.split(",")

        for genre in genre_list:
            genres[genre] += 1

    context = {
        "acct": u,
        "suggested": suggested,
        "genres": list(genres.most_common(5)),
        "ratings": u.criticrating_set.all(),
    }
    return HttpResponse(template.render(context, request))


def stats(request, acct):
    suggestions = MovieSuggestion.objects.filter(tennant_id=str(acct), status=0) \
        .select_related('suggested_by') \
        .prefetch_related('buffs') \
        .prefetch_related('interest_set').prefetch_related('interest_set__user') \

    # Get the year from the added_date for every movie suggestion
    years = sorted(list(set([x.added.year for x in suggestions])))[::-1]

    watched = MovieSuggestion.objects.filter(
            tennant_id=str(acct), status=1
        ) \
        .select_related('suggested_by') \
        .prefetch_related('buffs') \
        .prefetch_related('interest_set').prefetch_related('interest_set__user') \
        .prefetch_related('criticrating_set') \
        .prefetch_related('criticrating_set__user') \
        .order_by("-status_changed_date")

    top_voted = sorted(watched, key=lambda x: x.get_ourvotes)[0:5]

    years = {
        year: {
            "suggestions": suggestions.filter(added__year=year),
            "watched": watched.filter(status_changed_date__year=year),
            "watched_count": watched.filter(status_changed_date__year=year).count(),
            "suggestions_count": suggestions.filter(added__year=year).count(),
            "suggested_not_watched_count": suggestions.filter(added__year=year, status=0).count(),
            "top_rated": sorted(watched.filter(status_changed_date__year=year), key=lambda x: x.get_rating_nonavg)[-6:][::-1],
            "disappointments": [
                x
                for (rating, votes, invert_votes, score, x) in
                sorted([
                    (x.get_rating, x.get_ourvotes, 5 - x.get_rating, x.get_ourvotes * (5 - x.get_rating), x ) 
                    for x in watched.filter(status_changed_date__year=year)
                ], key=lambda x: x[3])[-6:][::-1]
            ],
            "burnup": {
                k: {
                    'added_end': suggestions.filter(added__year=year, added__month__lte=k).count(),
                    'watched_end': watched.filter(status_changed_date__year=year, status_changed_date__month__lte=k).count(),
                }
                for k in range(1, 13)
            },
        }
        for year in years
    }

    # months = {(i + 1): y for (i, y) in enumerate('jan feb mar apr may jun jul aug sep oct nov dec'.split(' '))}
    months = {(i + 1): y for (i, y) in enumerate('j f m a m j j a s o n d'.split(' '))}

    local_tz = pytz.timezone('Europe/Amsterdam')

    for year in years:
        count = years[year]['suggestions_count'] + years[year]['watched_count']

        by_date = {}
        delay = {}
        for e in Event.objects.filter(event_id='countdown', tennant_id=str(acct), added__year=year):
            key = e.added.strftime('%m-%d')

            if key not in by_date:
                by_date[key] = []
                delay[key] = []

            time_local = e.added.astimezone(local_tz).strftime('%H:%M')
            by_date[key].append(time_local)

            # We start at 1930
            official_start = local_tz.localize(datetime.datetime(e.added.year, e.added.month, e.added.day, hour=19, minute=30))
            minutes_late = (e.added - official_start).total_seconds() // 60
            delay[key].append(minutes_late)

        # Distribution of false starts
        false_starts = collections.Counter([len(v) - 1 for v in by_date.values()])

        # avg delay over 1930?
        avg_delay = [max(v) for v in delay.values()]

        # number of times on-time?
        # on time (<=1930), within 15 minutes, 30 minutes, 60 minutes.
        first_start = [min(v) for v in delay.values()]
        on_time = len([x for x in first_start if x <= 0])
        w15 = len([x for x in first_start if 0 < x <= 15])
        w30 = len([x for x in first_start if 15 < x <= 30])
        w60 = len([x for x in first_start if 30 < x <= 60])
        wover = len([x for x in first_start if 60 < x])

        if len(false_starts.values()) > 0:
            vmax = max(false_starts.values())
            years[year]['start_times'] = {
                'false_starts': {k: v / vmax for (k, v) in false_starts.items()},
                'delay': {
                    'min': min(avg_delay),
                    'avg': statistics.mean(avg_delay),
                    'max': max(avg_delay),
                },
                'on_time': [on_time, w15, w30, w60, wover]
            }

        for month in years[year]['burnup']:
            years[year]['burnup'][month]['added_start'] = years[year]['burnup'][month - 1]['added_end'] if month > 1 else 0
            years[year]['burnup'][month]['watched_start'] = years[year]['burnup'][month - 1]['watched_end'] if month > 1 else 0

            years[year]['burnup'][month]['added_start_percent'] = years[year]['burnup'][month]['added_start'] / count
            years[year]['burnup'][month]['watched_start_percent'] = years[year]['burnup'][month]['watched_start'] / count
            years[year]['burnup'][month]['added_end_percent'] = years[year]['burnup'][month]['added_end'] / count
            years[year]['burnup'][month]['watched_end_percent'] = years[year]['burnup'][month]['watched_end'] / count
            years[year]['burnup'][month]['name'] = months[month]

        suggestions_year = suggestions.filter(added__year=year)
        genres = collections.Counter()

        for s in suggestions_year:
            g = s.genre
            if g is None:
                continue

            if g.startswith("["):
                genre_list = eval(g)
                # TODO: remove later.
                s.genre = ",".join(genre_list)
                s.save()
            else:
                genre_list = g.split(",")

            for genre in genre_list:
                genres[genre] += 1
        q = list(genres.most_common(1))[0][1]
        years[year]['genres'] = [
            (k, v / q)
            for (k, v)  in list(genres.most_common(5))
        ]


    context = {
        "unwatched": sorted(
            suggestions,
            key=lambda x: -x.get_score,
        ),
        "watched": watched,
        "years": years,
        "acct": acct,
        "tg": TelegramGroup.objects.get(tennant_id=acct),
    }
    template = loader.get_template("stats.html")
    return HttpResponse(template.render(context, request))


def status(request):
    template = loader.get_template("status.html")
    r = requests.get("https://ipinfo.io/json").json()
    org = r["org"]
    ip = r["ip"]
    if "GIT_REV" in os.environ:
        url = (
            f"https://github.com/hexylena/movie-club-bot/commit/{os.environ['GIT_REV']}"
        )
    else:
        url = "https://github.com/hexylena/movie-club-bot/"

    data = {
        "Org": org,
        "IP": ip,
        "URL": url,
        "Execution Time": datetime.timedelta(seconds=time.process_time()),
        "Uptime": datetime.timedelta(seconds=time.time() - START_TIME),
    }

    fmt_msg = "\n".join([f"{k}: {v}" for (k, v) in data.items()])
    return HttpResponse(template.render({"msg": fmt_msg}))


def manifest(request):
    manifest = {
        "name": "Movie Club Bot",
        "theme_color": "#f32",
        "background_color": "#fff",
        "display": "minimal-ui",
        "scope": "/",
        "start_url": "/",
        "shortcuts": [
            {
                "name": "Bot Status",
                "short_name": "Status",
                "description": "View server status information",
                "url": "/status",
            },
            {
                "name": "Admin",
                "short_name": "Admin Page",
                "description": "Login to the admin page",
                "url": "/admin/",
            },
        ],
        "description": "Movie Club Bot",
    }

    return JsonResponse(manifest)

def static_file(request, path):
    if not re.match(r'^[0-9.-]+$', path):
        return HttpResponse(status=404)
    return HttpResponse(open(os.path.join(settings.MEDIA_ROOT, path + '.png'), 'rb').read(), content_type="image/png")
