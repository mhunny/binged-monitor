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

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

CACHE_FILE = "binged_cache.json"
SEEN_FILE = "seen_titles.json"

IST = ZoneInfo("Asia/Kolkata")
COMMAND_MAX_AGE_SECONDS = 10 * 60


# ============================================================
# FILTERS
# ============================================================

RATINGS = [
    "Must Watch",
    "Good",
    "Satisfactory",
    "Passable",
    "Poor",
    "Skip",
]

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

COMMAND_DESCRIPTIONS = [
    ("start", "Start Binged OTT Tracker"),
    ("help", "Show all commands"),
    ("latest", "Latest filtered releases"),
    ("today", "Today's releases"),
    ("movies", "Latest movies"),
    ("shows", "Latest TV shows"),
    ("hindi", "Latest Hindi releases"),
    ("punjabi", "Latest Punjabi releases"),
    ("mustwatch", "Must Watch"),
    ("good", "Good"),
    ("satisfactory", "Satisfactory"),
    ("passable", "Passable"),
    ("poor", "Poor"),
    ("skip", "Skip"),
    ("all", "All filtered releases"),
    ("refresh", "Refresh Binged data"),
    ("status", "Tracker status"),
    ("filters", "Active filters"),
]


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
            "%d %b %Y",
        )
    except ValueError:
        return None


