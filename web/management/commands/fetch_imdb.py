from django.core.management.base import BaseCommand
from django.utils.timezone import now
from web.utils import get_tmdb_id
import time
import math
import random
import web.models
import datetime


class Command(BaseCommand):
    help = "Update existing user permissions"

    def handle(self, *args, **options):
        years_2 = (now() - datetime.timedelta(days=365 * 2)).year

        # There's no point in checking anything over 2 years old, it
        # probably hasn't changed much since we imported it.
        for unwatched in web.models.MovieSuggestion.objects.filter(status=0, year__gt=years_2):
            # calculate whether or not to refresh based on age.

            # Generate a % chance to refresh based on age
            # where 0 days since updated = 0%
            # 730 days since updated = 50%
            # Should use a sigmoid.

            if unwatched.imdb_update is None:
                days_since_updated = 730
            else:
                days_since_updated = (now() - unwatched.imdb_update).days

            chance = 1 / (1 + math.exp(-0.01 * (days_since_updated - 730)))

            if random.random() < chance * 10:
                print(f"[IMDB] Updating {unwatched.title}")
                unwatched.update_from_imdb()
                time.sleep(1)


        for missing_tmdb in web.models.MovieSuggestion.objects.filter(tmdb_id=None):
            # calculate whether or not to refresh based on age.

            # Generate a % chance to refresh based on age
            # where 0 days since updated = 0%
            # 730 days since updated = 50%
            # Should use a sigmoid.

            if missing_tmdb.imdb_update is None:
                days_since_updated = 730
            else:
                days_since_updated = (now() - missing_tmdb.imdb_update).days

            chance = 1 / (1 + math.exp(-0.01 * (days_since_updated - 730)))

            if random.random() < chance * 10:
                print(f"Finding missing TMDB ID for {missing_tmdb.title}")

                missing_tmdb.tmdb_id = get_tmdb_id(missing_tmdb.imdb_id)
                if missing_tmdb.tmdb_id is not None:
                    missing_tmdb.save()
                time.sleep(1)

        # There's no point in checking anything over 2 years old, it
        # probably hasn't changed much since we imported it.
        for unwatched in web.models.MovieSuggestion.objects.filter(status=0, year__gt=years_2):
            # calculate whether or not to refresh based on age.

            # Generate a % chance to refresh based on age
            # where 0 days since updated = 0%
            # 730 days since updated = 50%
            # Should use a sigmoid.

            if unwatched.imdb_update is None:
                days_since_updated = 730
            else:
                days_since_updated = (now() - unwatched.imdb_update).days

            chance = 1 / (1 + math.exp(-0.01 * (days_since_updated - 730)))

            if random.random() < chance * 10:
                print(f"[TMDB] Updating {unwatched.title}")
                unwatched.update_from_tmdb()
                time.sleep(1)
