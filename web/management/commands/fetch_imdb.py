from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission
from django.utils.timezone import now
import time
import math
import random
import re
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
                print(f"Updating {unwatched.title}")
                unwatched.update_from_imdb()
                time.sleep(1)
            else:
                print(f"Skipping {unwatched.title} d={days_since_updated} c={chance}")
