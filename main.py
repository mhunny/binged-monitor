import os
import re
import json
import time
import requests

from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

BINGED_URL = (
    "https://www.binged.com/streaming-premiere-dates/"
    "?category%5B%5D=Film"
    "&category%5B%5D=Tv%20show"
    "&language%5B%5D=Hindi"
    "&language%5B%5D=Punjabi"
    "&mode=streaming-now"
    "&recommendation%5B%5D=Must_Watch"
    "&recommendation%5B%5D=Good"
    "&recommendation%5B%5D=Satisfactory"
    "&recommendation%5B%5D=Passable"
)

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SEEN_FILE = "seen_titles.json"

COMMAND_MAX_AGE_SECONDS = 10 * 60


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_api(method, params=None):

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/{method}"
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


def send_message(
    chat_id,
    text,
    reply_markup=None
):

    params = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }

    if reply_markup is not None:
        params["reply_markup"] = json.dumps(
            reply_markup
        )

    telegram_api(
        "sendMessage",
        params
    )


# ============================================================
# SCRAPERAPI
# ============================================================

def fetch_url(url, attempts=3):

    if not SCRAPER_API_KEY:
        raise RuntimeError(
            "SCRAPER_API_KEY secret is missing."
        )

    last_error = None

    for attempt in range(1, attempts + 1):

        print(
            f"ScraperAPI request "
            f"{attempt}/{attempts}"
        )

        try:

            params = {
                "api_key": SCRAPER_API_KEY,
                "url": url,
                "render": "true"
            }

            # Use premium proxy only on final retry.
            if attempt == attempts:
                params["premium"] = "true"

                print(
                    "Using premium proxy on final retry..."
                )

            response = requests.get(
                "https://api.scraperapi.com/",
                params=params,
                timeout=180
            )

            print(
                f"ScraperAPI HTTP status: "
                f"{response.status_code}"
            )

            print(
                f"Returned HTML length: "
                f"{len(response.text)}"
            )

            if response.status_code == 200:

                html = response.text

                first_part = html[:20000].lower()

                blocked_phrases = [
                    "access denied",
                    "<title>forbidden</title>",
                    "verify you are human",
                    "checking your browser",
                    "just a moment"
                ]

                for phrase in blocked_phrases:

                    if phrase in first_part:
                        raise RuntimeError(
                            f"Binged returned blocked/"
                            f"verification page: {phrase}"
                        )

                return html

            last_error = (
                f"ScraperAPI returned HTTP "
                f"{response.status_code}"
            )

        except Exception as e:

            last_error = str(e)

            print(
                f"ScraperAPI attempt "
                f"{attempt} failed: {e}"
            )

        if attempt < attempts:

            wait_seconds = attempt * 10

            print(
                f"Waiting {wait_seconds} seconds "
                f"before retry..."
            )

            time.sleep(
                wait_seconds
            )

    raise RuntimeError(
        last_error
        or "ScraperAPI request failed."
    )


def fetch_binged():

    print(
        "Fetching filtered Binged page..."
    )

    print(BINGED_URL)

    return fetch_url(
        BINGED_URL
    )


# ============================================================
# CONSTANTS
# ============================================================

RATINGS = [
    "Must Watch",
    "Good",
    "Satisfactory",
    "Passable",
    "Poor",
    "Skip",
    "Yet to Review"
]

TYPE_VALUES = [
    "Film",
    "TV Show",
    "Tv show"
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
    "Urdu"
]

PLATFORMS = [
    "Netflix",
    "Prime Video",
    "Amazon Prime Video",
    "Amazon",
    "Jio Hotstar",
    "JioHotstar",
    "Disney+ Hotstar",
    "Hotstar",
    "Jio Cinema",
    "JioCinema",
    "Sony LIV",
    "SonyLIV",
    "ZEE5",
    "Zee5",
    "Aha Video",
    "aha",
    "MX Player",
    "Apple TV+",
    "Apple TV",
    "Sun NXT",
    "Hoichoi",
    "Lionsgate Play",
    "Discovery+",
    "Discovery Plus",
    "YouTube",
    "Voot",
    "ALT Balaji",
    "Shemaroo Me",
    "Chaupal",
    "Manorama MAX",
    "Saina Play",
    "ETV Win",
    "Mubi",
    "Airtel Xstream",
    "Crunchyroll",
    "Tubi",
    "Viki",
    "Viu",
    "Tata Sky",
    "Simply South",
    "Tentkotta"
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
    "Western"
]


