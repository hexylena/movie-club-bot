from django.contrib import admin

# Register your models here.
from .models import *


class MovieSuggestionAdmin(admin.ModelAdmin):
    list_display = ("title", "year", "rating", "status", "suggested_by", "get_score")
    list_filter = ("year", "status", "suggested_by")


admin.site.register(MovieSuggestion, MovieSuggestionAdmin)


class CriticRatingAdmin(admin.ModelAdmin):
    list_display = ("user", "film", "score")


admin.site.register(CriticRating, CriticRatingAdmin)


class BuffAdmin(admin.ModelAdmin):
    list_display = ("short", "name", "value")


admin.site.register(Buff, BuffAdmin)


class PollAdmin(admin.ModelAdmin):
    list_display = ("film", "question", "created", "poll_type")


admin.site.register(Poll, PollAdmin)


class PollArbitraryAdmin(admin.ModelAdmin):
    list_display = ("poll_id", "metadata", "question", "options", "created")


admin.site.register(PollArbitrary, PollArbitraryAdmin)


class AntiInterestAdmin(admin.ModelAdmin):
    list_display = ("user", "film", "poll_id")


admin.site.register(AntiInterest, AntiInterestAdmin)


class InterestAdmin(admin.ModelAdmin):
    list_display = ("user", "film", "score")


admin.site.register(Interest, InterestAdmin)


class EventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "added", "value")


admin.site.register(Event, EventAdmin)


class TelegramGroupAdmin(admin.ModelAdmin):
    list_display = ("id", "name")

admin.site.register(TelegramGroup, TelegramGroupAdmin)

class InPersonMovieSuggestionAdmin(admin.ModelAdmin):
    list_display = ("id", "theater_datetime", "theater_location")

admin.site.register(InPersonMovieSuggestion, InPersonMovieSuggestionAdmin)

class UserDataAdmin(admin.ModelAdmin):
    pass

admin.site.register(UserData, UserDataAdmin)


class CompanyInformationAdmin(admin.ModelAdmin):
    list_display = ("tmdb_id", "name", "country")

admin.site.register(CompanyInformation, CompanyInformationAdmin)

class ProductionCountryAdmin(admin.ModelAdmin):
    list_display = ("iso", "name")

admin.site.register(ProductionCountry, ProductionCountryAdmin)
