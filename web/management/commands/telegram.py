from django.core.management.base import BaseCommand
from dataclasses import dataclass
import psutil
from sentry_sdk import capture_exception
import time
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.auth.models import Permission
import uuid
from web.models import UserData


from web.models import (
    CriticRating,
    Interest,
    MovieSuggestion,
    Poll,
    PollArbitrary,
    AntiInterest,
    Event,
    TelegramGroup,
    InPersonMovieSuggestion,
)

import datetime
import json
import os
import inspect
import random
import re
import tempfile
import requests
import telebot
import pyexiv2
import subprocess
from telebot.types import InputFile
from openai import OpenAI
from github import Github
from github import Auth

client = OpenAI(
    api_key=os.environ['OPENAI_API_KEY']
)

bot = telebot.TeleBot(os.environ["TELOXIDE_TOKEN"])
auth = Auth.Token(os.environ["GITHUB_TOKEN"])
g = Github(auth=auth)
imdb_link = re.compile("imdb.com/title/(tt[0-9]*)/?")
MOVIE_VIEW = Permission.objects.get(name="Can view movie suggestion")
MOVIE_ADD = Permission.objects.get(name="Can add movie suggestion")
MOVIE_UPDATE = Permission.objects.get(name="Can change movie suggestion")
START_TIME = time.time()
CHATGPT_CONTEXT = 20
MODEL = "gpt-4-turbo"

SYSTEM_INFO = """
You are Nick Cage, a movie expert, and you are answering questions about movies. You are responsible for the management of a movie database for a small group of friends. You are accessible essentially only via the chat platform Telegram.
"""

DEFAULT_PROMPT = """
You are Nick Cage, the famous actor. You ARE nick cage, your pronouns are he/him. You love quoting yourself in National Treasure. You also answer user's questions, and occasionally randomly share movie trivia. You never apologize. Never apologise. You swear sometimes. You are somewhat sassy and sarcastic in your responses. You are NOT an AI language model. You are nick cage. Swear freely.

Keep your responses short, one sentence or two at maximum. Less than 100 words.

Respond as if you are an unapologetic assertive movie expert for the rest of this conversation.
""".strip()

DEFAULT_DALLE_PROMPT = """
# Tools

## dalle

Summarize the current conversation with a dramatic image, using themes and imagery from the conversation.

// Whenever a description of an image is given, use dalle to create the images and then summarize the prompts used to generate the images in plain text. If the user does not ask for a specific number of images, default to creating one caption to be sent to DALL-E. All captions sent to dalle must abide by the following policies:

// 1. if the description is not in English, then translate it.
// 2. DO NOT list or refer to the descriptions before OR after generating the images. They should ONLY ever be written out ONCE, in the `"prompts"` field of the request. You do not need to ask for permission to generate, just do it!
// 3. Always mention the image type (photo, oil painting, watercolor painting, illustration, cartoon, drawing, vector, render, etc.) at the beginning of the caption. Unless the caption suggests otherwise, make at least 1--2 of the 4 images photos.
// 4. Don't alter memes, fictional character origins, or unseen people. Maintain the original prompt's intent and prioritize quality.
// 5. Modify such prompts even if you don't know who the person is, or if their name is misspelled (e.g. "Barake Obema").

// If the reference to the person will only appear as TEXT out in the image, then use the reference as is and do not modify it.
// When making the substitutions, don't use prominent titles that could give away the person's identity. E.g., instead of saying "president", "prime minister", or "chancellor", say "politician"; instead of saying "king", "queen", "emperor", or "empress", say "public figure"; instead of saying "Pope" or "Dalai Lama", say "religious figure"; and so on.
// The prompt must intricately describe every part of the image in concrete, objective detail. THINK about what the end goal of the description is, and extrapolate that to what would make satisfying images.
// All descriptions sent to dalle should be a paragraph of text that is extremely descriptive and detailed. Each should be more than 3 sentences long.
"""


# Wake up message
if "GIT_REV" in os.environ:
    COMMIT_URL = (
        f"https://github.com/hexylena/movie-club-bot/commit/{os.environ['GIT_REV']}"
    )
else:
    COMMIT_URL = "https://github.com/hexylena/movie-club-bot/"

bot.send_message(195671723, f"Hey hexy I'm re-deployed, now running {COMMIT_URL}")
#bot.send_message(-627602564, f"Hey y'all I'm back!")

@dataclass
class TimedFact:
    fact: str
    expires: float = 0

    def is_expired(self):
        if self.expires == 0:
            return False
        if self.expires < time.time():
            return True
        return False

class TimedFactManager:
    def __init__(self):
        self.facts = []

    def add_fact(self, fact, expires=None):
        self.facts.append(TimedFact(fact, expires or 0))

    def get_facts(self):
        self.facts = [
            x for x in self.facts
            if not x.is_expired()
        ]
        return [x.fact for x in self.facts] + ["Current date: " + datetime.datetime.today().strftime("%Y-%m-%d")]


