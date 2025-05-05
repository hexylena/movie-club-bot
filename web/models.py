from django.db import models
import uuid
from django.utils.timezone import now
import random
import secrets
import time
import pytz
import json
import isodate
import datetime
import math
from django.contrib.auth.models import User
from web.utils import get_ld_json, get_tmdb_id, get_tmdb

THEATERS = {
    'spui': 'Pathé Spuimarkt, Den Haag',
    'kuip': 'Pathé de Kuip, Rotterdam',
    'rdam': 'Pathé Schouwberplein, Rotterdam',
    'bhof': 'Pathé Buitenhof, Den Haag',
}

SHOWING_TYPES = {
    'scrx': 'ScreenX',
    'regular': 'Regular',
    '3d': '3D (Glasses Required)',
    'imax': 'IMAX',
    'imax3d': 'IMAX 3D (IMAX Glasses Required)',
    'dolby': 'Dolby™',
}

# Monkey patch, yikes.
User.__str__ = lambda self: self.first_name if self.first_name else self.username


class Buff(models.Model):
    tennant_id = models.CharField(max_length=64)
    short = models.CharField(max_length=8)
    name = models.TextField()
    value = models.FloatField()

    @property
    def value_adj(self):
        if self.short == 'spooky':
            if now().month == 10:
                return self.value
            else:
                return 0
        else:
            return self.value

    def __str__(self):
        if self.value < 0:
            return f"-{self.short}"
        else:
            return f"+{self.short}"

class CompanyInformation(models.Model):
    tmdb_id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=64)
    country = models.CharField(max_length=8)

    def __str__(self) -> str:
        return f"{self.name} [{self.country}]"

class ProductionCountry(models.Model):
    iso = models.CharField(max_length=4, primary_key=True)
    name = models.TextField()

    def __str__(self) -> str:
        return f"{self.iso} [{self.name}]"


class TelegramGroup(models.Model):
    tennant_id = models.CharField(max_length=64)
    name = models.TextField()
    count = models.IntegerField(default=0)
    uuid = models.UUIDField(default=uuid.uuid4)

    def __str__(self):
        return self.name


class InPersonMovieSuggestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    imdb_id = models.CharField(max_length=64)
    tmdb_id = models.IntegerField(null=True, blank=True)
    tennant_id = models.CharField(max_length=64)

    # Meta
    title = models.TextField(null=True, blank=True)
    runtime = models.IntegerField(null=True, blank=True)
    genre = models.TextField(null=True, blank=True)
    meta = models.TextField(null=True, blank=True)

    added = models.DateTimeField(auto_now_add=True)
    imdb_update = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    # People Going
    attendees = models.ManyToManyField(User, null=True, blank=True)

    # dinner_location = models.TextField(null=True)
    # dinner_time = models.CharField(max_length=8)
    theater_datetime = models.DateTimeField(null=True, blank=True) # , help="This *should* be processed as Europe/Amsterdam"
    theater_location = models.CharField(max_length=10, null=True, blank=True)
    showing_type = models.CharField(max_length=10, null=True, blank=True)

    processed = models.BooleanField(default=False)

    def __str__(self):
        local_tz = pytz.timezone('Europe/Amsterdam')
        dt = self.theater_datetime.astimezone(local_tz)
        return f"{self.title} at {dt.strftime('%A, %H:%M')} in {THEATERS.get(self.theater_location, self.theater_location)}"

    @property
    def runtime_f(self):
        if not self.runtime:
            return "Unknown"
        hours = self.runtime // 60
        minutes = self.runtime % 60
        if hours == 0:
            return f"{minutes}m"
        elif minutes == 0:
            return f"{hours}h"
        else:
            return f"{hours}h{minutes}m"

    @property
    def upcoming(self):
        return self.theater_datetime > now()

    def update_from_imdb(self):
        movie_details = get_ld_json(self.imdb_id)
        self.title = movie_details["name"].replace("&apos;", "'")

        try:
            r_s = isodate.parse_duration(movie_details["duration"]).seconds / 60
        except:
            r_s = 0

        try:
            g_s = ",".join(movie_details["genre"])
        except:
            g_s = ""

        self.runtime = r_s
        self.genre = g_s
        self.meta = json.dumps(movie_details)
        self.imdb_update = now()
        # Try and update it.
        if self.tmdb_id is None:
            self.tmdb_id = get_tmdb_id(self.imdb_id)
        self.save()

    @property
    def ics_start(self):
        return self.theater_datetime.strftime("%Y%m%dT%H%M%SZ")

    @property
    def ics_end(self):
        return (self.theater_datetime + datetime.timedelta(minutes=self.runtime)).strftime("%Y%m%dT%H%M%SZ")

    @property
    def needs_glasses(self):
        return '3d' in self.showing_type

    @property
    def desc(self):
        return SHOWING_TYPES.get(self.showing_type, self.showing_type)

    @property
    def location_ics(self):
        return THEATERS.get(self.theater_location, "Unknown") + ", Netherlands"



class MovieSuggestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    imdb_id = models.CharField(max_length=64)
    tmdb_id = models.IntegerField(null=True, blank=True)
    tennant_id = models.CharField(max_length=64)

    # Meta
    title = models.TextField()
    year = models.IntegerField()
    rating = models.FloatField()  # The IMDB score
    ratings = models.IntegerField()  # The IMDB number of people rating it.
    runtime = models.IntegerField()
    genre = models.TextField(null=True, blank=True)
    meta = models.TextField(null=True)

    production_countries = models.ManyToManyField(ProductionCountry, blank=True)
    production_companies = models.ManyToManyField(CompanyInformation, blank=True)

    added = models.DateTimeField(auto_now_add=True)
    # When was it last updated from IMDB, may be null
    imdb_update = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    tmdb_update = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    # Our info
    status = models.IntegerField()
    # 0: New
    # 1: Watched
    # 2: Removed
    status_changed_date = models.DateTimeField(null=True, blank=True)

    # Scoring
    # expressed_interest = models.ManyToManyField(User, blank=True)
    buffs = models.ManyToManyField(Buff, blank=True)

    suggested_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="suggestion"
    )

    @property
    def get_ourvotes(self):
        return sum([i.score for i in self.interest_set.all()])

    @property
    def get_ourvotes_emoji(self):
        return [i.score_e for i in self.interest_set.all()]

    @property
    def get_ourvotes_emoji_s(self):
        return ''.join([i.score_e for i in self.interest_set.all()])

    @property
    def runtime_f(self):
        if not self.runtime:
            return "Unknown"
        hours = self.runtime // 60
        minutes = self.runtime % 60
        if hours == 0:
            return f"{minutes}m"
        elif minutes == 0:
            return f"{hours}h"
        else:
            return f"{hours}h{minutes}m"

    @property
    def get_score(self):
        (final_score, _explanation) = self.get_score_explained()
        return final_score

    @property
    def get_ranking(self):
        unwatched = sorted(
            MovieSuggestion.objects.filter(tennant_id=self.tennant_id, status=0),
            key=lambda x: -x.get_score,
        )
        for idx, movie in enumerate(unwatched):
            if movie == self:
                return idx + 1

    @property
    def get_explanation(self):
        (_final_score, explanation) = self.get_score_explained()
        return "\n".join(explanation)

    def get_score_explained(self):
        try:
            explained_score = []

            buff_score = sum(
                [buff.value_adj for buff in self.buffs.all()]
            )  # could be in db.

            explained_score.append(f'buff_score = {buff_score}, this is the summ of any buffs that are applied like +cage.')

            if self.year < 1990:
                year_debuff = -1
                explained_score.append(f'year_debuff = 1, this movie is older than 1990.')
            else:
                year_debuff = 0
                explained_score.append(f'year_debuff = 0, this movie is more recent than 1990.')

            # Exception for unreleased
            if self.runtime == 0:
                runtime_debuff = -20 / 10
                explained_score.append(f'runtime_debuff = -2 | set because the runtime was 0 (usually for unreleased films)')
            else:
                runtime_debuff = -1 * abs(self.runtime - 90) / 10
                explained_score.append(f'runtime_debuff =  {runtime_debuff} | -1 * abs({runtime_debuff} - 90) / 10')


            # Exception for unreleased
            if self.ratings == 0:
                vote_adj = 5 * 5 + year_debuff
                explained_score.append(f'vote_adj = {vote_adj} | no ratings were available so we choose this number which includes year_debuff={year_debuff} in the calculation.')
            else:
                vote_adj = math.log10(self.ratings) * self.rating + year_debuff
                explained_score.append(f'vote_adj = {vote_adj} | log10({self.ratings} (ratings)) * self.rating + year_debuff.')

            old = self.days_since_added / 200
            explained_score.append(f'old = {old}, the number of days since it was added, divided by 200')
            # Ensure this is non-zero even if we balance it perfectly.
            interests = (sum([i.score for i in self.interest_set.all()]) + 0.5) / 4
            explained_score.append(f'interests = {interests} | calculated as (sum({[i.score for i in self.interest_set.all()]}) + 0.5)/4 interest score')

            final_score = round(interests * (runtime_debuff + buff_score + vote_adj), 2) - old
            explained_score.append(f'final_score = {final_score} | round({interests}(interests) * ({runtime_debuff}(runtime_debuff) + {buff_score}(buff_score) + {vote_adj}(vote_adj)), 2 - {old}(old)')
            explained_score.append(f'final_score = {final_score} | round({interests}(interests) * ({runtime_debuff + buff_score + vote_adj}), 2) - {old}(old)')
            explained_score.append(f'final_score = {final_score} | round({interests * (runtime_debuff + buff_score + vote_adj)}, 2) - {old}')
            return final_score, explained_score
        except:
            # Some things are weird here, dunno why.
            return 0, []

    @property
    def is_jj_interested(self):
        return self.is_user_interested('824932139')

    def is_user_interested(self, user: str):
        if not self.has_user_rated(user):
            return False
        wants = [y for y in self.interest_set.all() if y.user.username == user][0]
        if wants.score <= 0:
            return False
        return True

    def has_user_rated(self, user: str):
        v = [y.user.username == user for y in self.interest_set.all()]
        print(f"Checking if user has rated {self}: {v}")
        return any(v)

    @property
    def get_score_nojj(self):
        try:
            buff_score = sum(
                [buff.value_adj for buff in self.buffs.all()]
            )  # could be in db.
            if self.year < 1990:
                year_debuff = -1
            else:
                year_debuff = 0

            # Exception for unreleased
            if self.runtime == 0:
                runtime_debuff = -20 / 10
            else:
                runtime_debuff = -1 * abs(self.runtime - 90) / 10
            # Exception for unreleased
            if self.ratings > 0:
                vote_adj = 5 * 5 + year_debuff
            else:
                vote_adj = math.log10(self.ratings) * self.rating + year_debuff

            old = self.days_since_added / 20
            # Ensure this is non-zero even if we balance it perfectly.
            # Invert JJ's score:
            interests = (sum([
                i.score if i.user.username != '824932139' else -i.score
                for i in self.interest_set.all()
            ]) + 0.5) / 4

            return round(interests * (runtime_debuff + buff_score + vote_adj), 2) - old
        except:
            # Some things are weird here, dunno why.
            return 0

    @property
    def days_since_added(self):
        today = now()
        diff = today - self.added
        return diff.days

    @property
    def get_rating(self):
        nums = [x.score for x in self.criticrating_set.all()]

        if len(nums) == 0:
            return 0

        return sum(nums) / len(nums)

    @property
    def get_rating_nonavg(self):
        nums = [x.score for x in self.criticrating_set.all()]
        return nums

    @property
    def get_buffs(self):
        b = self.buffs.all()
        return "".join(map(str, b))

    @property
    def get_rated_2(self):
        return [str(i.user)[0].upper() for i in self.interest_set.all() if i.score == 2]

    @property
    def get_rated_1(self):
        return [str(i.user)[0].upper() for i in self.interest_set.all() if i.score == 1]

    @property
    def get_rated_0(self):
        return [str(i.user)[0].upper() for i in self.interest_set.all() if i.score == 0]

    @property
    def get_rated_m1(self):
        return [
            str(i.user)[0].upper() for i in self.interest_set.all() if i.score == -1
        ]

    @property
    def get_rated_m2(self):
        return [
            str(i.user)[0].upper() for i in self.interest_set.all() if i.score == -2
        ]
    @property
    def get_rated_m3(self):
        return [
            str(i.user)[0].upper() for i in self.interest_set.all() if i.score == -3
        ]

    @property
    def imdb_link(self):
        return f"https://www.imdb.com/title/{self.imdb_id}/"

    @property
    def description(self):
        try:
            return json.loads(self.meta)["description"]
        except:
            return "(No description available.)"

    @property
    def actors(self):
        try:
            actors = json.loads(self.meta)["actor"]
            return ', '.join([actor["name"] for actor in actors])
        except:
            return "(No actors known.)"

    def update_from_imdb(self):
        movie_details = get_ld_json(f"https://www.imdb.com/title/{self.imdb_id}/")

        # This is gross and I hate it.
        try:
            y_s = int(movie_details["datePublished"].split("-")[0])
        except:
            y_s = 0

        try:
            rv_s = movie_details["aggregateRating"]["ratingValue"]
        except:
            rv_s = 0

        try:
            rc_s = movie_details["aggregateRating"]["ratingCount"]
        except:
            rc_s = 0

        try:
            r_s = isodate.parse_duration(movie_details["duration"]).seconds / 60
        except:
            r_s = 0

        try:
            g_s = ",".join(movie_details["genre"])
        except:
            g_s = ""

        self.title = movie_details["name"].replace("&apos;", "'")
        self.year = y_s
        self.rating = rv_s
        self.ratings = rc_s
        self.runtime = r_s
        self.genre = g_s
        self.meta = json.dumps(movie_details)
        if self.tmdb_id is None:
            self.tmdb_id = get_tmdb_id(self.imdb_id)
        self.imdb_update = now()
        self.save()

    def update_from_tmdb(self):
        if self.tmdb_id is None:
            self.tmdb_id = get_tmdb_id(self.imdb_id)

        # If still not available, exit.
        if self.tmdb_id is None:
            return

        m = get_tmdb(self.tmdb_id)
        i = m.info()

        if 'production_countries' in i:
            countries = []
            for c in i['production_countries']:
                p, _ = ProductionCountry.objects.get_or_create(iso=c['iso_3166_1'], name=c['name'])
                countries.append(p)
            self.production_countries.set(countries)

        if 'production_companies' in i:
            companies = []
            for c in i['production_companies']:
                p, _ = CompanyInformation.objects.get_or_create(
                        tmdb_id=c['id'], name=c['name'], country=c['origin_country'])
                companies.append(p)
            self.production_companies.set(companies)

        self.tmdb_update = now()
        self.save()

    @classmethod
    def from_imdb(cls, tennant_id, imdb_id):
        try:
            return cls.objects.get(tennant_id=tennant_id, imdb_id=imdb_id)
        except cls.DoesNotExist:
            pass

        movie_details = get_ld_json(f"https://www.imdb.com/title/{imdb_id}/")

        # This is gross and I hate it.
        try:
            y_s = int(movie_details["datePublished"].split("-")[0])
        except:
            y_s = 0

        try:
            rv_s = movie_details["aggregateRating"]["ratingValue"]
        except:
            rv_s = 0

        try:
            rc_s = movie_details["aggregateRating"]["ratingCount"]
        except:
            rc_s = 0

        try:
            r_s = isodate.parse_duration(movie_details["duration"]).seconds / 60
        except:
            r_s = 0

        try:
            g_s = ",".join(movie_details["genre"])
        except:
            g_s = ""

        json_movie_details = json.dumps(movie_details)
        cagefactor = False
        if 'nm0000115/' in json_movie_details:
            cagefactor = True
        elif 'Nicholas Cage' in json_movie_details:
            cagefactor = True

        tmdb_id = get_tmdb_id(imdb_id)
        movie = cls(
            # IMDB Metadata
            imdb_id=imdb_id,
            tmdb_id=tmdb_id,
            tennant_id=tennant_id,
            title=movie_details["name"].replace("&apos;", "'"),
            year=y_s,
            rating=rv_s,
            ratings=rc_s,
            runtime=r_s,
            genre=g_s,
            meta=json_movie_details,
            # This is new
            status=0,
            suggested_by=None,
            # expressed_interest=[],
            added=now(),
        )
        # movie.save()
        # movie.buffs.add(Buffs.....)
        time.sleep(2 + random.random())
        return movie

    def __str__(self):
        return f"{self.title} ({self.year})"

    def str_pretty(self):
        msg = f"{self.title} ({self.year}) {self.description}\n"
        msg += f"{self.actors}\n"
        msg += f"  ⭐️{self.rating}\n"
        msg += f"  ⏰{self.runtime_f}\n"
        msg += f"  🎬{self.imdb_link}\n"
        if len(self.get_buffs) > 0:
            msg += f"  🎟{self.get_buffs}\n"
        msg += f"  📕{self.genre}\n"
        return msg


