import json

import requests
from bs4 import BeautifulSoup
import tmdbsimple as tmdb

from movie.settings import TMDB_API_KEY

tmdb.API_KEY = TMDB_API_KEY
tmdb.REQUESTS_TIMEOUT = (2, 5)  # seconds, for connect and read specifically 

def get_ld_json(url: str) -> dict:
    parser = "html.parser"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:107.0) Gecko/20100101 Firefox/107.0"
    }
    req = requests.get(url, headers=headers)
    soup = BeautifulSoup(req.text, parser)
    return json.loads(
        "".join(soup.find("script", {"type": "application/ld+json"}).contents)
    )

def get_movie_poster_url_from_tmdb(movie) -> str | None:
    try:
        tmdb_results = tmdb.Find(movie.imdb_id).info(external_source="imdb_id")
        poster_path = tmdb_results["movie_results"][0]["poster_path"]        
        return f"https://image.tmdb.org/t/p/w500{poster_path}"
    except Exception as _:
        return None
