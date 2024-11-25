from django.core.management.base import BaseCommand
import os
from django.utils import timezone
import datetime
import web.models
import telebot
import time


bot = telebot.TeleBot(os.environ["TELOXIDE_TOKEN"])


class Command(BaseCommand):
    help = "Reminders cronjobs"

    def handle(self, *args, **options):
        while True:
            print(f"Scheduling reminders at {datetime.datetime.now()}")
            try:
                self.send_messages()
            except Exception as e:
                print(f"Error: {e}")
            finally:
                # We'll never see a movie around the date/time change, right? RIGHT??
                time.sleep(3600)

    def send_messages(self):
        now = timezone.now()
        for suggestion in web.models.InPersonMovieSuggestion.objects.filter(theater_datetime__gte=now):
            print(f"{suggestion} is in {suggestion.theater_datetime - now}")
            hours_until = suggestion.theater_datetime - now

            msg = f"Reminder: We're seeing {suggestion} tonight!"
            if suggestion.needs_glasses:
                msg += " Don't forget your {suggestion.showing_type} glasses!"

            if hours_until < datetime.timedelta(hours=24) and hours_until > datetime.timedelta(hours=23):
                # Gross
                msg = msg.replace("tonight!", "tomorrow night!")
                bot.send_message(suggestion.tennant_id, msg)

                for user in suggestion.attendees.all():
                    print(f"Sending message to {user.username}")
                    # bot.send_message(user.username, msg)
            elif hours_until < datetime.timedelta(hours=9) and hours_until > datetime.timedelta(hours=8):
                bot.send_message(suggestion.tennant_id, msg)
                for user in suggestion.attendees.all():
                    print(f"Sending message to {user.username}")
                    # bot.send_message(user.username, msg)