class Interest(models.Model):
    tennant_id = models.CharField(max_length=64)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    film = models.ForeignKey(MovieSuggestion, on_delete=models.CASCADE)
    score = models.IntegerField(default=0)

    class Meta:
        unique_together = (("user", "film"),)

    @property
    def score_e(self):
        return {
            2: "💯",
            1: "🆗",
            0: "🤷",
            -1: "🤬",
            -2: "🚫",
            -3: "😎"

        }.get(self.score, "?")

    def __str__(self):
        return f"({self.id}){self.user.first_name}|{self.film}|{self.score}"


class CriticRating(models.Model):
    tennant_id = models.CharField(max_length=64)
    # Us, we're the critics.
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    film = models.ForeignKey(MovieSuggestion, on_delete=models.CASCADE)
    score = models.IntegerField()

    class Meta:
        unique_together = (("user", "film"),)

    def __str__(self):
        return f"{self.user.first_name}|{self.film}|" + "★" * self.score


class Poll(models.Model):
    tennant_id = models.CharField(max_length=64)
    poll_id = models.TextField(primary_key=True)
    film = models.ForeignKey(MovieSuggestion, on_delete=models.CASCADE)
    question = models.TextField()
    options = models.TextField()
    poll_type = models.TextField()
    created = models.DateTimeField(auto_now_add=True)


class PollArbitrary(models.Model):
    tennant_id = models.CharField(max_length=64)
    poll_id = models.TextField(primary_key=True)
    metadata = models.TextField(
        blank=True, null=True
    )  # Equivalent to 'Film', but, arbitrary
    question = models.TextField()
    options = models.TextField()
    poll_type = models.TextField()
    created = models.DateTimeField(auto_now_add=True)


class AntiInterest(models.Model):
    tennant_id = models.CharField(max_length=64)
    poll_id = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    film = models.ForeignKey(MovieSuggestion, on_delete=models.CASCADE)


class Event(models.Model):
    tennant_id = models.CharField(max_length=64)
    event_id = models.TextField()  # fuck it whatever
    added = models.DateTimeField(auto_now_add=True)
    value = models.TextField()

def get_token():
    return secrets.token_urlsafe(32)

class UserData(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="user_data")
    secret_hash = models.CharField(max_length=64, default=get_token)

    def generate_new_hash(self):
        self.secret_hash = get_token()
        self.save()

    def __str__(self) -> str:
        return f"{self.user.username}"
