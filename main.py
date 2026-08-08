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
# CONFIGURATION
# ============================================================

BINGED_BASE = "https://www.binged.com/streaming-premiere-dates/"

BINGED_FILTERED_URL = (
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
OFFSET_FILE = "telegram_offset.json"

IST = ZoneInfo("Asia/Kolkata")

# Maximum releases processed from one listing page.
MAX_TITLES = 20

# Detail pages are fetched one by one.
DETAIL_DELAY = 0.3

# A Telegram command older than this is ignored.
COMMAND_MAX_AGE = 15 * 60


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
    "Assamese",
    "Bhojpuri",
    "Konkani",
    "Odia",
    "Rajasthani",
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
    "Documentary",
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
# PLATFORMS
# ============================================================

PLATFORMS = [
    ("amazon prime video", "Prime Video"),
    ("prime video", "Prime Video"),
    ("amazon", "Prime Video"),

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
    ("apple tv+", "Apple TV+"),
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
    ("netflix", "Netflix"),
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
    if value is None:
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

    value = clean_text(value)

    patterns = [
        "%d %b %Y",
        "%d %B %Y",
    ]

    match = re.search(
        r"\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}\b",
        value,
        re.IGNORECASE,
    )

    if not match:
        return None

    for fmt in patterns:
        try:
            return datetime.strptime(
                match.group(0),
                fmt
            )
        except ValueError:
            pass

    return None


def format_date(value):
    parsed = parse_date(value)

    if not parsed:
        return "Not listed"

    return parsed.strftime("%d %b %Y")


# ============================================================
# FIELD EXTRACTION
# ============================================================

def find_rating(text):
    text = clean_text(text)

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
    text = clean_text(text)

    match = re.search(
        r"\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}\b",
        text,
        re.IGNORECASE
    )

    if match:
        return format_date(
            match.group(0)
        )

    return "Not listed"


def find_type(text):
    text = clean_text(text)

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

    return "Not listed"


def find_genres(text):
    text = clean_text(text)

    found = []

    for genre in GENRES:
        if re.search(
            rf"(?<![A-Za-z]){re.escape(genre)}(?![A-Za-z])",
            text,
            re.IGNORECASE
        ):
            if genre not in found:
                found.append(genre)

    return ", ".join(found) if found else "Not listed"


def find_languages(text):
    text = clean_text(text)

    found = []

    for language in LANGUAGES:
        if re.search(
            rf"(?<![A-Za-z]){re.escape(language)}(?![A-Za-z])",
            text,
            re.IGNORECASE
        ):
            if language not in found:
                found.append(language)

    return ", ".join(found) if found else "Not listed"


def find_platform(text):
    if not text:
        return None

    normalized = clean_text(text).lower()

    normalized = normalized.replace(
        "jiohotstar",
        "jio hotstar"
    )

    for alias, display_name in sorted(
        PLATFORMS,
        key=lambda x: len(x[0]),
        reverse=True
    ):
        if alias in normalized:
            return display_name

    return None


# ============================================================
# PLATFORM FROM DETAIL PAGE
# ============================================================

def extract_detail_platform(soup):
    values = []

    # Image/logo attributes are usually the cleanest source.
    for tag in soup.find_all(
        ["img", "a", "button"]
    ):
        for attr in [
            "alt",
            "title",
            "aria-label",
            "data-platform",
            "data-provider",
            "data-service",
        ]:
            value = tag.get(attr)

            if isinstance(value, list):
                value = " ".join(
                    str(x)
                    for x in value
                )

            if value:
                values.append(
                    str(value)
                )

    # Search visible page text, but only the beginning.
    body_text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    values.append(
        body_text[:6000]
    )

    for value in values:
        platform = find_platform(value)

        if platform:
            return platform

    return "Not listed"


# ============================================================
# SCRAPERAPI
# ============================================================

def scraperapi_fetch(
    target_url,
    render=False
):

    if not SCRAPER_API_KEY:
        raise RuntimeError(
            "SCRAPER_API_KEY secret is missing."
        )

    params = {
        "api_key": SCRAPER_API_KEY,
        "url": target_url,
    }

    if render:
        params["render"] = "true"

    response = requests.get(
        "https://api.scraperapi.com/",
        params=params,
        timeout=180
    )

    print(
        f"ScraperAPI HTTP status: "
        f"{response.status_code}"
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"ScraperAPI returned HTTP "
            f"{response.status_code}"
        )

    if not response.text:
        raise RuntimeError(
            "ScraperAPI returned empty content."
        )

    return response.text


def fetch_binged_listing():
    print(
        "Fetching combined Binged filtered page..."
    )

    print(
        BINGED_FILTERED_URL
    )

    # First try normal ScraperAPI request.
    try:
        print("Trying ScraperAPI: normal")

        html = scraperapi_fetch(
            BINGED_FILTERED_URL,
            render=False
        )

        print(
            f"Returned content length: "
            f"{len(html)}"
        )

        if len(html) > 10000:
            print(
                "Binged page fetched successfully."
            )
            return html

    except Exception as exc:
        print(
            f"Normal request failed: {exc}"
        )

    # If normal request fails, try rendered request.
    try:
        print("Trying ScraperAPI: rendered")

        html = scraperapi_fetch(
            BINGED_FILTERED_URL,
            render=True
        )

        print(
            f"Returned content length: "
            f"{len(html)}"
        )

        if len(html) > 10000:
            print(
                "Binged page fetched successfully."
            )
            return html

    except Exception as exc:
        print(
            f"Rendered request failed: {exc}"
        )

    raise RuntimeError(
        "Could not fetch Binged right now."
    )

# ============================================================
# FIND ACTUAL BINGED TITLE LINKS
# ============================================================

def is_content_link(href):
    if not href:
        return False

    href_lower = href.lower()

    if "binged.com" not in href_lower:
        return False

    # Current Binged title pages use the streaming-premiere-
    # dates path followed by the title slug.
    if "/streaming-premiere-dates/" not in href_lower:
        return False

    # Do not accept the listing page itself.
    path = href_lower.split("?", 1)[0].rstrip("/")

    if path.endswith(
        "/streaming-premiere-dates"
    ):
        return False

    return True


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

    title = re.sub(
        r"\s+\d{4}$",
        "",
        title
    )

    return clean_text(title)


def find_listing_titles(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    cards = []
    used = set()

    for anchor in soup.find_all(
        "a",
        href=True
    ):

        href = anchor.get(
            "href"
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

        if len(title) < 2 or len(title) > 150:
            continue

        lower = title.lower()

        excluded = {
            "streaming dates",
            "streaming now",
            "streaming soon",
            "view all",
            "read more",
            "contact",
            "about us",
            "privacy policy",
            "terms of use",
            "skip ad",
        }

        if lower in excluded:
            continue

        key = normal_key(title)

        if not key or key in used:
            continue

        # ----------------------------------------------------
        # Get nearby listing text for release date.
        # ----------------------------------------------------

        listing_text = ""

        container = anchor

        for _ in range(7):

            if not container:
                break

            candidate = clean_text(
                container.get_text(
                    " ",
                    strip=True
                )
            )

            if 20 <= len(candidate) <= 3000:

                listing_text = candidate

                if (
                    re.search(
                        r"\b\d{1,2}\s+"
                        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                        r"\s+\d{4}\b",
                        candidate,
                        re.IGNORECASE
                    )
                ):
                    break

            container = container.parent

        cards.append({
            "title": title,
            "binged_link": urljoin(
                BINGED_BASE,
                href
            ),
            "listing_text": listing_text,
            "release": find_date(
                listing_text
            ),
        })

        used.add(key)

        if len(cards) >= MAX_TITLES:
            break

    print(
        f"Found {len(cards)} Binged title link(s)."
    )

    return cards


# ============================================================
# DETAIL PAGE PARSER
# ============================================================

def parse_detail_page(
    html,
    card
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    full_text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = card["title"]

    h1 = soup.find("h1")

    if h1:
        h1_title = clean_title(
            h1.get_text(
                " ",
                strip=True
            )
        )

        if h1_title:
            title = h1_title

    # --------------------------------------------------------
    # RATING
    # --------------------------------------------------------

    rating = find_rating(
        full_text
    )

    # Prefer explicit "Binged Rating".
    rating_match = re.search(
        r"Binged\s+Rating\s+"
        r"(Must\s+Watch|Good|Satisfactory|Passable|Poor|Skip)",
        full_text,
        re.IGNORECASE
    )

    if rating_match:
        rating = clean_text(
            rating_match.group(1)
        )

        if rating.lower() == "must watch":
            rating = "Must Watch"

    # --------------------------------------------------------
    # TYPE
    # --------------------------------------------------------

    content_type = find_type(
        full_text
    )

    # --------------------------------------------------------
    # RELEASE
    # --------------------------------------------------------

    release = card.get(
        "release",
        "Not listed"
    )

    # The listing date is preferred because that is the exact
    # OTT release date shown by the filtered streaming page.
    if release == "Not listed":
        release = find_date(
            full_text
        )

    # --------------------------------------------------------
    # GENRE + LANGUAGE
    # --------------------------------------------------------

    # The information before "Binged Rating" normally contains
    # the title metadata: genre and language.
    rating_position = full_text.lower().find(
        "binged rating"
    )

    if rating_position >= 0:
        metadata_text = full_text[
            max(0, rating_position - 1500):
            rating_position
        ]
    else:
        metadata_text = full_text[:3000]

    genre = find_genres(
        metadata_text
    )

    language = find_languages(
        metadata_text
    )

    # --------------------------------------------------------
    # PLATFORM
    # --------------------------------------------------------

    platform = extract_detail_platform(
        soup
    )

    # If no platform was found from logo/attributes, search
    # for platform names in the page text before the cast/plot.
    if platform == "Not listed":

        platform = find_platform(
            full_text[:5000]
        )

    return {
        "title": title,
        "rating": rating,
        "release": release,
        "type": content_type,
        "genre": genre,
        "language": language,
        "platform": platform,
        "binged_link": card[
            "binged_link"
        ],
    }


# ============================================================
# FETCH ONE TITLE'S DETAILS
# ============================================================

def enrich_card(card):

    print(
        f"Fetching details: "
        f"{card['title']}"
    )

    # First try without JS rendering.
    # This is faster and cheaper.
    try:

        html = scraperapi_fetch(
            card["binged_link"],
            render=False
        )

        result = parse_detail_page(
            html,
            card
        )

        # If useful fields were found, use them.
        useful = (
            result["rating"] != "Not listed"
            or result["genre"] != "Not listed"
            or result["language"] != "Not listed"
            or result["platform"] != "Not listed"
        )

        if useful:
            return result

    except Exception as exc:

        print(
            f"Normal detail request failed: "
            f"{exc}"
        )

    # --------------------------------------------------------
    # Fallback: JS-rendered detail page.
    # --------------------------------------------------------

    try:

        html = scraperapi_fetch(
            card["binged_link"],
            render=True
        )

        return parse_detail_page(
            html,
            card
        )

    except Exception as exc:

        print(
            f"Rendered detail request failed: "
            f"{exc}"
        )

        return {
            "title": card["title"],
            "rating": "Not listed",
            "release": card.get(
                "release",
                "Not listed"
            ),
            "type": "Not listed",
            "genre": "Not listed",
            "language": "Not listed",
            "platform": "Not listed",
            "binged_link": card[
                "binged_link"
            ],
        }


# ============================================================
# FETCH LATEST RELEASES
# ============================================================

def fetch_latest():

    html = fetch_binged_listing()

    cards = find_listing_titles(
        html
    )

    if not cards:
        raise RuntimeError(
            "Binged page was fetched successfully "
            "but no title links could be extracted."
        )

    enriched = []

    for card in cards:

        enriched_card = enrich_card(
            card
        )

        enriched.append(
            enriched_card
        )

        time.sleep(
            DETAIL_DELAY
        )

    return enriched


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
# TELEGRAM MESSAGE
# ============================================================

def make_message(card):

    return (
        f"🎬 {card['title']}\n"
        f"⭐ Rating: {card['rating']}\n"
        f"📅 Release: {card['release']}\n"
        f"🎞 Type: {card['type']}\n"
        f"🎭 Genre: {card['genre']}\n"
        f"🗣 Language: {card['language']}\n"
        f"📺 Platform: {card['platform']}"
    )


def make_keyboard(card):

    return {
        "inline_keyboard": [
            [
                {
                    "text": "▶ Open in Stremio",
                    "url": stremio_link(
                        card["title"]
                    ),
                },
                {
                    "text": "🔗 Open on Binged",
                    "url": card[
                        "binged_link"
                    ],
                },
            ]
        ]
    }


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_api(
    method,
    params=None,
    post=False
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

    if post:
        response = requests.post(
            url,
            data=params or {},
            timeout=30
        )
    else:
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
            keyboard,
            ensure_ascii=False
        )

    telegram_api(
        "sendMessage",
        params,
        post=True
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

    try:

        telegram_api(
            "setMyCommands",
            {
                "commands": json.dumps(
                    commands
                )
            },
            post=True
        )

        print(
            "Telegram command menu registered."
        )

    except Exception as exc:

        print(
            f"Could not register Telegram "
            f"commands: {exc}"
        )


# ============================================================
# TELEGRAM OFFSET
# ============================================================

def load_offset():

    if not os.path.exists(
        OFFSET_FILE
    ):
        return 0

    try:

        with open(
            OFFSET_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

        return int(
            data.get(
                "offset",
                0
            )
        )

    except Exception:
        return 0


def save_offset(offset):

    with open(
        OFFSET_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            {
                "offset": offset
            },
            file
        )


# ============================================================
# GET TELEGRAM COMMAND
# ============================================================

def get_recent_command():

    offset = load_offset()

    try:

        result = telegram_api(
            "getUpdates",
            {
                "offset": offset,
                "limit": 20,
                "timeout": 0,
                "allowed_updates": json.dumps(
                    ["message"]
                ),
            }
        )

    except Exception as exc:

        print(
            f"Telegram getUpdates error: "
            f"{exc}"
        )

        return None

    updates = result.get(
        "result",
        []
    )

    if not updates:
        return None

    now = int(
        time.time()
    )

    selected = None

    for update in updates:

        update_id = update.get(
            "update_id"
        )

        if update_id is not None:
            save_offset(
                int(update_id) + 1
            )

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

        command = text.lower().split(
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

        if (
            now - message_date
            > COMMAND_MAX_AGE
        ):
            continue

        selected = message

    if selected:
        print(
            "Telegram command received: "
            f"{selected.get('text')}"
        )

    return selected


# ============================================================
# HELP
# ============================================================

def send_help(chat_id):

    text = (
        "🤖 Binged OTT Tracker\n\n"
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

    send_telegram(
        chat_id,
        text
    )


# ============================================================
# FILTERS
# ============================================================

def send_filters(chat_id):

    text = (
        "🔎 Active Binged filters\n\n"
        "Category: Film + TV Show\n"
        "Language: Hindi + Punjabi\n"
        "Mode: Streaming Now\n"
        "Rating: Must Watch + Good + "
        "Satisfactory + Passable + Poor + Skip"
    )

    send_telegram(
        chat_id,
        text
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
            f"Could not load seen titles: "
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
            "No matching releases found."
        )

        return

    for card in cards:

        send_telegram(
            chat_id,
            make_message(card),
            make_keyboard(card)
        )

        time.sleep(
            0.2
        )

    send_telegram(
        chat_id,
        f"✅ {len(cards)} title(s) found."
    )


# ============================================================
# FILTER CARDS
# ============================================================

def filter_cards(
    cards,
    command
):

    if command == "latest":
        return cards

    if command == "all":
        return cards

    if command == "movies":
        return [
            card for card in cards
            if card["type"].lower() == "film"
        ]

    if command == "shows":
        return [
            card for card in cards
            if card["type"].lower() == "tv show"
        ]

    if command == "hindi":
        return [
            card for card in cards
            if "hindi" in card["language"].lower()
        ]

    if command == "punjabi":
        return [
            card for card in cards
            if "punjabi" in card["language"].lower()
        ]

    if command in {
        "mustwatch",
        "good",
        "satisfactory",
        "passable",
        "poor",
        "skip",
    }:

        target = {
            "mustwatch": "must watch",
            "good": "good",
            "satisfactory": "satisfactory",
            "passable": "passable",
            "poor": "poor",
            "skip": "skip",
        }[command]

        return [
            card for card in cards
            if card["rating"].lower()
            == target
        ]

    if command == "today":

        today = datetime.now(
            IST
        ).date()

        result = []

        for card in cards:

            parsed = parse_date(
                card["release"]
            )

            if parsed and parsed.date() == today:
                result.append(card)

        return result

    return cards


# ============================================================
# COMMAND HANDLER
# ============================================================

def handle_command(message):

    chat_id = message[
        "chat"
    ][
        "id"
    ]

    command = clean_text(
        message.get(
            "text",
            ""
        )
    ).lower().split(
        "@",
        1
    )[0].lstrip("/")

    if command == "start":

        send_telegram(
            chat_id,
            "🤖 Binged OTT Tracker is active.\n\n"
            "Use /help to see all commands."
        )

        return

    if command == "help":

        send_help(
            chat_id
        )

        return

    if command == "filters":

        send_filters(
            chat_id
        )

        return

    if command == "status":

        seen = load_seen()

        send_telegram(
            chat_id,
            "📊 Binged OTT Tracker\n\n"
            f"Previously sent titles: {len(seen)}\n"
            "Source: Binged\n"
            "Filters: Hindi + Punjabi / Film + TV Show\n"
            "Mode: Streaming Now"
        )

        return

    if command == "refresh":

        send_telegram(
            chat_id,
            "🔄 Fetching Binged releases..."
        )

        cards = fetch_latest()

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

                seen.add(key)

        save_seen(
            seen
        )

        if new_cards:

            send_cards(
                chat_id,
                new_cards,
                "🆕 NEW BINGED RELEASES"
            )

        else:

            send_telegram(
                chat_id,
                "✅ No new releases found."
            )

        return

    if command in {
        "latest",
        "today",
        "movies",
        "shows",
        "hindi",
        "punjabi",
        "mustwatch",
        "good",
        "satisfactory",
        "passable",
        "poor",
        "skip",
        "all",
    }:

        send_telegram(
            chat_id,
            "🔄 Fetching Binged releases..."
        )

        cards = fetch_latest()

        filtered = filter_cards(
            cards,
            command
        )

        headings = {
            "latest": "🎬 LATEST — FILTERED BINGED RESULTS",
            "today": "📅 TODAY'S OTT RELEASES",
            "movies": "🎬 LATEST HINDI / PUNJABI MOVIES",
            "shows": "📺 LATEST HINDI / PUNJABI TV SHOWS",
            "hindi": "🇮🇳 LATEST HINDI RELEASES",
            "punjabi": "🇮🇳 LATEST PUNJABI RELEASES",
            "mustwatch": "⭐ MUST WATCH",
            "good": "⭐ GOOD",
            "satisfactory": "⭐ SATISFACTORY",
            "passable": "⭐ PASSABLE",
            "poor": "⭐ POOR",
            "skip": "⭐ SKIP",
            "all": "🎬 ALL FILTERED RELEASES",
        }

        send_cards(
            chat_id,
            filtered,
            headings[command]
        )

        return

    send_help(
        chat_id
    )


# ============================================================
# AUTOMATIC HOURLY / SCHEDULED UPDATE
# ============================================================

def automatic_update():

    print(
        "Fetching Binged releases..."
    )

    cards = fetch_latest()

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

        send_telegram(
            TELEGRAM_CHAT_ID,
            make_message(card),
            make_keyboard(card)
        )

        seen.add(key)

        new_count += 1

        time.sleep(
            0.2
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

    register_commands()

    command_message = get_recent_command()

    if command_message:

        handle_command(
            command_message
        )

        return

    automatic_update()


if __name__ == "__main__":

    try:

        run()

    except Exception as exc:

        print("")
        print(
            "========================================"
        )
        print(
            "ERROR"
        )
        print(
            "========================================"
        )
        print(
            str(exc)
        )

        raise
