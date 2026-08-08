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


# ============================================================
# SECRETS
# ============================================================

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


# ============================================================
# LOCAL FILES
# ============================================================

SEEN_FILE = "seen_titles.json"
TELEGRAM_OFFSET_FILE = "telegram_offset.json"


# ============================================================
# SETTINGS
# ============================================================

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


TELEGRAM_COMMAND_LIST = [
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
        r"\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}\b",
        text,
        re.IGNORECASE,
    )

    return (
        match.group(0)
        if match
        else "Not listed"
    )


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

    return (
        ", ".join(found)
        if found
        else "Not listed"
    )


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

    return (
        ", ".join(found)
        if found
        else "Not listed"
    )


# ============================================================
# PLATFORM
# ============================================================

def find_platform(text):

    if not text:
        return None

    normalized = str(text).lower()

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
        if alias in normalized:
            return name

    return None


def extract_platform(element):

    if not element:
        return "Not listed"

    values = [
        str(element),
        element.get_text(
            " ",
            strip=True
        ),
    ]

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

        result = find_platform(
            value
        )

        if result:
            return result

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


def find_title_link(element):

    candidates = []

    for anchor in element.find_all(
        "a",
        href=True
    ):

        raw = clean_text(
            anchor.get_text(
                " ",
                strip=True
            )
        )

        href = anchor.get("href")

        if not raw or not href:
            continue

        title = clean_title(raw)

        if len(title) < 2:
            continue

        if len(title) > 150:
            continue

        excluded = [
            "view all",
            "read more",
            "streaming dates",
            "filters",
            "clear",
            "home",
            "reviews",
            "news",
            "ranked lists",
        ]

        if title.lower() in excluded:
            continue

        if title.lower() in [
            x.lower()
            for x in RATINGS
        ]:
            continue

        candidates.append(
            (title, href)
        )

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
# PARSE BINGED PAGE
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

        if len(text) > 2500:
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

        title, link = find_title_link(
            element
        )

        if not title:
            continue

        key = normal_key(title)

        if not key:
            continue

        if key in used:
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
            "platform": extract_platform(
                element
            ),
            "binged_link": (
                urljoin(
                    BINGED_BASE,
                    link
                )
                if link
                else BINGED_BASE
            ),
        })

        used.add(key)

    print(
        f"Extracted {len(cards)} title(s)"
    )

    return cards


# ============================================================
# NEXT PAGE
# ============================================================

