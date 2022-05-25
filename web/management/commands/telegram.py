from django.core.management.base import BaseCommand, CommandError
from django.db.utils import ProgrammingError

from web.models import MovieSuggestion

import isodate
from bs4 import BeautifulSoup
import datetime
import json
import os
import re
import requests
import telebot
import time

bot = telebot.TeleBot(os.environ['TELOXIDE_TOKEN'])
imdb_link = re.compile("imdb.com/title/(tt[0-9]*)/?")

class Command(BaseCommand):
    help = "(Long Running) Telegram Bot"


    def get_ld_json(self, url: str) -> dict:
        parser = "html.parser"
        req = requests.get(url)
        soup = BeautifulSoup(req.text, parser)
        return json.loads("".join(soup.find("script", {"type":"application/ld+json"}).contents))

    def locate(self, message):
        r = requests.get('https://ipinfo.io/json').json()
        bot.reply_to(message, r['org'])

    def countdown(self, chat_id, message_parts):
        if len(message_parts) == 2:
            try:
                length = int(message_parts[1])
                if length > 10:
                    length = 10
                elif length < 1:
                    length = 1
            except:
                length = 5
        else:
            length = 5

        times = ['Go! 🎉'] + list(range(1, length + 1))
        for i in times[::-1]:
            bot.send_message(chat_id, str(i))
            time.sleep(1)

    def process_imdb_links(self, message):
        new_count = 0
        for m in imdb_link.findall(message.text):
            bot.send_message(message.chat.id, f"Received {m}")
            try:
                movie = MovieSuggestion.objects.get(imdb_id=m)
                bot.send_message(message.chat.id, f"{m} known.")
            except MovieSuggestion.DoesNotExist:
                if new_count > 0:
                    time.sleep(1)

                movie_details = self.get_ld_json(f"https://www.imdb.com/title/{m}/")
                bot.send_message(message.chat.id, f"{m} looks like a new movie, added it to the database.\n\n**{movie_details['name']}**\n\n{movie_details['description']}\n\n{movie_details['genre'].join(' ')}")

                movie = MovieSuggestion.objects.create(
                    imdb_id=m,
                    title=movie_details['name'],
                    year=int(movie_details['datePublished'].split('-')[0]),
                    rating=movie_details['aggregateRating']['ratingValue'],
                    ratings=movie_details['aggregateRating']['ratingCount'],
                    runtime=isodate.parse_duration(movie_details['duration']).seconds / 60,
                    watched=False,
                    cage_factor=False,
                    rock_factor=False,
                    expressed_interest=[],
                )
                movie.save()
                bot.send_message(message.chat.id, f"{m} looks like a new movie, done.")
                new_count += 1

    def handle(self, *args, **options):
        def handle_messages(messages):
            for message in messages:
                if message.text.startswith('/start') or message.text.startswith('/help'):
                    # Do something with the message
                    bot.reply_to(message, 'Howdy, how ya doin')
                elif message.text.startswith('/locate'):
                    self.locate(message)
                elif message.text.startswith('/countdown'):
                    self.countdown(message.chat.id, message.text.split())
                else:
                    self.process_imdb_links(message)

        bot.set_update_listener(handle_messages)
        bot.infinity_polling()