def find_rating(text):
    for rating in sorted(RATINGS, key=len, reverse=True):
        if re.search(
            rf"\b{re.escape(rating)}\b",
            text,
            re.IGNORECASE,
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


def find_languages(text):
    found = []
    for language in LANGUAGES:
        if re.search(
            rf"\b{re.escape(language)}\b",
            text,
            re.IGNORECASE,
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
            re.IGNORECASE,
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

    normalized = str(text)
    normalized = normalized.replace("\\/", "/")
    normalized = re.sub(r"[-_+/]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()

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

    for alias, name in sorted(
        platforms,
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if alias in normalized:
            return name

    return None


def extract_platform(element):
    if not element:
        return "Not listed"

    # Search only this card/container, not the complete page.
    values = [
        element.get_text(" ", strip=True)
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
            "data-title",
            "data-platform",
            "data-provider",
            "data-service",
            "data-network",
        ]:
            value = tag.get(attr)

            if isinstance(value, list):
                value = " ".join(
                    str(x) for x in value
                )

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

    if not title:
        return ""

    for rating in sorted(RATINGS, key=len, reverse=True):
        title = re.sub(
            rf"\s+{re.escape(rating)}$",
            "",
            title,
            flags=re.IGNORECASE,
        )

    title = re.sub(
        r"\s+(?:Film|TV\s*Show)$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return clean_text(title)


def find_title_link(element):
    candidates = []

    excluded = {
        "view all",
        "read more",
        "streaming dates",
        "filters",
        "clear",
        "home",
        "reviews",
        "news",
        "ranked lists",
    }

    rating_names = {
        x.lower()
        for x in RATINGS
    }

    for anchor in element.find_all(
        "a",
        href=True,
    ):
        raw_text = clean_text(
            anchor.get_text(
                " ",
                strip=True,
            )
        )

        href = anchor.get("href")

        if not raw_text or not href:
            continue

        title = clean_title(raw_text)

        if len(title) < 2 or len(title) > 150:
            continue

        if title.lower() in excluded:
            continue

        if title.lower() in rating_names:
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
# PARSE BINGED
# ============================================================

def parse_cards(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    date_pattern = re.compile(
        r"\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}\b",
        re.IGNORECASE,
    )

    rating_pattern = re.compile(
        r"\b"
        r"(?:Must Watch|Good|Satisfactory|Passable|Poor|Skip)"
        r"\b",
        re.IGNORECASE,
    )

    candidates = []

    # This is the parser structure that previously produced
    # the working 20-title /latest result.
    for element in soup.find_all(
        ["article", "li", "tr", "div"]
    ):
        text = clean_text(
            element.get_text(
                " ",
                strip=True,
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
        key=lambda item: len(item[1])
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

        title, binged_link = find_title_link(
            element
        )

        if not title:
            continue

        title = clean_title(title)
        title_key = normal_key(title)

        if not title_key:
            continue

        if title_key in used:
            continue

        date_object = parse_date(
            release_date
        )

        cards.append({
            "title": title,
            "rating": rating,
            "date": release_date,
            "date_object": (
                date_object.isoformat()
                if date_object
                else None
            ),
            "type": find_type(text),
            "genre": find_genres(text),
            "language": find_languages(text),
            "platform": extract_platform(element),
            "binged_link": (
                urljoin(
                    BINGED_BASE,
                    binged_link,
                )
                if binged_link
                else BINGED_BASE
            ),
        })

        used.add(title_key)

    cards.sort(
        key=lambda card: (
            card.get("date_object")
            or ""
        ),
        reverse=True,
    )

    print(
        f"Extracted {len(cards)} title(s)"
    )

    return cards


# ============================================================
# SCRAPERAPI
# ============================================================

def fetch_binged(url):
    if not SCRAPER_API_KEY:
        raise RuntimeError(
            "SCRAPER_API_KEY secret is missing."
        )

    # Normal request first. This is faster and was sufficient
    # for the working latest-page result.
    modes = [
        (
            "normal",
            {
                "api_key": SCRAPER_API_KEY,
                "url": url,
            },
        ),
        (
            "render",
            {
                "api_key": SCRAPER_API_KEY,
                "url": url,
                "render": "true",
            },
        ),
    ]

    last_error = None

    for mode_name, params in modes:

        print(
            f"ScraperAPI mode: {mode_name}"
        )

        try:
            response = requests.get(
                "https://api.scraperapi.com/",
                params=params,
                timeout=120,
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
            ]

            if any(
                phrase in lower
                for phrase in blocked_phrases
            ):
                last_error = (
                    "Binged returned a "
                    "verification/block page."
                )
                continue

            return html

        except Exception as exc:
            last_error = str(exc)
            print(
                f"ScraperAPI error: {exc}"
            )

        time.sleep(2)

    raise RuntimeError(
        last_error
        or "Could not fetch Binged."
    )


# ============================================================
# CACHE
# ============================================================

def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def load_json(path, default):
    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)
    except Exception:
        return default


def refresh_cache():
    print(
        "Fetching Binged releases..."
    )

    html = fetch_binged(
        BINGED_LATEST_URL
    )

    cards = parse_cards(html)

    # Never replace a working cache with an empty parse.
    if not cards:
        raise RuntimeError(
            "Binged page was fetched, but "
            "0 titles were parsed. Existing data "
            "has not been replaced."
        )

    cache = {
        "updated_at": int(time.time()),
        "updated_ist": datetime.now(
            IST
        ).strftime(
            "%d %b %Y %H:%M:%S"
        ),
        "source": BINGED_LATEST_URL,
        "cards": cards,
    }

    save_json(
        CACHE_FILE,
        cache,
    )

    print(
        f"Cached {len(cards)} title(s)."
    )

    return cards


def get_cards():
    cache = load_json(
        CACHE_FILE,
        {},
    )

    cards = cache.get(
        "cards",
        [],
    )

    if not isinstance(
        cards,
        list,
    ):
        return []

    return cards


# ============================================================
# TELEGRAM
# ============================================================

def telegram_request(
    method,
    params=None,
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
        timeout=30,
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
    keyboard=None,
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
        params,
    )


def register_commands():
    commands = [
        {
            "command": command,
            "description": description,
        }
        for command, description
        in COMMAND_DESCRIPTIONS
    ]

    telegram_request(
        "setMyCommands",
        {
            "commands": json.dumps(
                commands
            )
        },
    )


def clear_webhook():
    telegram_request(
        "deleteWebhook",
        {
            "drop_pending_updates": "false"
        },
    )


def get_updates():
    result = telegram_request(
        "getUpdates",
        {
            "limit": 20,
            "timeout": 0,
            "allowed_updates": json.dumps(
                ["message"]
            ),
        },
    )

    return result.get(
        "result",
        []
    )


def acknowledge_updates(updates):
    if not updates:
        return

    last_id = max(
        int(update["update_id"])
        for update in updates
    )

    telegram_request(
        "getUpdates",
        {
            "offset": last_id + 1,
            "limit": 1,
            "timeout": 0,
            "allowed_updates": json.dumps(
                ["message"]
            ),
        },
    )


def get_latest_command(updates):
    now = int(time.time())
    latest = None

    for update in updates:

        message = update.get(
            "message"
        )

        if not message:
            continue

        text = clean_text(
            message.get(
                "text",
                "",
            )
        )

        if not text.startswith("/"):
            continue

        command = (
            text.split()[0]
            .lower()
            .split("@", 1)[0]
        )

        if command not in COMMANDS:
            continue

        message_date = int(
            message.get(
                "date",
                0,
            )
        )

        if (
            now - message_date
            > COMMAND_MAX_AGE_SECONDS
        ):
            continue

        latest = message

    return latest


# ============================================================
# DISPLAY
# ============================================================

def stremio_web_link(title):
    return (
        "https://web.stremio.com/"
        "#/search?search="
        + quote(
            title,
            safe="",
        )
    )


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
                    "url": card.get(
                        "binged_link",
                        BINGED_BASE,
                    ),
                }
            ],
        ]
    }


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


def help_text():
    lines = [
        "📖 Binged OTT Tracker",
        "",
        "Commands:",
    ]

    for command, description in COMMAND_DESCRIPTIONS:
        lines.append(
            f"/{command} — {description}"
        )

    return "\n".join(lines)


def filters_text():
    return (
        "🔎 Active filters\n\n"
        "Category: Film + TV Show\n"
        "Language: Hindi + Punjabi\n"
        "Mode: Streaming now\n"
        "Ratings: Must Watch, Good, "
        "Satisfactory, Passable, Poor, Skip\n"
        "Source: Binged\n"
        "Results: latest fetched Binged page"
    )


def status_text(cards):
    cache = load_json(
        CACHE_FILE,
        {},
    )

    updated = cache.get(
        "updated_ist",
        "Never",
    )

    return (
        "📊 Tracker status\n\n"
        f"Cached titles: {len(cards)}\n"
        f"Last refresh: {updated} IST"
    )


# ============================================================
# FILTERING
# ============================================================

def card_date_object(card):
    value = card.get(
        "date_object"
    )

    if value:
        try:
            return datetime.fromisoformat(
                value
            )
        except Exception:
            pass

    parsed = parse_date(
        card.get(
            "date",
            "",
        )
    )

    return parsed or datetime.min


def sort_cards(cards):
    return sorted(
        cards,
        key=card_date_object,
        reverse=True,
    )


def filter_cards(cards, mode):
    cards = sort_cards(cards)

    if mode == "latest":
        return cards[:20]

    if mode == "today":
        today = datetime.now(
            IST
        ).date()

        return [
            card
            for card in cards
            if (
                parse_date(
                    card.get("date", "")
                )
                and parse_date(
                    card.get("date", "")
                ).date()
                == today
            )
        ]

    if mode == "movies":
        return [
            card
            for card in cards
            if card.get(
                "type",
                "",
            ).lower() == "film"
        ][:20]

    if mode == "shows":
        return [
            card
            for card in cards
            if card.get(
                "type",
                "",
            ).lower() == "tv show"
        ][:20]

    if mode == "hindi":
        return [
            card
            for card in cards
            if "hindi" in card.get(
                "language",
                "",
            ).lower()
        ][:20]

    if mode == "punjabi":
        return [
            card
            for card in cards
            if "punjabi" in card.get(
                "language",
                "",
            ).lower()
        ][:20]

    rating_map = {
        "mustwatch": "Must Watch",
        "good": "Good",
        "satisfactory": "Satisfactory",
        "passable": "Passable",
        "poor": "Poor",
        "skip": "Skip",
    }

    if mode in rating_map:
        target = rating_map[mode].lower()

        return [
            card
            for card in cards
            if card.get(
                "rating",
                "",
            ).lower() == target
        ][:20]

    if mode == "all":
        return cards

    return cards[:20]


# ============================================================
# SEND RESULTS
# ============================================================

def send_cards(
    chat_id,
    cards,
    heading,
):
    send_telegram(
        chat_id,
        heading,
    )

    if not cards:
        send_telegram(
            chat_id,
            "No matching titles found.",
        )
        return

    for card in cards:
        send_telegram(
            chat_id,
            make_message(card),
            make_keyboard(card),
        )
        time.sleep(0.10)

    send_telegram(
        chat_id,
        f"✅ {len(cards)} title(s) found.",
    )


# ============================================================
# COMMAND HANDLER
# ============================================================

def handle_command(
    message,
    command,
):
    chat_id = message[
        "chat"
    ][
        "id"
    ]

    if command == "start":
        send_telegram(
            chat_id,
            "🎬 Binged OTT Tracker is active.\n\n"
            "Use /help to see all commands.",
        )
        return

    if command == "help":
        send_telegram(
            chat_id,
            help_text(),
        )
        return

    if command == "filters":
        send_telegram(
            chat_id,
            filters_text(),
        )
        return

    cards = get_cards()

    if command == "status":
        send_telegram(
            chat_id,
            status_text(cards),
        )
        return

    if command == "refresh":

        send_telegram(
            chat_id,
            "🔄 Fetching Binged releases...",
        )

        try:
            cards = refresh_cache()

            send_telegram(
                chat_id,
                "✅ Binged refresh complete.\n\n"
                f"{len(cards)} title(s) cached.",
            )

        except Exception as exc:
            send_telegram(
                chat_id,
                "❌ Could not fetch Binged right now.\n\n"
                f"{exc}",
            )

        return

    # If there is no cache, fetch once.
    if not cards:

        send_telegram(
            chat_id,
            "🔄 Fetching Binged releases...",
        )

        try:
            cards = refresh_cache()

        except Exception as exc:
            send_telegram(
                chat_id,
                "❌ Could not fetch Binged right now.\n\n"
                f"{exc}",
            )
            return

    selected = filter_cards(
        cards,
        command,
    )

    headings = {
        "latest":
            "🎬 LATEST — FILTERED BINGED RESULTS",
        "today":
            "📅 TODAY'S OTT RELEASES",
        "movies":
            "🎬 LATEST MOVIES",
        "shows":
            "📺 LATEST TV SHOWS",
        "hindi":
            "🇮🇳 LATEST HINDI RELEASES",
        "punjabi":
            "🟠 LATEST PUNJABI RELEASES",
        "mustwatch":
            "⭐ MUST WATCH",
        "good":
            "⭐ GOOD",
        "satisfactory":
            "⭐ SATISFACTORY",
        "passable":
            "⭐ PASSABLE",
        "poor":
            "⭐ POOR",
        "skip":
            "⭐ SKIP",
        "all":
            "🎬 ALL FILTERED RELEASES",
    }

    send_cards(
        chat_id,
        selected,
        headings.get(
            command,
            "🎬 RESULTS",
        ),
    )


# ============================================================
# AUTOMATIC UPDATE
# ============================================================

def automatic_update():
    print(
        "Checking latest Binged page..."
    )

    cards = refresh_cache()

    previous = load_json(
        SEEN_FILE,
        None,
    )

    # First successful run establishes baseline.
    # It does NOT spam Telegram with all existing titles.
    if previous is None:

        seen = sorted({
            normal_key(card["title"])
            for card in cards
            if normal_key(card["title"])
        })

        save_json(
            SEEN_FILE,
            seen,
        )

        print(
            "Initial seen-title baseline created."
        )

        return

    seen = set(
        previous
        if isinstance(previous, list)
        else []
    )

    new_cards = []

    for card in cards:

        key = normal_key(
            card["title"]
        )

        if not key:
            continue

        if key not in seen:
            new_cards.append(card)
            seen.add(key)

    save_json(
        SEEN_FILE,
        sorted(seen),
    )

    if not TELEGRAM_CHAT_ID:
        print(
            "TELEGRAM_CHAT_ID is missing."
        )
        return

    for card in reversed(new_cards):
        send_telegram(
            TELEGRAM_CHAT_ID,
            make_message(card),
            make_keyboard(card),
        )
        time.sleep(0.10)

    print(
        f"New automatic alerts: "
        f"{len(new_cards)}"
    )


# ============================================================
# MAIN
# ============================================================

def run():

    print("")
    print("=" * 50)
    print("BINGED → TELEGRAM")
    print("=" * 50)

    if not SCRAPER_API_KEY:
        raise RuntimeError(
            "SCRAPER_API_KEY secret is missing."
        )

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN secret is missing."
        )

    clear_webhook()
    register_commands()

    updates = get_updates()
    command_message = get_latest_command(
        updates
    )

    if command_message:

        raw_text = clean_text(
            command_message.get(
                "text",
                "",
            )
        )

        command = (
            raw_text.split()[0]
            .lower()
            .split("@", 1)[0]
        )

        print(
            f"Telegram command received: {command}"
        )

        try:
            handle_command(
                command_message,
                COMMANDS[command],
            )
        finally:
            # Consume the update only after it has
            # been handled, preventing old commands
            # from repeating on the next run.
            acknowledge_updates(
                updates
            )

        return

    if updates:
        acknowledge_updates(
            updates
        )

    automatic_update()


if __name__ == "__main__":

    try:
        run()
    except Exception as exc:
        print("")
        print("=" * 50)
        print("ERROR")
        print("=" * 50)
        print(str(exc))
        raise