def find_next_page(
    html,
    current_url
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    for anchor in soup.find_all(
        "a",
        href=True
    ):

        rel = anchor.get("rel")

        if rel:

            if isinstance(
                rel,
                list
            ):
                rel_text = " ".join(
                    rel
                ).lower()
            else:
                rel_text = str(
                    rel
                ).lower()

            if "next" in rel_text:

                next_url = urljoin(
                    current_url,
                    anchor["href"]
                )

                if next_url != current_url:
                    return next_url

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
# SCRAPER API
# ============================================================

def fetch_binged(
    url,
    attempts=3
):

    if not SCRAPER_API_KEY:
        raise RuntimeError(
            "SCRAPER_API_KEY secret is missing."
        )

    last_error = None

    for attempt in range(
        1,
        attempts + 1
    ):

        print(
            f"ScraperAPI request "
            f"{attempt}/{attempts}"
        )

        try:

            params = {
                "api_key": SCRAPER_API_KEY,
                "url": url,
                "render": "true",
            }

            response = requests.get(
                "https://api.scraperapi.com/",
                params=params,
                timeout=180
            )

            print(
                "ScraperAPI HTTP status: "
                f"{response.status_code}"
            )

            print(
                "Returned content length: "
                f"{len(response.text)}"
            )

            if response.status_code == 200:

                html = response.text

                lower = html[
                    :30000
                ].lower()

                blocked = [
                    "access denied",
                    "<title>forbidden</title>",
                    "verify you are human",
                    "checking your browser",
                    "just a moment",
                    "cf-chl-",
                ]

                if any(
                    phrase in lower
                    for phrase in blocked
                ):
                    raise RuntimeError(
                        "Binged returned a "
                        "verification/block page."
                    )

                return html

            last_error = (
                "ScraperAPI returned HTTP "
                f"{response.status_code}"
            )

        except Exception as exc:

            last_error = str(exc)

            print(
                f"Attempt failed: {exc}"
            )

        if attempt < attempts:

            wait = attempt * 8

            print(
                f"Retrying in "
                f"{wait} seconds..."
            )

            time.sleep(wait)

    raise RuntimeError(
        last_error
        or "Could not fetch Binged."
    )


# ============================================================
# FETCH LATEST
# ============================================================

def fetch_latest():

    print(
        "Fetching latest Binged page..."
    )

    print(BINGED_LATEST_URL)

    html = fetch_binged(
        BINGED_LATEST_URL
    )

    cards = parse_cards(html)

    cards.sort(
        key=lambda card: (
            card["date_object"]
            or datetime.min
        ),
        reverse=True
    )

    return cards


# ============================================================
# CATEGORY URL
# ============================================================

def make_category_url(category):

    value = CATEGORY_VALUES.get(
        category
    )

    if not value:
        raise ValueError(
            f"Unknown category: {category}"
        )

    return (
        BINGED_BASE
        + "?category%5B%5D=Film"
        + "&category%5B%5D=Tv%20show"
        + "&language%5B%5D=Hindi"
        + "&language%5B%5D=Punjabi"
        + "&mode=streaming-now"
        + "&recommendation%5B%5D="
        + value
    )


# ============================================================
# FETCH ALL PAGES FOR RATING
# ============================================================

def fetch_category_all_pages(
    category
):

    first_url = make_category_url(
        category
    )

    print(
        f"Fetching ALL {category} pages..."
    )

    all_cards = []

    current_url = first_url
    visited = set()

    for page_number in range(
        1,
        MAX_CATEGORY_PAGES + 1
    ):

        if current_url in visited:
            print(
                "Pagination loop detected."
            )
            break

        visited.add(current_url)

        print(
            f"Category page "
            f"{page_number}"
        )

        html = fetch_binged(
            current_url
        )

        page_cards = parse_cards(
            html
        )

        all_cards.extend(
            page_cards
        )

        next_url = find_next_page(
            html,
            current_url
        )

        if not next_url:
            break

        current_url = next_url

        time.sleep(1)

    unique = {}

    for card in all_cards:

        key = normal_key(
            card["title"]
        )

        if key and key not in unique:
            unique[key] = card

    cards = list(
        unique.values()
    )

    cards.sort(
        key=lambda card: (
            card["date_object"]
            or datetime.min
        ),
        reverse=True
    )

    return cards


# ============================================================
# STREMIO
# ============================================================

def stremio_web_link(title):

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
                    "url": stremio_web_link(
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
        "chat_id": str(chat_id),
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

    print(
        "Registering Telegram commands..."
    )

    result = telegram_api(
        "setMyCommands",
        {
            "commands": json.dumps(
                TELEGRAM_COMMAND_LIST,
                ensure_ascii=False
            )
        },
        post=True
    )

    print(
        "Telegram command menu registered."
    )

    return result


# ============================================================
# TELEGRAM WEBHOOK
# ============================================================

def remove_webhook():

    try:

        telegram_api(
            "deleteWebhook",
            {
                "drop_pending_updates": "false"
            },
            post=True
        )

        print(
            "Telegram webhook cleared."
        )

    except Exception as exc:

        print(
            f"Webhook cleanup warning: {exc}"
        )


# ============================================================
# TELEGRAM OFFSET
# ============================================================

def load_offset():

    if not os.path.exists(
        TELEGRAM_OFFSET_FILE
    ):
        return None

    try:

        with open(
            TELEGRAM_OFFSET_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        value = data.get(
            "offset"
        )

        if value is None:
            return None

        return int(value)

    except Exception as exc:

        print(
            f"Could not read Telegram offset: "
            f"{exc}"
        )

        return None


def save_offset(offset):

    with open(
        TELEGRAM_OFFSET_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            {
                "offset": int(offset)
            },
            file
        )


# ============================================================
# GET TELEGRAM COMMAND
# ============================================================

def get_recent_command():

    offset = load_offset()

    params = {
        "limit": 100,
        "timeout": 0,
        "allowed_updates": json.dumps(
            ["message"]
        ),
    }

    if offset is not None:
        params["offset"] = offset

    try:

        result = telegram_api(
            "getUpdates",
            params
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

    latest_command = None

    now = int(time.time())

    highest_update_id = None

    for update in updates:

        update_id = update.get(
            "update_id"
        )

        if update_id is not None:

            highest_update_id = max(
                highest_update_id or update_id,
                update_id
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
        )[0].split(
            " ",
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
            > COMMAND_MAX_AGE_SECONDS
        ):
            continue

        latest_command = message

    # Confirm ALL updates returned by Telegram.
    # Telegram requires offset = update_id + 1.
    if highest_update_id is not None:

        save_offset(
            highest_update_id + 1
        )

    return latest_command


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

            data = json.load(file)

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
# SEND CARDS
# ============================================================

def send_cards(
    chat_id,
    cards,
    heading=None,
    limit=None
):

    if heading:

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

    if limit is not None:

        cards = cards[:limit]

    for card in cards:

        send_telegram(
            chat_id,
            make_message(card),
            make_keyboard(card)
        )

        time.sleep(0.15)

    send_telegram(
        chat_id,
        f"✅ {len(cards)} title(s) found."
    )


# ============================================================
# HELP
# ============================================================

def help_text():

    return (
        "🤖 Binged OTT Tracker\n\n"

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
        "🔎 ACTIVE BINGED FILTERS\n\n"
        "Category: Film + TV Show\n"
        "Language: Hindi + Punjabi\n"
        "Mode: Streaming Now\n"
        "Ratings:\n"
        "• Must Watch\n"
        "• Good\n"
        "• Satisfactory\n"
        "• Passable\n"
        "• Poor\n"
        "• Skip"
    )


# ============================================================
# STATUS
# ============================================================

def status_text():

    seen = load_seen()

    return (
        "📊 BINGED OTT TRACKER STATUS\n\n"
        f"Seen titles: {len(seen)}\n"
        f"ScraperAPI: "
        f"{'Configured' if SCRAPER_API_KEY else 'Missing'}\n"
        f"Telegram token: "
        f"{'Configured' if TELEGRAM_BOT_TOKEN else 'Missing'}\n"
        f"Telegram chat ID: "
        f"{'Configured' if TELEGRAM_CHAT_ID else 'Missing'}\n"
        f"Update offset: "
        f"{load_offset() or 'Not set'}"
    )


# ============================================================
# COMMAND HANDLER
# ============================================================

def handle_command(message):

    chat_id = message[
        "chat"
    ][
        "id"
    ]

    text = clean_text(
        message.get(
            "text",
            ""
        )
    ).lower()

    command = text.split(
        "@",
        1
    )[0].split(
        " ",
        1
    )[0]

    print(
        f"Telegram command received: "
        f"{command}"
    )

    # --------------------------------------------------------
    # /start
    # --------------------------------------------------------

    if command == "/start":

        send_telegram(
            chat_id,
            "✅ Binged OTT Tracker is active.\n\n"
            "Use /help to see all commands."
        )

        return True

    # --------------------------------------------------------
    # /help
    # --------------------------------------------------------

    if command == "/help":

        send_telegram(
            chat_id,
            help_text()
        )

        return True

    # --------------------------------------------------------
    # /filters
    # --------------------------------------------------------

    if command == "/filters":

        send_telegram(
            chat_id,
            filters_text()
        )

        return True

    # --------------------------------------------------------
    # /status
    # --------------------------------------------------------

    if command == "/status":

        send_telegram(
            chat_id,
            status_text()
        )

        return True

    # --------------------------------------------------------
    # Commands requiring Binged
    # --------------------------------------------------------

    if command in [
        "/latest",
        "/all",
        "/today",
        "/movies",
        "/shows",
        "/hindi",
        "/punjabi",
    ]:

        send_telegram(
            chat_id,
            "🔄 Fetching Binged releases..."
        )

        cards = fetch_latest()

        # /today
        if command == "/today":

            today = datetime.now(
                IST
            ).date()

            cards = [
                card
                for card in cards
                if (
                    card["date_object"]
                    and card["date_object"].date()
                    == today
                )
            ]

            send_cards(
                chat_id,
                cards,
                "📅 TODAY'S OTT RELEASES"
            )

            return True

        # /movies
        if command == "/movies":

            cards = [
                card
                for card in cards
                if card["type"] == "Film"
            ]

            send_cards(
                chat_id,
                cards,
                "🎬 HINDI + PUNJABI MOVIES"
            )

            return True

        # /shows
        if command == "/shows":

            cards = [
                card
                for card in cards
                if card["type"] == "TV Show"
            ]

            send_cards(
                chat_id,
                cards,
                "📺 HINDI + PUNJABI TV SHOWS"
            )

            return True

        # /hindi
        if command == "/hindi":

            cards = [
                card
                for card in cards
                if "Hindi" in card["language"]
            ]

            send_cards(
                chat_id,
                cards,
                "🇮🇳 HINDI RELEASES"
            )

            return True

        # /punjabi
        if command == "/punjabi":

            cards = [
                card
                for card in cards
                if "Punjabi" in card["language"]
            ]

            send_cards(
                chat_id,
                cards,
                "🟠 PUNJABI RELEASES"
            )

            return True

        # /latest and /all
        send_cards(
            chat_id,
            cards,
            "🎬 LATEST FILTERED BINGED RESULTS"
        )

        return True

    # --------------------------------------------------------
    # Rating commands
    # --------------------------------------------------------

    rating_commands = {
        "/mustwatch": "mustwatch",
        "/good": "good",
        "/satisfactory": "satisfactory",
        "/passable": "passable",
        "/poor": "poor",
        "/skip": "skip",
    }

    if command in rating_commands:

        category = rating_commands[
            command
        ]

        display_name = {
            "mustwatch": "Must Watch",
            "good": "Good",
            "satisfactory": "Satisfactory",
            "passable": "Passable",
            "poor": "Poor",
            "skip": "Skip",
        }[category]

        send_telegram(
            chat_id,
            f"🔄 Fetching ALL {display_name} "
            f"releases from Binged..."
        )

        cards = fetch_category_all_pages(
            category
        )

        cards = [
            card
            for card in cards
            if card["rating"].lower()
            == display_name.lower()
        ]

        send_cards(
            chat_id,
            cards,
            f"🎬 {display_name.upper()} "
            f"— BINGED RESULTS"
        )

        return True

    # --------------------------------------------------------
    # /refresh
    # --------------------------------------------------------

    if command == "/refresh":

        send_telegram(
            chat_id,
            "🔄 Checking Binged for new releases..."
        )

        cards = fetch_latest()

        seen = load_seen()

        new_cards = []

        for card in cards:

            key = normal_key(
                card["title"]
            )

            if not key:
                continue

            if key not in seen:

                new_cards.append(
                    card
                )

        if not new_cards:

            send_telegram(
                chat_id,
                "✅ No new Binged releases found."
            )

            return True

        for card in new_cards:

            send_telegram(
                chat_id,
                make_message(card),
                make_keyboard(card)
            )

            seen.add(
                normal_key(
                    card["title"]
                )
            )

            time.sleep(0.15)

        save_seen(seen)

        send_telegram(
            chat_id,
            f"✅ {len(new_cards)} new "
            f"title(s) found."
        )

        return True

    return False


# ============================================================
# AUTOMATIC UPDATE
# ============================================================

def automatic_update():

    print(
        "Checking latest Binged page..."
    )

    cards = fetch_latest()

    print(
        f"Latest page contains "
        f"{len(cards)} title(s)."
    )

    seen = load_seen()

    new_cards = []

    for card in cards:

        key = normal_key(
            card["title"]
        )

        if not key:
            continue

        if key in seen:
            continue

        new_cards.append(
            card
        )

    for card in new_cards:

        print(
            f"New title: "
            f"{card['title']}"
        )

        send_telegram(
            TELEGRAM_CHAT_ID,
            make_message(card),
            make_keyboard(card)
        )

        seen.add(
            normal_key(
                card["title"]
            )
        )

        time.sleep(0.15)

    save_seen(seen)

    print(
        f"New Telegram alerts: "
        f"{len(new_cards)}"
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

    # --------------------------------------------------------
    # Required secrets
    # --------------------------------------------------------

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
    # Make sure Telegram is configured for polling.
    # --------------------------------------------------------

    remove_webhook()

    # --------------------------------------------------------
    # Register command menu.
    # --------------------------------------------------------

    register_commands()

    # --------------------------------------------------------
    # Read Telegram command.
    # --------------------------------------------------------

    command_message = get_recent_command()

    if command_message:

        handled = handle_command(
            command_message
        )

        if handled:
            return

    # --------------------------------------------------------
    # No command = automatic tracker run.
    # --------------------------------------------------------

    automatic_update()


# ============================================================
# ENTRY POINT
# ============================================================

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