# ============================================================
# TEXT HELPERS
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
        value.lower()
    )


def parse_date(value):

    if not value:
        return None

    match = re.search(
        r"\b(\d{1,2})\s+"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+(\d{4})\b",
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


def find_rating(text):

    for rating in RATINGS:

        if re.search(
            rf"\b{re.escape(rating)}\b",
            text,
            re.IGNORECASE
        ):

            return rating

    return None


def find_date(text):

    match = re.search(
        r"\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}\b",
        text,
        re.IGNORECASE
    )

    if match:

        return match.group(0)

    return None


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

    return None


def find_language(text):

    found = []

    for language in LANGUAGES:

        if re.search(
            rf"\b{re.escape(language)}\b",
            text,
            re.IGNORECASE
        ):

            if language not in found:

                found.append(
                    language
                )

    return ", ".join(found)


def find_platform(text):

    platforms = sorted(
        PLATFORMS,
        key=len,
        reverse=True
    )

    for platform in platforms:

        if re.search(
            rf"\b{re.escape(platform)}\b",
            text,
            re.IGNORECASE
        ):

            return platform

    return None


def find_genres(text):

    found = []

    for genre in GENRES:

        if re.search(
            rf"\b{re.escape(genre)}\b",
            text,
            re.IGNORECASE
        ):

            if genre not in found:

                found.append(
                    genre
                )

    return ", ".join(found)


# ============================================================
# NORMALIZE PLATFORM
# ============================================================

def normalize_platform(platform):

    if not platform:
        return None

    lower = platform.lower()

    if lower in [
        "hotstar",
        "jio hotstar",
        "jiohotstar",
        "disney+ hotstar"
    ]:

        return "Jio Hotstar"

    if lower in [
        "amazon",
        "amazon prime video"
    ]:

        return "Prime Video"

    if lower == "zee5":

        return "ZEE5"

    if lower == "sony liv":

        return "Sony LIV"

    if lower == "aha video":

        return "aha"

    return platform


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):

    title = clean_text(
        title
    )

    if not title:
        return ""

    # Remove accidental rating suffix.
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

    # Remove accidental type suffix.
    title = re.sub(
        r"\s+(?:Film|TV\s*Show)$",
        "",
        title,
        flags=re.IGNORECASE
    )

    return clean_text(
        title
    )


# ============================================================
# PLATFORM FROM LISTING CARD
# ============================================================

def extract_platform_from_element(
    element
):

    # 1. Images / logos.
    for img in element.find_all("img"):

        values = [
            img.get("alt"),
            img.get("title"),
            img.get("data-title"),
            img.get("aria-label")
        ]

        for value in values:

            value = clean_text(
                value
            )

            if not value:
                continue

            platform = find_platform(
                value
            )

            if platform:

                return normalize_platform(
                    platform
                )

    # 2. Links / labels.
    for tag in element.find_all(
        ["a", "span", "div"]
    ):

        values = [
            tag.get_text(
                " ",
                strip=True
            ),
            tag.get("title"),
            tag.get("aria-label")
        ]

        for value in values:

            value = clean_text(
                value
            )

            if not value:
                continue

            platform = find_platform(
                value
            )

            if platform:

                return normalize_platform(
                    platform
                )

    # 3. HTML attributes.
    for tag in element.find_all(True):

        for value in tag.attrs.values():

            if isinstance(
                value,
                list
            ):

                value = " ".join(
                    str(x)
                    for x in value
                )

            if not isinstance(
                value,
                str
            ):

                continue

            platform = find_platform(
                value
            )

            if platform:

                return normalize_platform(
                    platform
                )

    return None


# ============================================================
# TITLE LINK
# ============================================================

