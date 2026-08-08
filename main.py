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
# BINGED OTT TRACKER
# ============================================================

BINGED_BASE = "https://www.binged.com/streaming-premiere-dates/"

BINGED_URL = (
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

IST = ZoneInfo("Asia/Kolkata")

# GitHub runs approximately every 5 minutes.
# A command is considered recent for 7 minutes.
COMMAND_MAX_AGE = 7 * 60


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


# ============================================================
# LANGUAGES
# ============================================================

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


# ============================================================
# GENRES
# ============================================================

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
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def normal_key(value):
    return re.sub(
        r"[^a-z0-9]+",
        "",
        str(value).lower()
    )


def parse_date(value):
    if not value:
        return None

    match = re.search(
        r"\b"
        r"\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}"
        r"\b",
        value,
        re.IGNORECASE
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

    for rating in sorted(
        RATINGS,
        key=len,
        reverse=True
    ):

        if re.search(
            rf"\b{re.escape(rating)}\b",
            text,
            re.IGNORECASE
        ):
            return rating

    return "Not listed"


def find_date(text):

    match = re.search(
        r"\b"
        r"\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}"
        r"\b",
        text,
        re.IGNORECASE
    )

    return match.group(0) if match else "Not listed"


def find_type(text):

    if re.search(
        r"\bTV\s*Show\b",
        text,
        re.IGNORECASE
    ):
        return "TV Show"

    if re.search(
        r"\bFilm\b",
        text,
        re.IGNORECASE
    ):
        return "Film"

    if re.search(
        r"\bTv\s+show\b",
        text,
        re.IGNORECASE
    ):
        return "TV Show"

    return "Not listed"


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

    values = []

    values.append(str(element))

    values.append(
        element.get_text(
            " ",
            strip=True
        )
    )

    attributes = [
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
        "data-network",
    ]

    for tag in element.find_all(True):

        for attribute in attributes:

            value = tag.get(
                attribute
            )

            if isinstance(
                value,
                list
            ):
                value = " ".join(
                    str(x)
                    for x in value
                )

            if value:
                values.append(
                    str(value)
                )

    for value in values:

        platform = find_platform(
            value
        )

        if platform:
            return platform

    return "Not listed"


# ============================================================
# TITLE
# ============================================================

def clean_title(title):

    title = clean_text(title)

    if not title:
        return ""

    for rating in sorted(
        RATINGS,
        key=len,
        reverse=True
    ):

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


# ============================================================
# FIND TITLE LINKS
# ============================================================

def is_content_link(href):

    if not href:
        return False

    href_lower = href.lower()

    if "binged.com" not in href_lower:
        return False

    return any(
        path in href_lower
        for path in [
            "/movie/",
            "/tv-show/",
            "/web-series/",
            "/streaming-premiere-dates/",
        ]
    )


def is_navigation_title(title):

    return title.lower() in {
        "view all",
        "read more",
        "streaming dates",
        "filters",
        "clear",
        "home",
        "reviews",
        "news",
        "ranked lists",
        "next",
        "previous",
        "previous page",
        "next page",
    }


# ============================================================
# FIND BEST CONTAINER
# ============================================================

def find_best_container(anchor):

    current = anchor

    best = None

    # Search substantially farther than the old
    # five-parent limit.
    for _ in range(12):

        if not current:
            break

        text = clean_text(
            current.get_text(
                " ",
                strip=True
            )
        )

        has_date = bool(
            re.search(
                r"\b\d{1,2}\s+"
                r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                r"\s+\d{4}\b",
                text,
                re.IGNORECASE
            )
        )

        has_rating = bool(
            re.search(
                r"\b(?:Must Watch|Good|Satisfactory|Passable|Poor|Skip)\b",
                text,
                re.IGNORECASE
            )
        )

        if has_date and has_rating:

            if 20 <= len(text) <= 4000:
                best = current
                break

        current = current.parent

    return best or anchor.parent or anchor


# ============================================================
# PARSE BINGED PAGE
# ============================================================

def parse_cards(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    cards = []
    used = set()

    # --------------------------------------------------------
    # Method 1:
    # Find actual Binged content links.
    # --------------------------------------------------------

    for anchor in soup.find_all(
        "a",
        href=True
    ):

        href = anchor.get(
            "href",
            ""
        )

        if not is_content_link(href):
            continue

        raw_title = clean_text(
            anchor.get_text(
                " ",
                strip=True
            )
        )

        title = clean_title(
            raw_title
        )

        if not title:
            continue

        if len(title) < 2:
            continue

        if len(title) > 150:
            continue

        if is_navigation_title(title):
            continue

        if title.lower() in {
            x.lower()
            for x in RATINGS
        }:
            continue

        key = normal_key(title)

        if not key:
            continue

        if key in used:
            continue

        # ----------------------------------------------------
        # Find surrounding card.
        # ----------------------------------------------------

        container = find_best_container(
            anchor
        )

        text = clean_text(
            container.get_text(
                " ",
                strip=True
            )
        )

        # ----------------------------------------------------
        # Rating
        # ----------------------------------------------------

        rating = find_rating(text)

        if rating == "Not listed":

            rating = find_rating(
                str(container)
            )

        if rating == "Not listed":
            continue

        # ----------------------------------------------------
        # Date
        # ----------------------------------------------------

        release_date = find_date(text)

        if release_date == "Not listed":

            release_date = find_date(
                str(container)
            )

        if release_date == "Not listed":
            continue

        # ----------------------------------------------------
        # Create card
        # ----------------------------------------------------

        card = {
            "title": title,

            "rating": rating,

            "date": release_date,

            "date_object": parse_date(
                release_date
            ),

            "type": find_type(
                text
            ),

            "genre": find_genres(
                text
            ),

            "language": find_languages(
                text
            ),

            "platform": extract_platform(
                container
            ),

            "binged_link": urljoin(
                BINGED_BASE,
                href
            ),
        }

        cards.append(
            card
        )

        used.add(
            key
        )

    # --------------------------------------------------------
    # Method 2:
    # Fallback: article/list cards.
    #
    # This catches layouts where the title link itself
    # is not a direct content URL.
    # --------------------------------------------------------

    if not cards:

        for element in soup.find_all(
            [
                "article",
                "li",
                "tr",
                "div",
            ]
        ):

            text = clean_text(
                element.get_text(
                    " ",
                    strip=True
                )
            )

            if len(text) < 30:
                continue

            if len(text) > 4000:
                continue

            rating = find_rating(text)

            if rating == "Not listed":
                continue

            release_date = find_date(text)

            if release_date == "Not listed":
                continue

            title = None
            href = None

            for anchor in element.find_all(
                "a",
                href=True
            ):

                candidate = clean_title(
                    clean_text(
                        anchor.get_text(
                            " ",
                            strip=True
                        )
                    )
                )

                candidate_href = anchor.get(
                    "href"
                )

                if not candidate:
                    continue

                if is_navigation_title(
                    candidate
                ):
                    continue

                if (
                    2 <= len(candidate) <= 150
                    and is_content_link(
                        candidate_href
                    )
                ):

                    title = candidate
                    href = candidate_href
                    break

            if not title:
                continue

            key = normal_key(title)

            if not key or key in used:
                continue

            cards.append({
                "title": title,
                "rating": rating,
                "date": release_date,
                "date_object": parse_date(
                    release_date
                ),
                "type": find_type(text),
                "genre": find_genres(text),
                "language": find_languages(text),
                "platform": extract_platform(element),
                "binged_link": urljoin(
                    BINGED_BASE,
                    href
                ),
            })

            used.add(key)

    # --------------------------------------------------------
    # Sort newest first.
    # --------------------------------------------------------

    cards.sort(
        key=lambda card: (
            card["date_object"]
            or datetime.min
        ),
        reverse=True
    )

    print(
        f"Extracted {len(cards)} title(s)"
    )

    return cards


# ============================================================
# SCRAPERAPI
# ============================================================

def fetch_binged():

    if not SCRAPER_API_KEY:

        raise RuntimeError(
            "SCRAPER_API_KEY secret is missing."
        )

    attempts = [

        # First attempt: normal request.
        {
            "name": "normal",
            "params": {
                "api_key": SCRAPER_API_KEY,
                "url": BINGED_URL,
                "device_type": "desktop",
            },
        },

        # Second: JS rendering.
        {
            "name": "render",
            "params": {
                "api_key": SCRAPER_API_KEY,
                "url": BINGED_URL,
                "render": "true",
                "device_type": "desktop",
            },
        },

        # Third: premium + rendering.
        {
            "name": "premium-render",
            "params": {
                "api_key": SCRAPER_API_KEY,
                "url": BINGED_URL,
                "render": "true",
                "premium": "true",
                "device_type": "desktop",
            },
        },
    ]

    last_error = (
        "Could not fetch Binged."
    )

    for attempt in attempts:

        print(
            f"Trying ScraperAPI: "
            f"{attempt['name']}"
        )

        try:

            response = requests.get(
                "https://api.scraperapi.com/",
                params=attempt["params"],
                timeout=120
            )

            print(
                "ScraperAPI HTTP status: "
                f"{response.status_code}"
            )

            print(
                "Returned content length: "
                f"{len(response.text)}"
            )

            if response.status_code != 200:

                last_error = (
                    "ScraperAPI returned HTTP "
                    f"{response.status_code}"
                )

                continue

            html = response.text

            lower = html[:50000].lower()

            blocked_phrases = [
                "access denied",
                "<title>forbidden</title>",
                "verify you are human",
                "checking your browser",
                "just a moment",
                "cf-chl",
            ]

            if any(
                phrase in lower
                for phrase in blocked_phrases
            ):

                print(
                    "Binged returned a "
                    "block/verification page."
                )

                last_error = (
                    "Binged returned a "
                    "verification/block page."
                )

                continue

            print(
                "Binged page fetched successfully."
            )

            return html

        except Exception as exc:

            print(
                f"ScraperAPI request failed: "
                f"{exc}"
            )

            last_error = str(exc)

        time.sleep(2)

    raise RuntimeError(
        last_error
    )


# ============================================================
# FETCH CARDS
# ============================================================

def fetch_cards():

    print(
        "Fetching combined Binged filtered page..."
    )

    print(
        BINGED_URL
    )

    html = fetch_binged()

    cards = parse_cards(
        html
    )

    if not cards:

        raise RuntimeError(
            "Binged page was fetched successfully "
            "but no titles could be extracted."
        )

    return cards


# ============================================================
# STREMIO
# ============================================================

def stremio_link(title):

    return (
        "https://web.stremio.com/"
        "#/search?search="
        + quote(
            title,
            safe=""
        )
    )


# ============================================================
# TELEGRAM KEYBOARD
# ============================================================

def make_keyboard(card):

    return {
        "inline_keyboard": [

            [
                {
                    "text": "▶ Open Stremio",
                    "url": stremio_link(
                        card["title"]
                    ),
                }
            ],

            [
                {
                    "text": "🔗 Open on Binged",
                    "url": card[
                        "binged_link"
                    ],
                }
            ],

        ]
    }


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def make_message(card):

    return (
        f"🎬 {card['title']}\n"
        f"⭐ Rating: {card['rating']}\n"
        f"📅 Release: {card['date']}\n"
        f"🎞 Type: {card['type']}\n"
        f"🎭 Genre: {card['genre']}\n"
        f"🗣 Language: {card['language']}\n"
        f"📺 Platform: {card['platform']}"
    )


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_request(
    method,
    params=None
):

    if not TELEGRAM_BOT_TOKEN:

        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN secret is missing."
        )

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/"
        f"{method}"
    )

    response = requests.get(
        url,
        params=params or {},
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):

        raise RuntimeError(
            f"Telegram API error: {data}"
        )

    return data


def send_telegram(
    chat_id,
    text,
    keyboard=None
):

    params = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }

    if keyboard:

        params["reply_markup"] = json.dumps(
            keyboard
        )

    telegram_request(
        "sendMessage",
        params
    )


