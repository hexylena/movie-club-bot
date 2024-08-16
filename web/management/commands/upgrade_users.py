from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.auth.models import Permission
import re
import web.models


class Command(BaseCommand):
    help = "Update existing user permissions"

    def handle(self, *args, **options):
        tables = [x for x in dir(web.models) if x[0] == x[0].upper() and x[0] != '_' and x != 'User']
        fixed = [re.sub(r'([A-Z])', r' \1', x[0].lower() + x[1:]).lower() for x in tables]

        for user in User.objects.all():
            print(f"Updating {user}")
            for permission in ('view', 'add', 'change'):
                for table in fixed:
                    if '_ ' in table:
                        continue
                    print(f"  {permission} {table}")
                    user.user_permissions.add(Permission.objects.get(name=f"Can {permission} {table}"))

            user.save()

        # Remove duplicate intersts
        d = {}
        for i in web.models.Interest.objects.all():
            k = f"{i.film_id}|{i.user_id}"
            if k not in d:
                d[k] = []

            d[k].append(i)

        for k, v in d.items():
            if len(v) == 1:
                continue

            # Find the most recent one
            v = sorted(v, key=lambda x: x.id)[::-1]

            print(f"Removing duplicate interests for {k}: {v}")
            for i in v[1:]:
                i.delete()