def find_title_link(
    element
):

    candidates = []

    for a in element.find_all(
        "a",
        href=True
    ):

        raw_text = clean_text(
            a.get_text(
                " ",
                strip=True
            )
        )

        href = a.get(
            "href"
        )

        if not raw_text or not href:
            continue

        title = clean_title(
            raw_text
        )

        if len(title) < 2:
            continue

        if len(title) > 150:
            continue

        lower = title.lower()

        if lower in [
            x.lower()
            for x in RATINGS
        ]:

            continue

        if lower in [
            x.lower()
            for x in TYPE_VALUES
        ]:

            continue

        if lower in [
            x.lower()
            for x in LANGUAGES
        ]:

            continue

        if lower in [
            x.lower()
            for x in PLATFORMS
        ]:

            continue

        if lower in [
            "view all",
            "read more",
            "streaming dates",
            "home",
            "reviews",
            "news",
            "ranked lists"
        ]:

            continue

        candidates.append(
            (
                title,
                href
            )
        )

    if not candidates:

        return None, None

    # Prefer Binged content/detail URLs.
    for title, href in candidates:

        href_lower = href.lower()

        if (
            "binged.com" in href_lower
            and (
                "/streaming-premiere-dates/"
                in href_lower
                or "/movie/" in href_lower
                or "/tv-show/" in href_lower
                or "/web-series/" in href_lower
            )
        ):

            return title, href

    return candidates[0]


# ============================================================
# PARSE BINGED LIST
# ============================================================

def parse_cards(html):

    print(
        "Parsing Binged release cards..."
    )

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
            "div",
            "li",
            "tr"
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

        if not date_pattern.search(
            text
        ):

            continue

        if not rating_pattern.search(
            text
        ):

            continue

        candidates.append(
            (
                element,
                text
            )
        )

    # Smallest useful containers first.
    candidates.sort(
        key=lambda x: len(x[1])
    )

    cards = []

    used_titles = set()

    for element, text in candidates:

        rating = find_rating(
            text
        )

        release_date = find_date(
            text
        )

        media_type = find_type(
            text
        )

        if not rating or not release_date:

            continue

        title, binged_link = find_title_link(
            element
        )

        if not title:

            continue

        title = clean_title(
            title
        )

        if not title:

            continue

        title_key = normal_key(
            title
        )

        if not title_key:

            continue

        if title_key in used_titles:

            continue

        if title.lower() in [
            "title",
            "stream date",
            "streaming platform",
            "search",
            "filters"
        ]:

            continue

        # ----------------------------------------------------
        # Metadata
        # ----------------------------------------------------

        platform = extract_platform_from_element(
            element
        )

        language = find_language(
            text
        )

        genres = find_genres(
            text
        )

        # ----------------------------------------------------
        # Normalize Binged link.
        # ----------------------------------------------------

        if binged_link:

            if binged_link.startswith(
                "/"
            ):

                binged_link = (
                    "https://www.binged.com"
                    + binged_link
                )

            elif binged_link.startswith(
                "//"
            ):

                binged_link = (
                    "https:"
                    + binged_link
                )

            elif binged_link.startswith(
                "http://"
            ):

                binged_link = binged_link.replace(
                    "http://",
                    "https://",
                    1
                )

        if not binged_link:

            binged_link = BINGED_URL

        date_object = parse_date(
            release_date
        )

        used_titles.add(
            title_key
        )

        cards.append(
            {
                "title": title,
                "rating": rating,
                "date": release_date,
                "date_object": date_object,
                "type": media_type or "Not listed",
                "genre": genres or "Not listed",
                "language": language or "Not listed",
                "platform": platform or "Not listed",
                "binged_link": binged_link
            }
        )

    # ========================================================
    # NEWEST → OLDEST
    # ========================================================

    cards.sort(
        key=lambda card: (
            card["date_object"]
            or datetime.min
        ),
        reverse=True
    )

    print(
        f"Parsed release cards: "
        f"{len(cards)}"
    )

    return cards


# ============================================================
# STREMIO + TELEGRAM BUTTONS + MESSAGE
# ============================================================

def stremio_app_link(title):
    """
    Native Stremio Android/Desktop deep link.
    This is displayed as text because Telegram URL buttons
    require a supported URL scheme.
    """
    return (
        "stremio:///search?search="
        + quote(title, safe="")
    )


def stremio_web_link(title):
    """
    Stremio Web search.
    This is used for the clickable Telegram button.
    """
    return (
        "https://web.stremio.com/"
        "#/search?search="
        + quote(title, safe="")
    )


