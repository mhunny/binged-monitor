import os
import re
import json
import time
import requests

from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
from datetime import datetime
from zoneinfo import ZoneInfo


# ============================================================
# CONFIG
# ============================================================

BINGED_BASE = "https://www.binged.com/streaming-premiere-dates/"

BINGED_LATEST_URL = (
    BINGED_BASE
    + "?category%5B%5D=Film"
    + "&category%5B%5D=Tv%20show"
    + "&language%5B%5D=Hindi"
    + "&language%5B%5D=Punjabi"
    + "&mode=streaming-now"
    + "&recommendation%5B%5D=Must_Watch"
    + "&recommendation%5B%5D=Good"
    + "&recommendation%5B%5D=Satisfactory"
    + "&recommendation%5B%5D=Passable"
    + "&recommendation%5B%5D=Poor"
    + "&recommendation%5B%5D=Skip"
)

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SEEN_FILE = "seen_titles.json"

MAX_CATEGORY_PAGES = 20
COMMAND_MAX_AGE_SECONDS = 15 * 60
IST = ZoneInfo("Asia/Kolkata")


# ============================================================
# RATINGS
# ============================================================

RATINGS = [
    "Must Watch",
    "Good",
    "Satisfactory",
    "Passable",
    "Poor",
    "Skip",
]

CATEGORY_VALUES = {
    "mustwatch": "Must_Watch",
    "good": "Good",
    "satisfactory": "Satisfactory",
    "passable": "Passable",
    "poor": "Poor",
    "skip": "Skip",
}


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

COMMANDS = {
    "/start": "start",
    "/help": "help",
    "/latest": "latest",
    "/today": "today",
    "/movies": "movies",
    "/shows": "shows",
    "/hindi": "hindi",
    "/punjabi": "punjabi",
    "/mustwatch": "mustwatch",
    "/good": "good",
    "/satisfactory": "satisfactory",
    "/passable": "passable",
    "/poor": "poor",
    "/skip": "skip",
    "/all": "all",
    "/refresh": "refresh",
    "/status": "status",
    "/filters": "filters",
}


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normal_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def parse_date(value):
    if not value:
        return None

    match = re.search(
        r"\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}\b",
        value,
        re.IGNORECASE,
    )

    if not match:
        return None

    try:
        return datetime.strptime(
            match.group(0),
            "%d %b %Y"
        )
    except ValueError:
        return None


# ============================================================
# FIELD EXTRACTION
# ============================================================

def find_rating(text):
    for rating in sorted(RATINGS, key=len, reverse=True):
        if re.search(
            rf"\b{re.escape(rating)}\b",
            text,
            re.IGNORECASE
        ):
            return rating

    return "Not listed"


def find_date(text):
    match = re.search(
        r"\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}\b",
        text,
        re.IGNORECASE,
    )

    return match.group(0) if match else "Not listed"


def find_type(text):
    if re.search(r"\bTV\s*Show\b", text, re.IGNORECASE):
        return "TV Show"

    if re.search(r"\bFilm\b", text, re.IGNORECASE):
        return "Film"

    return "Not listed"


LANGUAGES = [
    "Hindi",
    "Punjabi",
    "Telugu",
    "Tamil",
    "Malayalam",
    "Kannada",
    "Bengali",
    "Marathi",
    "Gujarati",
    "English",
    "Urdu",
]

GENRES = [
    "Action",
    "Adventure",
    "Animation",
    "Biography",
    "Comedy",
    "Crime",
    "Drama",
    "Family",
    "Fantasy",
    "Film-Noir",
    "Game-Show",
    "History",
    "Horror",
    "Kids",
    "Music",
    "Musical",
    "Mystery",
    "News",
    "Reality-TV",
    "Political",
    "Romance",
    "Sci-Fi",
    "Social",
    "Sports",
    "Talk-Show",
    "Thriller",
    "War",
    "Western",
]


def find_languages(text):
    found = []

    for language in LANGUAGES:
        if re.search(
            rf"\b{re.escape(language)}\b",
            text,
            re.IGNORECASE
        ):
            if language not in found:
                found.append(language)

    return ", ".join(found) if found else "Not listed"


def find_genres(text):
    found = []

    for genre in GENRES:
        if re.search(
            rf"\b{re.escape(genre)}\b",
            text,
            re.IGNORECASE
        ):
            if genre not in found:
                found.append(genre)

    return ", ".join(found) if found else "Not listed"


# ============================================================
# PLATFORM
# ============================================================

def find_platform(text):
    if not text:
        return None

    text = str(text).lower()

    platforms = [
        ("amazon prime video", "Prime Video"),
        ("prime video", "Prime Video"),
        ("jio hotstar", "Jio Hotstar"),
        ("jiohotstar", "Jio Hotstar"),
        ("disney plus hotstar", "Jio Hotstar"),
        ("disney hotstar", "Jio Hotstar"),
        ("hotstar", "Jio Hotstar"),
        ("sony liv", "Sony LIV"),
        ("sonyliv", "Sony LIV"),
        ("zee5", "ZEE5"),
        ("zee 5", "ZEE5"),
        ("mx player", "MX Player"),
        ("mxplayer", "MX Player"),
        ("apple tv plus", "Apple TV+"),
        ("apple tv", "Apple TV+"),
        ("jio cinema", "JioCinema"),
        ("jiocinema", "JioCinema"),
        ("sun nxt", "Sun NXT"),
        ("sunnxt", "Sun NXT"),
        ("lionsgate play", "Lionsgate Play"),
        ("discovery plus", "Discovery+"),
        ("airtel xstream", "Airtel Xstream"),
        ("manorama max", "Manorama MAX"),
        ("shemaroo me", "Shemaroo Me"),
        ("etv win", "ETV Win"),
        ("alt balaji", "ALT Balaji"),
        ("crunchyroll", "Crunchyroll"),
        ("simply south", "Simply South"),
        ("tentkotta", "Tentkotta"),
        ("chaupal", "Chaupal"),
        ("hoichoi", "Hoichoi"),
        ("mubi", "Mubi"),
        ("tubi", "Tubi"),
        ("viki", "Viki"),
        ("viu", "Viu"),
        ("voot", "Voot"),
        ("youtube", "YouTube"),
        ("aha video", "aha"),
        ("aha", "aha"),
    ]

    platforms.sort(
        key=lambda x: len(x[0]),
        reverse=True
    )

    for alias, name in platforms:
        if alias in text:
            return name

    return None