# ============================================================
# TELEGRAM COMMAND MENU
# ============================================================

def register_commands():

    commands = [

        {
            "command": "start",
            "description": "Start Binged OTT Tracker",
        },

        {
            "command": "help",
            "description": "Show all available commands",
        },

        {
            "command": "latest",
            "description": "Latest filtered OTT releases",
        },

        {
            "command": "today",
            "description": "Today's OTT releases",
        },

        {
            "command": "movies",
            "description": "Latest Hindi Punjabi movies",
        },

        {
            "command": "shows",
            "description": "Latest Hindi Punjabi TV shows",
        },

        {
            "command": "hindi",
            "description": "Latest Hindi releases",
        },

        {
            "command": "punjabi",
            "description": "Latest Punjabi releases",
        },

        {
            "command": "mustwatch",
            "description": "Must Watch releases",
        },

        {
            "command": "good",
            "description": "Good rated releases",
        },

        {
            "command": "satisfactory",
            "description": "Satisfactory releases",
        },

        {
            "command": "passable",
            "description": "Passable releases",
        },

        {
            "command": "poor",
            "description": "Poor rated releases",
        },

        {
            "command": "skip",
            "description": "Skip rated releases",
        },

        {
            "command": "all",
            "description": "All filtered releases",
        },

        {
            "command": "refresh",
            "description": "Check Binged for new releases",
        },

        {
            "command": "status",
            "description": "Show tracker status",
        },

        {
            "command": "filters",
            "description": "Show active Binged filters",
        },
    ]

    telegram_request(
        "setMyCommands",
        {
            "commands": json.dumps(
                commands
            )
        }
    )

    print(
        "Telegram command menu registered."
    )


