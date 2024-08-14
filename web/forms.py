from django.forms import ModelForm
from django import forms
from .models import *

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

class InPersonMovieSuggestionForm(ModelForm):
    class Meta:
        model = InPersonMovieSuggestion
        fields = [
            'imdb_id',
            'theater_datetime',
            'theater_location',
            'showing_type',
        ]

        labels = {
            "imdb_id": "IMDb URL",
            "showing_type": "Showing Type",
            "theater_datetime": "Showing Time",
            "theater_location": "Location",
        }

        widgets = {
            'theater_datetime':forms.TextInput(attrs={'type':'datetime-local'}),
        }

    theater_location = forms.ChoiceField(
        widget=forms.RadioSelect,
        choices=THEATERS.items(),
    )
    showing_type = forms.ChoiceField(
        widget=forms.RadioSelect,
        choices=SHOWING_TYPES.items(),
    )