def extract_platform(element):
    if not element:
        return "Not listed"

    values = [str(element)]

    values.append(
        element.get_text(" ", strip=True)
    )

    for tag in element.find_all(True):
        for attr in [
            "alt",
            "title",
            "aria-label",
            "class",
            "id",
            "src",
            "href",
            "data-platform",
            "data-provider",
            "data-service",
        ]:
            value = tag.get(attr)

            if isinstance(value, list):
                value = " ".join(str(x) for x in value)

            if value:
                values.append(str(value))

    for value in values:
        result = find_platform(value)

        if result:
            return result

    return "Not listed"


# ============================================================
# TITLE
# ============================================================

def clean_title(title):
    title = clean_text(title)

    for rating in sorted(RATINGS, key=len, reverse=True):
        title = re.sub(
            rf"\s+{re.escape(rating)}$",
            "",
            title,
            flags=re.IGNORECASE
        )

    title = re.sub(
        r"\s+(?:Film|TV\s*Show)$",
        "",
        title,
        flags=re.IGNORECASE
    )

    return clean_text(title)


def find_title_link(element):
    candidates = []

    for anchor in element.find_all("a", href=True):

        raw = clean_text(
            anchor.get_text(" ", strip=True)
        )

        href = anchor.get("href")

        if not raw or not href:
            continue

        title = clean_title(raw)

        if len(title) < 2 or len(title) > 150:
            continue

        if title.lower() in [
            "view all",
            "read more",
            "streaming dates",
            "filters",
            "clear",
            "home",
            "reviews",
            "news",
            "ranked lists",
        ]:
            continue

        if title.lower() in [
            x.lower() for x in RATINGS
        ]:
            continue

        candidates.append((title, href))

    if not candidates:
        return None, None

    for title, href in candidates:

        href_lower = href.lower()

        if (
            "binged.com" in href_lower
            and (
                "/streaming-premiere-dates/" in href_lower
                or "/movie/" in href_lower
                or "/tv-show/" in href_lower
                or "/web-series/" in href_lower
            )
        ):
            return title, href

    return candidates[0]


# ============================================================
# PARSE BINGED
# ============================================================

def parse_cards(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    date_pattern = re.compile(
        r"\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}\b",
        re.IGNORECASE
    )

    rating_pattern = re.compile(
        r"\b(?:Must Watch|Good|Satisfactory|Passable|Poor|Skip)\b",
        re.IGNORECASE
    )

    candidates = []

    for element in soup.find_all(
        ["article", "li", "tr", "div"]
    ):

        text = clean_text(
            element.get_text(" ", strip=True)
        )

        if len(text) < 30 or len(text) > 2500:
            continue

        if not date_pattern.search(text):
            continue

        if not rating_pattern.search(text):
            continue

        candidates.append(
            (element, text)
        )

    candidates.sort(
        key=lambda x: len(x[1])
    )

    cards = []
    used = set()

    for element, text in candidates:

        rating = find_rating(text)
        release_date = find_date(text)

        if (
            rating == "Not listed"
            or release_date == "Not listed"
        ):
            continue

        title, link = find_title_link(element)

        if not title:
            continue

        key = normal_key(title)

        if not key or key in used:
            continue

        cards.append({
            "title": title,
            "rating": rating,
            "date": release_date,
            "date_object": parse_date(release_date),
            "type": find_type(text),
            "genre": find_genres(text),
            "language": find_languages(text),
            "platform": extract_platform(element),
            "binged_link": (
                urljoin(BINGED_BASE, link)
                if link
                else BINGED_BASE
            ),
        })

        used.add(key)

    return cards


# ============================================================
# NEXT PAGE DETECTION
# ============================================================

def find_next_page(html, current_url):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # First: look for rel="next"
    for anchor in soup.find_all(
        "a",
        href=True
    ):

        rel = anchor.get("rel")

        if rel:

            if isinstance(rel, list):
                rel_text = " ".join(rel).lower()
            else:
                rel_text = str(rel).lower()

            if "next" in rel_text:

                next_url = urljoin(
                    current_url,
                    anchor["href"]
                )

                if next_url != current_url:
                    return next_url

    # Second: look for a visible Next button/link
    for anchor in soup.find_all(
        "a",
        href=True
    ):

        text = clean_text(
            anchor.get_text(
                " ",
                strip=True
            )
        ).lower()

        aria = clean_text(
            anchor.get(
                "aria-label",
                ""
            )
        ).lower()

        title = clean_text(
            anchor.get(
                "title",
                ""
            )
        ).lower()

        classes = " ".join(
            anchor.get(
                "class",
                []
            )
        ).lower()

        if (
            text in [
                "next",
                "next page",
                "older",
                "older posts",
                "›",
                "»",
                "→",
            ]
            or "next page" in aria
            or "next page" in title
            or "next" in classes
        ):

            next_url = urljoin(
                current_url,
                anchor["href"]
            )

            if next_url != current_url:
                return next_url

    return None


# ============================================================
# SCRAPERAPI FETCH
# ============================================================