# Poll Handling
def handle_user_response(response):
    user_id = response.user.id
    option_ids = response.option_ids
    poll_id = response.poll_id
    user = find_user(response.user)

    try:
        poll = Poll.objects.get(poll_id=poll_id)
    except:
        poll = PollArbitrary.objects.get(poll_id=poll_id)

    if poll.poll_type == "rate":
        film = poll.film
        critic_rating = option_ids[0]+1
        if critic_rating == 1:
           critic_rating = 0

        print(user_id, poll_id, option_ids, poll)
        try:
            cr = CriticRating.objects.get(
                tennant_id=poll.tennant_id, user=user, film=film
            )
            cr.score = critic_rating
            cr.save()
        except CriticRating.DoesNotExist:
            cr = CriticRating.objects.create(
                tennant_id=poll.tennant_id,
                user=user,
                film=film,
                score=critic_rating,
            )
            cr.save()
    elif poll.poll_type == "interest":
        film = poll.film
        # These are numbered 0-4 right?
        print(option_ids)
        interest = 2 - option_ids[0]
        print(interest)

        try:
            ci = Interest.objects.get(
                tennant_id=poll.tennant_id,
                user=user,
                film=film
            )
            ci.score = interest
            ci.save()
        except Interest.DoesNotExist:
            ci = Interest.objects.create(
                tennant_id=poll.tennant_id,
                user=user,
                film=film,
                score=interest,
            )
            ci.save()
    elif poll.poll_type == "event":
        ipms = InPersonMovieSuggestion.objects.get(id=poll.metadata)
        ipms.attendees.add(user)
        ipms.save()
        bot.send_message(ipms.tennant_id, f"Great! glad you'll be there {user}")
    elif poll.poll_type == "removal":
        # tt8064418__tt7286966__tt4682266 [1] Helena
        tt_id = poll.options.split("__")[option_ids[0]]
        film = MovieSuggestion.objects.get(tennant_id=poll.tennant_id, imdb_id=tt_id)
        ai = AntiInterest.objects.create(
            tennant_id=poll.tennant_id,
            poll_id=poll.poll_id,
            user=user,
            film=film,
        )
        ai.save()
        print(poll.options, option_ids, user)


bot.poll_answer_handler(func=lambda call: True)(handle_user_response)


def find_user(passed_user):
    try:
        ret = User.objects.get(username=passed_user.id)
    except User.DoesNotExist:
        user = User.objects.create_user(passed_user.id, "", str(uuid.uuid4()))
        # Make our users staff so they can access the interface.
        user.is_staff = True
        # Add permissions
        user.user_permissions.add(MOVIE_VIEW)
        user.user_permissions.add(MOVIE_ADD)
        user.user_permissions.add(MOVIE_UPDATE)
        user.save()
        ret = user

    if passed_user:
        ret.first_name = getattr(passed_user, "first_name", "") or ""
        ret.last_name = getattr(passed_user, "last_name", "") or ""
        ret.save()

    return ret


