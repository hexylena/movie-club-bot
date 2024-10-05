from django.db import models
import uuid
from django.utils.timezone import now
import random
import hashlib
import time
import json
import isodate
import datetime
import math
from django.contrib.auth.models import User
from web.utils import get_ld_json

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
    theater_datetime = models.DateTimeField(null=True, blank=True)
    theater_location = models.CharField(max_length=10, null=True, blank=True)
    showing_type = models.CharField(max_length=10, null=True, blank=True)

    processed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} at {self.theater_datetime.strftime('%A, %H:%M')} in {THEATERS.get(self.theater_location, self.theater_location)}"

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
    tennant_id = models.CharField(max_length=64)

    # Meta
    title = models.TextField()
    year = models.IntegerField()
    rating = models.FloatField()  # The IMDB score
    ratings = models.IntegerField()  # The IMDB number of people rating it.
    runtime = models.IntegerField()
    genre = models.TextField(null=True, blank=True)
    meta = models.TextField(null=True)

    added = models.DateTimeField(auto_now_add=True)
    # When was it last updated from IMDB, may be null
    imdb_update = models.DateTimeField(auto_now_add=True, null=True, blank=True)

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
            interests = (sum([i.score for i in self.interest_set.all()]) + 0.5) / 4

            return round(interests * (runtime_debuff + buff_score + vote_adj), 2) - old
        except:
            # Some things are weird here, dunno why.
            return 0

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
        want_to_watch = self.interest_set.all()
        if all([y.user.username != user for y in want_to_watch]):
            return False
        return True

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
    def imdb_link(self):
        return f"https://www.imdb.com/title/{self.imdb_id}/"

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
        self.imdb_update = now()
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

        movie = cls(
            # IMDB Metadata
            imdb_id=imdb_id,
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
        try:
            meta = json.loads(self.meta)
        except:
            meta = {"description": "(No description available.)"}

        msg = f"{self.title} ({self.year}) {meta['description']}\n"
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

class UserData(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="user_data")
    secret_hash = models.CharField(max_length=64, default=lambda: hashlib.sha256().hexdigest())

    def generate_new_hash(self):
        self.secret_hash = hashlib.sha256().hexdigest()

    def __str__(self) -> str:
        return f"{self.user.username}"