def make_keyboard(card):

    title = card["title"]

    return {
        "inline_keyboard": [
            [
                {
                    "text": "▶ Open Stremio",
                    "url": (
                        "https://web.stremio.com/"
                        "#/search?search="
                        + quote(title, safe="")
                    )
                }
            ],
            [
                {
                    "text": "🔗 Open on Binged",
                    "url": card["binged_link"]
                }
            ]
        ]
    }

def make_message(card):

    app_link = stremio_app_link(
        card["title"]
    )

    return (
        f"🎬 {card['title']}\n"
        f"⭐ Rating: {card['rating']}\n"
        f"📅 Release: {card['date']}\n"
        f"🎞 Type: {card['type']}\n"
        f"🎭 Genre: {card['genre']}\n"
        f"🗣 Language: {card['language']}\n"
        f"📺 Platform: {card['platform']}\n\n"     
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
        ) as f:

            data = json.load(
                f
            )

        return set(
            data
        )

    except Exception:

        return set()


def save_seen(
    seen
):

    with open(
        SEEN_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            sorted(seen),
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# TELEGRAM /latest
# ============================================================

def get_latest_command():

    try:

        data = telegram_api(
            "getUpdates",
            {
                "limit": 20,
                "timeout": 0,
                "allowed_updates": [
                    "message"
                ]
            }
        )

    except Exception as e:

        print(
            f"Telegram getUpdates error: "
            f"{e}"
        )

        return None

    updates = data.get(
        "result",
        []
    )

    if not updates:

        return None

    latest_command = None

    now = int(
        time.time()
    )

    for update in updates:

        message = update.get(
            "message"
        )

        if not message:

            continue

        text = (
            message.get(
                "text"
            )
            or ""
        ).strip()

        command = text.lower()

        if not (
            command == "/latest"
            or command.startswith(
                "/latest@"
            )
        ):

            continue

        message_date = message.get(
            "date",
            0
        )

        if (
            now - message_date
            > COMMAND_MAX_AGE_SECONDS
        ):

            continue

        latest_command = message

    return latest_command


# ============================================================
# /latest
# ============================================================

def handle_latest(
    message
):

    chat_id = message[
        "chat"
    ][
        "id"
    ]

    print(
        f"/latest requested by "
        f"chat {chat_id}"
    )

    try:

        send_message(
            chat_id,
            "🔄 Fetching latest filtered Binged releases..."
        )

        html = fetch_binged()

        cards = parse_cards(
            html
        )

        if not cards:

            send_message(
                chat_id,
                "❌ Binged was reached, but no "
                "release cards could be extracted."
            )

            return

        for card in cards:

            send_message(
                chat_id,
                make_message(
                    card
                ),
                make_keyboard(
                    card
                )
            )

            time.sleep(
                0.2
            )

        send_message(
            chat_id,
            f"✅ Latest filtered list: "
            f"{len(cards)} title(s), "
            f"sorted newest → oldest."
        )

    except Exception as e:

        print(
            f"/latest error: "
            f"{e}"
        )

        send_message(
            chat_id,
            "❌ Could not fetch Binged.\n\n"
            f"Error: {str(e)[:500]}"
        )


# ============================================================
# AUTOMATIC UPDATES
# ============================================================

def automatic_update():

    print(
        "Checking Binged for new releases..."
    )

    seen = load_seen()

    html = fetch_binged()

    cards = parse_cards(
        html
    )

    if not cards:

        print(
            "No cards extracted. "
            "Automatic notification skipped."
        )

        return

    new_count = 0

    for card in cards:

        title_key = normal_key(
            card["title"]
        )

        if not title_key:

            continue

        if title_key in seen:

            continue

        print(
            f"New title: "
            f"{card['title']} "
            f"| {card['date']}"
        )

        try:

            send_message(
                TELEGRAM_CHAT_ID,
                make_message(
                    card
                ),
                make_keyboard(
                    card
                )
            )

            seen.add(
                title_key
            )

            new_count += 1

        except Exception as e:

            print(
                f"Telegram send failed: "
                f"{e}"
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

    # Check for /latest first.
    command = get_latest_command()

    if command:

        handle_latest(
            command
        )

        return

    # Otherwise automatic update.
    automatic_update()


if __name__ == "__main__":

    run()
