from django.shortcuts import render
import re
from django.conf import settings
import collections
from .models import MovieSuggestion, TelegramGroup
from django.template import loader
import requests
import datetime
import time
import glob
import os
from django.http import HttpResponse
from django.http import JsonResponse
from django.contrib.auth.models import User

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

    for year in years:
        count = years[year]['suggestions_count'] + years[year]['watched_count']
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
