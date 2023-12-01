from django.db import models
import uuid
from django.utils.timezone import now
import random
import time
import json
import isodate
import math
from django.contrib.auth.models import User
from web.utils import get_ld_json

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

    def __str__(self):
        return self.name


# Create your models here.
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
    def days_since_added(self):
        today = now()
        diff = today - self.added
        return diff.days

    @property
    def get_rating(self):
        nums = CriticRating.objects.filter(film=self)
        nums = [x.score for x in nums]

        if len(nums) == 0:
            return 0

        return sum(nums) / len(nums)

    @property
    def get_rating_nonavg(self):
        nums = CriticRating.objects.filter(film=self)
        nums = [x.score for x in nums]
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
        return f"{self.user.first_name}|{self.film}|{self.score}"


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