# ============================================================
# SEEN TITLES
# ============================================================

def load_seen():

    if not os.path.exists(
        SEEN_FILE
    ):
        return set()

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

        if isinstance(
            data,
            list
        ):

            return set(
                str(x)
                for x in data
            )

    except Exception as exc:

        print(
            f"Could not read seen file: "
            f"{exc}"
        )

    return set()


def save_seen(seen):

    with open(
        SEEN_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            sorted(seen),
            file,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# TELEGRAM COMMAND READER
# ============================================================

def get_command():

    # Make sure Telegram is using polling.
    telegram_request(
        "deleteWebhook",
        {
            "drop_pending_updates": "false"
        }
    )

    result = telegram_request(
        "getUpdates",
        {
            "limit": 50,
            "timeout": 0,
            "allowed_updates": json.dumps(
                ["message"]
            ),
        }
    )

    updates = result.get(
        "result",
        []
    )

    if not updates:
        return None

    now = int(
        time.time()
    )

    latest_command = None

    for update in updates:

        message = update.get(
            "message"
        )

        if not message:
            continue

        text = clean_text(
            message.get(
                "text",
                ""
            )
        )

        if not text:
            continue

        command = text.lower()

        command = command.split(
            "@",
            1
        )[0]

        if command not in COMMANDS:
            continue

        message_date = int(
            message.get(
                "date",
                0
            )
        )

        age = now - message_date

        if 0 <= age <= COMMAND_MAX_AGE:

            latest_command = message

    return latest_command


# ============================================================
# FILTERING
# ============================================================

def filter_cards(
    cards,
    mode
):

    if mode == "mustwatch":

        return [
            card for card in cards
            if card["rating"].lower()
            == "must watch"
        ]

    if mode == "good":

        return [
            card for card in cards
            if card["rating"].lower()
            == "good"
        ]

    if mode == "satisfactory":

        return [
            card for card in cards
            if card["rating"].lower()
            == "satisfactory"
        ]

    if mode == "passable":

        return [
            card for card in cards
            if card["rating"].lower()
            == "passable"
        ]

    if mode == "poor":

        return [
            card for card in cards
            if card["rating"].lower()
            == "poor"
        ]

    if mode == "skip":

        return [
            card for card in cards
            if card["rating"].lower()
            == "skip"
        ]

    if mode == "movies":

        return [
            card for card in cards
            if card["type"].lower()
            == "film"
        ]

    if mode == "shows":

        return [
            card for card in cards
            if card["type"].lower()
            == "tv show"
        ]

    if mode == "hindi":

        return [
            card for card in cards
            if re.search(
                r"\bHindi\b",
                card["language"],
                re.IGNORECASE
            )
        ]

    if mode == "punjabi":

        return [
            card for card in cards
            if re.search(
                r"\bPunjabi\b",
                card["language"],
                re.IGNORECASE
            )
        ]

    if mode == "today":

        today = datetime.now(
            IST
        ).date()

        return [
            card for card in cards
            if (
                card["date_object"]
                and card["date_object"].date()
                == today
            )
        ]

    return cards


# ============================================================
# SEND CARDS
# ============================================================

def send_cards(
    chat_id,
    cards,
    heading
):

    send_telegram(
        chat_id,
        heading
    )

    if not cards:

        send_telegram(
            chat_id,
            "No matching titles found."
        )

        return

    for card in cards:

        send_telegram(
            chat_id,
            make_message(card),
            make_keyboard(card)
        )

        time.sleep(
            0.1
        )

    send_telegram(
        chat_id,
        f"✅ {len(cards)} title(s) found."
    )


# ============================================================
# HELP
# ============================================================

def help_text():

    return (
        "📋 Available commands:\n\n"

        "/start - Start Binged OTT Tracker\n"
        "/help - Show all available commands\n"
        "/latest - Latest filtered OTT releases\n"
        "/today - Today's OTT releases\n"
        "/movies - Latest Hindi Punjabi movies\n"
        "/shows - Latest Hindi Punjabi TV shows\n"
        "/hindi - Latest Hindi releases\n"
        "/punjabi - Latest Punjabi releases\n"
        "/mustwatch - Must Watch releases\n"
        "/good - Good rated releases\n"
        "/satisfactory - Satisfactory releases\n"
        "/passable - Passable releases\n"
        "/poor - Poor rated releases\n"
        "/skip - Skip rated releases\n"
        "/all - All filtered releases\n"
        "/refresh - Check Binged for new releases\n"
        "/status - Show tracker status\n"
        "/filters - Show active Binged filters"
    )


# ============================================================
# FILTERS
# ============================================================

def filters_text():

    return (
        "🔎 Active Binged filters:\n\n"
        "Category: Film + TV Show\n"
        "Language: Hindi + Punjabi\n"
        "Mode: Streaming Now\n"
        "Ratings: Must Watch, Good, Satisfactory, "
        "Passable, Poor, Skip"
    )


# ============================================================
# HANDLE COMMAND
# ============================================================

def handle_command(
    message,
    command
):

    chat_id = message[
        "chat"
    ][
        "id"
    ]

    mode = COMMANDS.get(
        command
    )

    print(
        f"Telegram command received: "
        f"{command}"
    )

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    if mode == "start":

        send_telegram(
            chat_id,
            "🎬 Binged OTT Tracker is active.\n\n"
            + help_text()
        )

        return

    # --------------------------------------------------------
    # HELP
    # --------------------------------------------------------

    if mode == "help":

        send_telegram(
            chat_id,
            help_text()
        )

        return

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------

    if mode == "filters":

        send_telegram(
            chat_id,
            filters_text()
        )

        return

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if mode == "status":

        seen = load_seen()

        send_telegram(
            chat_id,
            "📊 Tracker status\n\n"
            f"Seen titles: {len(seen)}\n"
            "Schedule: Every 5 minutes\n"
            "Binged source: Active\n"
            f"Checked: "
            f"{datetime.now(IST).strftime('%d %b %Y, %I:%M %p')} IST"
        )

        return

    # --------------------------------------------------------
    # BINGED FETCH
    # --------------------------------------------------------

    send_telegram(
        chat_id,
        "🔄 Fetching Binged releases..."
    )

    try:

        cards = fetch_cards()

    except Exception as exc:

        print(
            f"Binged fetch error: {exc}"
        )

        send_telegram(
            chat_id,
            "❌ Could not fetch Binged right now.\n\n"
            f"{exc}"
        )

        return

    # --------------------------------------------------------
    # REFRESH
    # --------------------------------------------------------

    if mode == "refresh":

        seen = load_seen()

        new_cards = []

        for card in cards:

            key = normal_key(
                card["title"]
            )

            if key not in seen:

                new_cards.append(
                    card
                )

        if not new_cards:

            send_telegram(
                chat_id,
                "✅ Binged checked.\n"
                "No new releases found."
            )

            return

        for card in new_cards:

            send_telegram(
                chat_id,
                make_message(card),
                make_keyboard(card)
            )

            time.sleep(
                0.1
            )

        send_telegram(
            chat_id,
            f"✅ {len(new_cards)} new title(s) found."
        )

        return

    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    result = filter_cards(
        cards,
        mode
    )

    headings = {

        "latest":
            "🎬 LATEST — FILTERED BINGED RESULTS",

        "today":
            "📅 TODAY'S OTT RELEASES",

        "movies":
            "🎬 LATEST HINDI + PUNJABI MOVIES",

        "shows":
            "📺 LATEST HINDI + PUNJABI TV SHOWS",

        "hindi":
            "🗣 HINDI RELEASES",

        "punjabi":
            "🗣 PUNJABI RELEASES",

        "mustwatch":
            "⭐ MUST WATCH RELEASES",

        "good":
            "⭐ GOOD RELEASES",

        "satisfactory":
            "⭐ SATISFACTORY RELEASES",

        "passable":
            "⭐ PASSABLE RELEASES",

        "poor":
            "⭐ POOR RELEASES",

        "skip":
            "⭐ SKIP RELEASES",

        "all":
            "🎬 ALL FILTERED RELEASES",
    }

    heading = headings.get(
        mode,
        "🎬 BINGED RELEASES"
    )

    send_cards(
        chat_id,
        result,
        heading
    )


# ============================================================
# AUTOMATIC UPDATE
# ============================================================

def automatic_update():

    print(
        "Checking latest Binged page..."
    )

    try:

        cards = fetch_cards()

    except Exception as exc:

        print(
            f"Automatic update skipped: "
            f"{exc}"
        )

        return

    seen = load_seen()

    new_count = 0

    for card in cards:

        key = normal_key(
            card["title"]
        )

        if not key:
            continue

        if key in seen:
            continue

        print(
            f"New title: "
            f"{card['title']}"
        )

        try:

            send_telegram(
                TELEGRAM_CHAT_ID,
                make_message(card),
                make_keyboard(card)
            )

            seen.add(
                key
            )

            new_count += 1

            time.sleep(
                0.1
            )

        except Exception as exc:

            print(
                f"Telegram send failed: "
                f"{exc}"
            )

    save_seen(
        seen
    )

    print(
        f"New Telegram alerts: "
        f"{new_count}"
    )

    print(
        f"Total seen titles: "
        f"{len(seen)}"
    )


# ============================================================
# MAIN
# ============================================================

def run():

    print("")
    print(
        "========================================"
    )
    print(
        "BINGED → TELEGRAM"
    )
    print(
        "========================================"
    )

    if not SCRAPER_API_KEY:
        raise RuntimeError(
            "SCRAPER_API_KEY secret is missing."
        )

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN secret is missing."
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID secret is missing."
        )

    # --------------------------------------------------------
    # Register command menu.
    # --------------------------------------------------------

    try:

        register_commands()

    except Exception as exc:

        print(
            f"Command menu registration failed: "
            f"{exc}"
        )

    # --------------------------------------------------------
    # Check Telegram.
    # --------------------------------------------------------

    try:

        command_message = get_command()

    except Exception as exc:

        print(
            f"Telegram command check failed: "
            f"{exc}"
        )

        command_message = None

    # --------------------------------------------------------
    # Process command.
    # --------------------------------------------------------

    if command_message:

        raw_text = clean_text(
            command_message.get(
                "text",
                ""
            )
        ).lower()

        command = raw_text.split(
            "@",
            1
        )[0]

        handle_command(
            command_message,
            command
        )

        return

    # --------------------------------------------------------
    # No command.
    # Automatic check.
    # --------------------------------------------------------

    automatic_update()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    run()