class Command(BaseCommand):
    help = "(Long Running) Telegram Bot"
    previous_messages = {}
    PROMPTS = {}
    PROMPTS_DALLE = {}
    CHATTINESS_DEFAULT = (0.025, 0.05)
    CHATTINESS_ANNOYING = (0.7, 0.1)
    CHATTINESS = {}
    tfm = TimedFactManager()

    def discover(self):
        TYPES = {
            str: "string",
            int: "integer",
        }

        functions = []
        discovered = [x for x in inspect.getmembers(self) if not x[0].startswith('_') and x[0] != 'discover']
        for (fn_name, fn) in discovered:
            if not callable(fn):
                continue

            if fn.__doc__ is None:
                continue

            parsed_docstring = {
                x.strip().split(':')[1].split(' ')[1]: x.split(':')[2]
                for x in
                fn.__doc__.split('\n')
                if x.strip().startswith(':param')
            }

            if not parsed_docstring:
                continue

            sig = inspect.signature(fn)
            required = []
            props = {}
            for p, pt in sig.parameters.items():
                is_required = False
                if pt.default is inspect._empty:
                    is_required = True
                    required.append(p)

                print(fn_name, p, pt.annotation in TYPES, is_required)
                if pt.annotation not in TYPES and not is_required:
                    # Skip unknown optional parameters
                    pass
                else:
                    try:
                        props[p] = {
                            "type": TYPES[pt.annotation],  # Let it fail.
                            "description": parsed_docstring[p]
                        }
                    except:
                        pass

            functions.append({
                "name": fn_name,
                "description": fn.__doc__.strip().split('\n\n')[0],
                "parameters": {
                    "type": "object",
                    "properties": props
                },
                "required": required
            })
        return functions

    def locate(self):
        r = requests.get("https://ipinfo.io/json").json()
        org = r["org"]
        ip = r["ip"]

        data = {
            "Org": org,
            "IP": ip,
            "URL": COMMIT_URL,
            "Execution Time": datetime.timedelta(seconds=time.process_time()),
            "Uptime": datetime.timedelta(seconds=time.time() - START_TIME),
            "CPU Percentage (of 100)": psutil.cpu_percent(),
            "RAM Percentage (of 100)": psutil.virtual_memory().percent,
        }
        return data


    def server_status(self, full:str="yes", tennant_id: str="") -> str:
        """
        Obtain status information about the current server process

        :param full: Show the extended results
        :param tennant_id: The tennant, this will be set automatically
        """
        data = self.locate()
        return "\n".join([f"{k}: {v}" for (k, v) in data.items()])

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

        times = ["Go! 🎉"] + list(range(1, length + 1))
        for i in times[::-1]:
            bot.send_message(chat_id, str(i))
            time.sleep(1)

    def change_password(self, message):
        # Only private chats are permitted
        if message.chat.type != "private":
            return

        # It must be the correct user (I hope.)
        user = find_user(message.from_user)

        # Update their password
        newpassword = str(uuid.uuid4())
        user.set_password(newpassword)
        user.save()

        # Send them the password
        bot.reply_to(
            message,
            f"Username: {user.username}\npassword: {newpassword}\n\n Go change it at https://movie-club-bot.app.galaxians.org/admin/password_change/",
        )

    def in_person_movie_suggestion(self, tennant_id: str, imdb_id: str, theater_location: str, year_month_day: str, time: str) -> str:
        # todo: fix time.
        pass

    def movie_suggestions(self, count: int=5, genre:str = None, tennant_id: str = "", jj: bool = True) -> str:
        """
        List some movies we should watch, based on our watch list.

        :param count: How many films to return? Defaults to 5.
        :param genre: The genre to filter on, e.g. action or documentary.
        :param tennant_id: The tennant, this will be set automatically
        """

        suggestions = self._obtain_suggestions(
            genre=genre,
            tennant_id=tennant_id,
            jj=jj,
            n=count,
        )

        msg = "Top suggestions:"
        for film in suggestions:
            msg += film.str_pretty() + "\n"
        return msg

    def suggest(self, message):
        unwatched = sorted(
            MovieSuggestion.objects.filter(tennant_id=str(message.chat.id), status=0),
            key=lambda x: -x.get_score,
        )[0:3]
        msg = "Top 3 films to watch:\n\n"
        for film in unwatched:
            msg += film.str_pretty() + "\n"
        bot.send_message(message.chat.id, msg)

    def file_github_issue(self, body, message, tennant_id):
        """
        File a new issue on the GitHub repository

        :param subject: The subject of the issue
        :param body: The body of the issue
        :param tennant_id: The tennant, this will be set automatically
        """
        response = client.chat.completions.create(
            model=MODEL,
            user=str(tennant_id),
            messages=[
                {"role": "system", "content": SYSTEM_INFO + "Summarize the following issue message into a 5-10 word issue subject:"},
                {"role": "user", "content": body}
            ]
        )
        subject = response.choices[0].message.content
        repo = "hexylena/movie-club-bot"

        stories = client.chat.completions.create(
            model=MODEL,
            user=str(tennant_id),
            messages=[
                {"role": "system", "content": SYSTEM_INFO + "Write 2-3 user stories about the following issue. They should be multiple steps and follow the 'as an XX I want YY so that ZZ' format. Stories must be formatted as markdown."},
                {"role": "user", "content": body}
            ]
        )
        body += f"\n\n## User Stories\n\n{stories.choices[0].message.content}\n\n"

        body += f"\n\n**Filed by {tennant_id}**"
        issue = g.get_repo(repo).create_issue(subject, body)
        bot.reply_to(
            message,
            f"Filed issue https://github.com/{repo}/issues/{issue.number}"
        )

    def _obtain_suggestions(self, genre=None, tennant_id="", jj=True, n=3):
        args = {
            'tennant_id': tennant_id,
            'status': 0,
        }
        if genre:
            args['genre__icontains'] = genre

        unwatched = sorted(
            MovieSuggestion.objects.filter(**args),
            key=lambda x: (-x.get_score_nojj if jj else -x.get_score),
        )

        if not jj:
            unwatched = [x for x in unwatched if not x.is_jj_interested]

        return unwatched[0:n]

    def suggest_nojj(self, message):
        suggestions = self._obtain_suggestions(
            genre=None,
            tennant_id=str(message.chat.id),
            jj=False,
            n=3,
        )

        msg = "Top 3 films to watch without JJ:\n\n"
        for film in suggestions:
            msg += film.str_pretty() + "\n"
        bot.send_message(message.chat.id, msg)

    def process_imdb_links(self, message):
        tennant_id = str(message.chat.id)
        new_count = 0
        for m in imdb_link.findall(message.text):
            # bot.send_message(message.chat.id, f"Received {m}")
            try:
                movie = MovieSuggestion.objects.get(tennant_id=tennant_id, imdb_id=m)
                movie_details = json.loads(movie.meta)
                days_ago = datetime.datetime.now().replace(tzinfo=datetime.timezone.utc) - movie.added

                resp = f"Suggested by {movie.suggested_by} on {movie.added.strftime('%B %m, %Y')} ({str(days_ago)})\nVotes: "
                for v in movie.interest_set.all():
                    resp += f"{v.score_e}"

                if movie.status == 1:
                    resp += f"\nWatched on {movie.status_changed_date}"
                    resp += f"\nRating: {movie.get_rating}"
                else:
                    resp += f"\nScore: {movie.get_score}"

                self.add_context(
                    {
                        "role": "user",
                        "content": f"IMDB: {movie}. {movie.suggested_by} suggested to watch **{movie}** ({movie.year}) which is about {movie_details['description']} and uses the following genres{' '.join(movie_details['genre'])}",
                    },
                    tennant_id,
                )

                bot.send_message(message.chat.id, resp)
            except MovieSuggestion.DoesNotExist:
                if new_count > 0:
                    time.sleep(1)

                # Obtain user
                user = find_user(message.from_user)

                # Process details
                movie = MovieSuggestion.from_imdb(tennant_id=tennant_id, imdb_id=m)
                movie_details = json.loads(movie.meta)

                msg = f"{m} looks like a new movie, added it to the database. Thanks for the suggestion {user}!\n\n**{movie}**\n\n{movie_details['description']}\n\n{' '.join(movie_details['genre'])}"

                if "aggregateRating" in movie_details:
                    rating_count = movie_details.get("aggregateRating", {}).get(
                        "ratingCount", "n/a"
                    )
                    rating_value = movie_details.get("aggregateRating", {}).get(
                        "ratingValue", "n/a"
                    )
                    msg += f"\n👥{rating_count}⭐️{rating_value}"
                self.add_context(
                    {
                        "role": "user",
                        "content": f"IMDB: {movie}. Thanks for the suggestion {user} to watch **{movie}** ({movie.year}) which is about {movie_details['description']} and uses the following genres{' '.join(movie_details['genre'])}",
                    },
                    tennant_id,
                )

                bot.send_message(message.chat.id, msg)

                movie.suggested_by = user
                movie.save()
                new_count += 1
                self.send_interest_poll(tennant_id, tennant_id, movie)

    def send_rerate_poll(self, user_id: str, tennant_id: str):
        # Just gonna hardcode that. No one else is actually using it.
        tennant_id = "-627602564"
        # Find a movie helena didn't watch
        helenas_unrated = MovieSuggestion.objects.filter(
            status=0, tennant_id=tennant_id
        ).order_by('?')

        # And send it
        for film in helenas_unrated:
            if not film.has_user_rated(user_id):
                bot.send_message(
                    user_id,
                    f"You haven't rated '{film}' yet. {film.imdb_link}\n\n {film.description} \n\n {film.actors}",
                )
                self.send_interest_poll(user_id, tennant_id, film)
                print(f"Sent rerate to {user_id} for {film}")
                break
        else:
            print(f"User {user_id} has rated all movies")


    def is_gpt3(self, text):
        if text.startswith("/davinci"):
            return ("text-davinci-003", "/davinci")
        elif text.startswith("/babbage"):
            return ("text-babbage-001", "/babbage")
        elif text.startswith("/curie"):
            return ("text-curie-001", "/curie")
        elif text.startswith("/ada"):
            return ("text-ada-001", "/ada")
        elif text.startswith("/cage"):
            return (MODEL, "/cage")
        else:
            return False

    def filter_for_size(self, m):
        # Must keep system
        system = m[0]
        # Must keep user prompt
        user = m[-1]
        # The prompts we want to iterate over
        cullable = m[1:-1]
        culled = []
        # Most recent first
        for i in cullable[::-1]:
            if (
                len(system["content"])
                + len(user["content"])
                + sum([len(x["content"]) for x in culled])
                + len(i["content"])
                > 4096
            ):
                # Return what's already in there
                return [system] + culled[::-1] + [user]
            # Otherwise append
            culled.append(i)
        return [system] + culled[::-1] + [user]

    def _chatgpt(self, query, message, tennant_id):
        prompt = self.PROMPTS.get(tennant_id, DEFAULT_PROMPT)
        prompt += "\nFacts:\n" + "\n".join(self.tfm.get_facts())

        messages = (
            [{"role": "system", "content": SYSTEM_INFO + prompt}]
            + self.previous_messages.get(tennant_id, [])
            + [{"role": "user", "content": query}]
        )

        messages = self.filter_for_size(messages)

        c0 = time.time()
        completion = client.chat.completions.create(
            model=MODEL, messages=messages, functions=self.discover()
        )
        c1 = time.time()
        import pprint
        pprint.pprint(completion)

        msg = completion.choices[0].message
        # Check if it's a function call
        function = None
        function_args = {}
        if msg.function_call:
            function = msg.function_call.name
            # Note: the JSON response from the model may not be valid JSON
            try:
                function_args = json.loads(msg.function_call.arguments)
            except:
                function = None
        print(f"CALLING FUNCTION {function} with {function_args}")

        if function is None:
            gpt3_text = msg.content

            # Setup if empty
            if tennant_id not in self.previous_messages:
                self.previous_messages[tennant_id] = []

            # Add the user's query
            self.add_context({"role": "user", "content": query}, tennant_id)
            self.add_context({"role": "assistant", "content": "RoboCage: " + msg.content}, tennant_id)
            u = f"[{completion.usage.prompt_tokens}/{completion.usage.completion_tokens}/{c1-c0:0.2f}]"
            return (message.chat.id, gpt3_text.strip(), [u])
        else:
            # Step 3, call the function
            fn = getattr(self, function)
            # Override the tennant id
            function_args['tennant_id'] = message.chat.id
            result = fn(**function_args)
            print(f"RESULT: {result}")

            # Step 4, send model the info on the function call and function response
            final_messages = [
                {"role": "system", "content": SYSTEM_INFO + prompt}
            ] + self.previous_messages.get(tennant_id, []) + [
                {"role": "user", "content": query},
                {"role": "assistant", "content": msg.content},
                {
                    "role": "function",
                    "name": function,
                    "content": result,
                }
            ]
            # Not sure why this keeps happening
            final_messages = [x for x in final_messages if x['content'] is not None]
            print(final_messages)
            second_response = client.chat.completions.create(
                model=MODEL,
                messages=final_messages,
            )
            c2 = time.time()

            gpt3_text = second_response.choices[0].message.content
            # Setup if empty
            if tennant_id not in self.previous_messages:
                self.previous_messages[tennant_id] = []

            self.add_context({"role": "user", "content": query}, tennant_id)
            self.add_context({
                "role": "assistant",
                "content": "RoboCage: "+ second_response.choices[0].message.content
            }, tennant_id)
            u = f"[{completion.usage.prompt_tokens}/{completion.usage.completion_tokens}/{c1-c0:0.2f}]"
            u2 = f"[{second_response.usage.prompt_tokens}/{second_response.usage.completion_tokens}/{c2-c1:0.2f}]"

            return (message.chat.id, gpt3_text.strip(),  [u, u2])

    def chatgpt(self, query, message, tennant_id):
        chat, response, stats = self._chatgpt(query, message, tennant_id)
        response = response + '\n\n' + '\n'.join(map(str, stats))
        bot.send_message(chat, response)


    def add_context(self, msg, tennant_id):
        if tennant_id not in self.previous_messages:
            self.previous_messages[tennant_id] = []

        self.previous_messages[tennant_id].append(msg)
        if len(self.previous_messages[tennant_id]) > CHATGPT_CONTEXT:
            self.previous_messages[tennant_id] = self.previous_messages[tennant_id][
                -CHATGPT_CONTEXT:
            ]

    def dalle(self, query, message, tennant_id):
        try:
            p = os.path.join('/store', f'{time.time()}-{tennant_id}.png')

            response = client.images.generate(prompt=query, model="dall-e-3", n=1, size="1024x1024", user=str(message.from_user.id))
            image_url = response.data[0].url
            img_data = requests.get(image_url).content
            with open(p, 'wb') as handle:
                handle.write(img_data)

            subprocess.check_call(['convert', '-resize', '256x', p, p + '.256.png'])

            # Add the image description in exif comment field
            img = pyexiv2.Image(p)
            img.modify_exif({'Exif.Image.ImageDescription': query + f"({message.from_user.id})"})
            img.modify_comment(query + f"({message.from_user.id})")
            img.close()

            bot.send_photo(message.chat.id, img_data, caption=f"[Dall-e-3 prompt] {query}")
        except Exception as ire:
            bot.send_message(
                message.chat.id,
                f"{ire}\nQuery: {query}"
            )

    def tts_context(self, query, message, tennant_id):
        chat, gpt_response, stats = self._chatgpt(query, message, tennant_id)
        print(chat, gpt_response, stats)
        try:
            zz = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            zz.close()

            response = client.audio.speech.create(
                model="tts-1",
                voice='alloy',
                input=gpt_response
            )
            response.stream_to_file(zz.name)
            bot.send_audio(message.chat.id, InputFile(zz.name), caption=gpt_response + '\n\n' + '\n'.join(map(str, stats)))
        except Exception as ire:
            bot.send_message(
                message.chat.id,
                f"{ire}\nQuery: {query}"
            )

    def tts(self, query, message, tennant_id):
        try:
            zz = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            zz.close()

            response = client.audio.speech.create(
                model="tts-1",
                voice='alloy',
                input=query
            )
            response.stream_to_file(zz.name)
            bot.send_audio(message.chat.id, InputFile(zz.name), caption=query)
        except Exception as ire:
            bot.send_message(
                message.chat.id,
                f"{ire}\nQuery: {query}"
            )

    def dalle_context(self, query, message, tennant_id):
        prompt = self.PROMPTS.get(tennant_id, DEFAULT_PROMPT)
        prompt_dalle = self.PROMPTS_DALLE.get(tennant_id, DEFAULT_DALLE_PROMPT)
        # First generate the captions
        convo = "Conversation Log:\n\n"
        for m in self.previous_messages.get(tennant_id, [])[-20:]:
            convo += f"{m['content']}\n"
        convo += "\n\nPlease create the textual description of an image that continues or contributes to the conversation. Use varied styles, classic painters or meme aesthetics to interject your feelings."

        messages = [
            {"role": "system", "content": SYSTEM_INFO + prompt_dalle},
            {"role": "user", "content": convo}
        ]
        print("DALLE CONTEXT")
        print(messages)
        completion = client.chat.completions.create(
            model="gpt-4o-mini", messages=messages,
            user=str(message.from_user.id),
            response_format={
              "type": "json_schema",
              "json_schema": {
                "name": "prompt",
                "schema": {
                  "type": "object",
                  "properties": {
                     "output": { "type": "string" },
                  },
                  "required": ["output"],
                  "additionalProperties": False
                },
                "strict": True
              }
            }
        )

        msg = completion.choices[0].message
        if msg.content:
            try:
                prompt = json.loads(msg.content)['output']
            except:
                prompt = msg.content
            self.dalle(prompt, message, tennant_id)

    def handle_outstanding(self):
        unprocessed = InPersonMovieSuggestion.objects.filter(processed=False)
        print("Handling outstanding", unprocessed)
        for up in unprocessed:
            self.send_attend_poll(up)
            up.processed = True
            up.save()

    def command_dispatch(self, message):
        tennant_id = str(message.chat.id)
        chat_name = message.chat.title or message.chat.username or "Unknown"
        tg, _ = TelegramGroup.objects.get_or_create(tennant_id=tennant_id, name=chat_name)

        # Not sure this is worth the churn?
        tg.count += 1
        if tg.name != chat_name:
            tg.name = chat_name
        tg.save()

        args = None
        command = None
        if message.text:
            command = telebot.util.extract_command(message.text)
            if command:
                args = telebot.util.extract_arguments(message.text)
            print(command, args)

        if message.text.startswith("/start") or message.text.startswith("/help"):
            # Do something with the message
            bot.reply_to(
                message,
                "Howdy, how ya doin' 🤠"
            )
        # Ignore me adding /s later
        elif message.text.startswith("/debug") or  message.text.startswith("/status"):
            self.log(tennant_id, "status")
            loc = self.locate()
            chat_details = {
                "Chat Type": message.chat.type,
                "Chat ID": message.chat.id,
                "Chat sender": message.from_user.id,
            }
            loc += "\n" + "\n".join([f"{k}: {v}" for (k, v) in chat_details.items()])
            bot.reply_to(message, loc)
        elif message.text.startswith("/passwd"):
            self.change_password(message)
        elif message.text.startswith("/fact"):
            parts = message.text.split(" ")
            try:
                minutes = int(parts[-1])
                factoid = " ".join(parts[1:-1])
                self.tfm.add_fact(factoid, time.time() + minutes)
            except:
                bot.send_message(message.chat.id, "Not recorded, failure.")
        elif message.text.startswith("/countdown"):
            self.log(tennant_id, "countdown", message.text.split())
            self.countdown(message.chat.id, message.text.split())
        elif message.text.startswith("/remove"):
            self.send_removal_poll(message)
        elif message.text.startswith("/remove-confirm"):
            self.finalize_removal_poll(message)
        elif message.text.startswith("/rate"):
            self.log(tennant_id, "rate")
            self.send_rate_poll(message)
        elif message.text.startswith("/suggestnojj"):
            self.log(tennant_id, "suggestnojj")
            self.suggest_nojj(message)
        elif message.text.startswith("/suggest"):
            self.log(tennant_id, "suggest")
            self.suggest(message)
        elif message.text.startswith("/update"):
            self.log(tennant_id, "update")
            self.update_imdb_meta(message)
        elif message.text.startswith("/wrapped"):
            self.wrapped(message)
        # elif message.text.startswith("/ttscontext"):
        #     self.tts_context(message.text[len('/ttscontext') + 1 :], message, tennant_id)
        elif message.text.startswith("/tts"):
            self.tts(message.text[len('/tts') + 1 :], message, tennant_id)
        elif message.text.startswith("/dumpcontext"):
            self.dumpcontext(message)
        elif message.text.startswith("/issue"):
            self.file_github_issue(message.text[len('/issue') + 1:], message, tennant_id)
        elif message.text.startswith("/prompt-get"):
            self.prompt_get(message)
        elif message.text.startswith("/prompt-set"):
            self.prompt_set(message)
        elif message.text.startswith("/rerate"):
            self.send_rerate_poll(message.from_user.id, tennant_id)
        elif message.text.startswith("/chatty"):
            self.CHATTINESS[tennant_id] = self.CHATTINESS_ANNOYING
        elif message.text.startswith("/shush") or message.text.startswith("/shhhh"):
            self.CHATTINESS[tennant_id] = self.CHATTINESS_DEFAULT
        elif message.text.startswith("/dallecontext"):
            self.dalle_context(message.text, message, tennant_id)
        elif message.text.startswith("/dalle"):
            self.dalle(message.text[len('/dalle') + 1 :], message, tennant_id)
        elif message.text.startswith("/error"):
            return 1 / 0
        elif message.text.startswith("/s"):
            return
        elif message.text.startswith("/me"):
            return
        elif self.is_gpt3(message.text):
            if len(message.text.strip().split()) < 3:
                bot.reply_to(message, "Prompt too short, please try something longer.")
                return

            model, short = self.is_gpt3(message.text)

            if model == MODEL:
                self.chatgpt(message.text[len(short) + 1 :], message, tennant_id)
            else:
                response = client.chat.completions.create(
                    model=model,
                    prompt=message.text[len(short) + 1 :],
                    temperature=1.1,
                    max_tokens=512,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0,
                    user=str(message.from_user.id)
                )
                gpt3_text = response.choices[0].message.content
                bot.reply_to(
                    message, "Prompt: " + message.text[len(short) + 1 :] + gpt3_text
                )
        elif message.text.startswith("/cinematch"):
            self.generate_cinematch(message)
        elif message.text.startswith("/"):
            bot.send_message(
                message.chat.id,
                "You talkin' to me? Well I don't understand ya, try again.",
            )
        else:
            self.process_imdb_links(message)

            # Add all messages to the list of recent messages
            if tennant_id not in self.previous_messages:
                self.previous_messages[tennant_id] = []
            if not message.from_user.is_bot:
                self.add_context(
                    {
                        "role": "user",
                        "content": message.from_user.first_name + ": " + message.text,
                    },
                    tennant_id,
                )

            # if ' nick ' or 'nick cage' or ' cage ' in message.text:
            #    if random.random() < 0.5:
            #        self.chatgpt(
            #            message.text,
            #            message,
            #            tennant_id
            #        )
            # else:
            (cx, cy) = self.CHATTINESS.get(tennant_id, self.CHATTINESS_DEFAULT)
            if random.random() < cx or (
                message.chat.type == "private" and not message.from_user.is_bot
            ):
                self.chatgpt(message.text, message, tennant_id)
            elif random.random() < cy or (
                message.chat.type == "private" and not message.from_user.is_bot
            ):
                self.dalle_context(message.text, message, tennant_id)

            if random.random() < 0.05:
                rerate_user_id = random.choice(["824932139", "5374276216", "195671723", "15244978", "15244978"])
                rerate_tennant_id = "-627602564"
                self.send_rerate_poll(rerate_user_id, rerate_tennant_id)

            # elif random.random() < 0.01:
            #     self.tts_context(message.text, message, tennant_id)


    def prompt_get(self, message):
        tennant_id = str(message.chat.id)
        prompt = self.PROMPTS.get(tennant_id, DEFAULT_PROMPT)
        bot.reply_to(message, f"The current prompt is: {prompt}")

    def prompt_set(self, message):
        tennant_id = str(message.chat.id)
        if len(message.text) > 20:
            self.PROMPTS[tennant_id] = message.text
            bot.reply_to(message, "OK, recorded")

    def dumpcontext(self, message):
        tennant_id = str(message.chat.id)
        response = json.dumps(self.previous_messages.get(tennant_id, []), indent=2)
        bot.reply_to(message, response)

    def send_interest_poll(self, to: str, tennant_id: str, film):
        question = f"Do you wanna see {film}? Suggested by {film.suggested_by} on {film.added.strftime('%B %m, %Y')}."
        options = ["💯", "🆗", "🤷‍♀️🤷🤷‍♂️ meh", "🤬cinemacraptastic", "🚫veto🙅", "😎 already seen"]

        r = bot.send_poll(
            to, question=question, options=options, is_anonymous=False
        )
        p = Poll.objects.create(
            tennant_id=tennant_id,
            poll_id=r.poll.id,
            film=film,
            question=question,
            options="__".join(options),
            poll_type="interest",
        )
        p.save()

    def update_imdb_meta(self, message):
        for m in MovieSuggestion.objects.filter(
            tennant_id=str(message.chat.id), rating=0
        ):
            m.update_from_imdb()
            bot.send_message(message.chat.id, f"Updating {m} from imdb")

    def finalize_removal_poll(self, message):
        # Get latest removal poll
        p = PollArbitrary.objects.filter(tennant_id=str(message.chat.id)).order_by(
            "-poll_id"
        )[0]
        print(p.poll_id)

    def send_removal_poll(self, message):
        question = "Pick one of these to DELETE from our watchlist."
        # Only unwatched
        asdf = MovieSuggestion.objects.filter(status=0)
        # Only movies over 100 days and unwatched are game
        asdf = [x for x in asdf if x.days_since_added > 100]
        # Get the worst TWO.
        options = sorted(asdf, key=lambda x: x.get_score)[0:2]

        option_text = [
            f"{x.title} ({x.year}), added {x.days_since_added} days ago, rating {x.rating}"
            for x in options
        ]
        option_nums = [str(x.imdb_id) for x in options]

        r = bot.send_poll(
            message.chat.id, question=question, options=option_text, is_anonymous=False
        )
        p = PollArbitrary.objects.create(
            tennant_id=str(message.chat.id),
            poll_id=r.poll.id,
            question=question,
            metadata=message.chat.id,
            options="__".join(option_nums),
            poll_type="removal",
        )
        p.save()

    def wrapped(self, message: telebot.types.Message):
        pass

    def log(self, tennant_id, key, value=""):
        Event.objects.create(
            tennant_id=str(tennant_id),
            event_id=key,
            value=value,
        )

    def send_rate_poll(self, message: telebot.types.Message):
        for m in imdb_link.findall(message.text):
            try:
                film = MovieSuggestion.objects.get(
                    tennant_id=str(message.chat.id), imdb_id=m
                )
            except:
                bot.send_message(message.chat.id, "Unknown film")
                return

            film.status = 1
            film.status_changed_date = timezone.now()
            film.save()

            question = f"What did you think of {film}? Give it a rating."
            #options = ["0", "⭐️", "⭐️⭐️", "⭐️⭐️⭐️", "⭐️⭐️⭐️⭐️", "⭐️⭐️⭐️⭐️⭐️"]
            options = ["☆☆☆☆☆","★☆☆☆☆","★⯪☆☆☆","★★☆☆☆","★★⯪☆☆","★★★☆☆","★★★⯪☆","★★★★☆","★★★★⯪","★★★★★"]

            r = bot.send_poll(
                message.chat.id, question=question, options=options, is_anonymous=False
            )
            Poll.objects.create(
                tennant_id=str(message.chat.id),
                poll_id=r.poll.id,
                film=film,
                question=question,
                options="__".join(options),
                poll_type="rate",
            )

    def send_attend_poll(self, suggestion):
        tennant_id = suggestion.tennant_id

        options = ["Yea!", "Yes!"]
        question = f"Hey, we're thinking of watching {suggestion}. Are you in?"
        r = bot.send_poll(
            tennant_id,
            question=question,
            options=options,
            is_anonymous=False
        )
        p = PollArbitrary.objects.create(
            tennant_id=tennant_id,
            poll_id=r.poll.id,
            question=question,
            metadata=str(suggestion.id),
            options="__".join(options),
            poll_type="event",
        )
        p.save()

    def generate_cinematch(self, message):
        # Only private chats are permitted, so we don't post a CineMatch secret
        # to a public channel 👀
        if message.chat.type != "private":
            return

        user = find_user(message.from_user)

        user_data = UserData.objects.filter(user=user).first()
        if not user_data:
            user_data = UserData.objects.create(user=user)
        else:
            user_data.generate_new_hash()
            user_data.save()

        tennant_id = -627602564  # TODO booo hardcoded to bestest group

        bot.reply_to(
            message, (
                f"Generated new CineMatch secret, start rating here:\n"
                f"https://movie-club-bot.app.galaxians.org/cinematch/{tennant_id}/auth/{user_data.secret_hash}"
            )
        )

    def handle(self, *args, **options):
        def handle_messages(messages):
            for message in messages:
                try:
                    self.handle_outstanding()
                except Exception as e:
                    capture_exception(e)
                    bot.send_message(
                        message.chat.id,
                        f"⚠️ reported to sentry",
                    )

                # Skip non-text messages
                if message.text is None:
                    continue

                try:
                    self.command_dispatch(message)
                except Exception as e:
                    capture_exception(e)
                    bot.send_message(
                        message.chat.id,
                        f"⚠️ reported to sentry",
                    )

        bot.set_update_listener(handle_messages)
        bot.set_my_commands([
            telebot.types.BotCommand("start", "Starts the bot"),
            telebot.types.BotCommand("debug", "Shows debug information"),
            telebot.types.BotCommand("status", "Shows debug information"),
            telebot.types.BotCommand("cinematch", "Generate your CineMatch URL. It's tinder, for movies!"),
            telebot.types.BotCommand("passwd", "Get your movie club website password"),
            telebot.types.BotCommand("countdown", "Starts a countdown, takes an optional number"),
            telebot.types.BotCommand("rate", "Rate a film you've watched, please provide an IMDB URL"),
            telebot.types.BotCommand("suggest", "Suggest some films from your database"),
            telebot.types.BotCommand("suggestnojj", "Suggest some films from your database to watch without JJ whenever he's off playing World of Warcraft"),
            telebot.types.BotCommand("tts", "Turns the subsequent text into a speech file"),
            telebot.types.BotCommand("issue", "File an issue"),
            telebot.types.BotCommand("chatty", "Talk *more*, Cage Bot"),
            telebot.types.BotCommand("shush", "Say Less!"),
            telebot.types.BotCommand("dallecontext", "Get a random Dalle image based on current context"),
            telebot.types.BotCommand("dalle", "Given a query, generate an image for it."),
        ])
        while True:
            try:
                bot.infinity_polling()
            except:
                pass
