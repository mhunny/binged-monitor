import os
import re
import json
import time
import requests

from bs4 import BeautifulSoup
from urllib.parse import quote


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


def send_message(chat_id, text):

    telegram_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True
        }
    )


# ============================================================
# BINGED FETCH
# ============================================================

def fetch_binged():

    if not SCRAPER_API_KEY:
        raise RuntimeError(
            "SCRAPER_API_KEY secret is missing."
        )

    print("Fetching Binged through ScraperAPI...")

    response = requests.get(
        "https://api.scraperapi.com/",
        params={
            "api_key": SCRAPER_API_KEY,
            "url": BINGED_URL,
            "render": "true"
        },
        timeout=120
    )

    print(
        f"ScraperAPI HTTP status: "
        f"{response.status_code}"
    )

    print(
        f"Returned HTML length: "
        f"{len(response.text)}"
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"ScraperAPI returned HTTP "
            f"{response.status_code}"
        )

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
                f"Binged returned a blocked/verification page: "
                f"{phrase}"
            )

    return html


# ============================================================
# HELPERS
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
    "JioHotstar",
    "Disney+ Hotstar",
    "Jio Cinema",
    "JioCinema",
    "Sony LIV",
    "SonyLIV",
    "ZEE5",
    "Zee5",
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
    "Tata Sky",
    "Mubi",
    "Aha Video",
    "Airtel Xstream",
    "Jio Hotstar"
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


def is_date(value):

    return bool(
        re.search(
            r"\b\d{1,2}\s+"
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+\d{4}\b",
            value,
            re.IGNORECASE
        )
    )


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
                found.append(language)

    return ", ".join(found)


def find_platform(text):

    # Long names first.
    sorted_platforms = sorted(
        PLATFORMS,
        key=len,
        reverse=True
    )

    for platform in sorted_platforms:

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
                found.append(genre)

    return ", ".join(found)


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):

    title = clean_text(title)

    if not title:
        return ""

    # Remove trailing rating accidentally included
    # in the title link.
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

    # Remove trailing media type if accidentally included.
    title = re.sub(
        r"\s+(?:Film|TV\s*Show)$",
        "",
        title,
        flags=re.IGNORECASE
    )

    # Remove duplicate whitespace.
    title = clean_text(title)

    return title


# ============================================================
# PLATFORM EXTRACTION
# ============================================================

def extract_platform_from_element(element):

    # 1. Look at image alt/title attributes.
    for img in element.find_all("img"):

        values = [
            img.get("alt"),
            img.get("title"),
            img.get("data-title"),
            img.get("aria-label")
        ]

        for value in values:

            value = clean_text(value)

            if not value:
                continue

            platform = find_platform(value)

            if platform:
                return platform

    # 2. Look at links.
    for link in element.find_all("a"):

        values = [
            link.get_text(
                " ",
                strip=True
            ),
            link.get("title"),
            link.get("aria-label")
        ]

        for value in values:

            value = clean_text(value)

            platform = find_platform(value)

            if platform:
                return platform

    # 3. Look at all HTML attributes.
    for tag in element.find_all(True):

        for value in tag.attrs.values():

            if isinstance(value, list):
                value = " ".join(
                    str(x)
                    for x in value
                )

            if not isinstance(value, str):
                continue

            platform = find_platform(value)

            if platform:
                return platform

    return None


# ============================================================
# TITLE LINK EXTRACTION
# ============================================================

def find_title_link(element):

    candidates = []

    for a in element.find_all(
        "a",
        href=True
    ):

        text = clean_text(
            a.get_text(
                " ",
                strip=True
            )
        )

        href = a.get("href")

        if not text:
            continue

        if not href:
            continue

        cleaned = clean_title(text)

        if not cleaned:
            continue

        if len(cleaned) < 2:
            continue

        if len(cleaned) > 150:
            continue

        if cleaned.lower() in [
            x.lower()
            for x in RATINGS
        ]:
            continue

        if cleaned.lower() in [
            x.lower()
            for x in TYPE_VALUES
        ]:
            continue

        if cleaned.lower() in [
            x.lower()
            for x in LANGUAGES
        ]:
            continue

        if cleaned.lower() in [
            x.lower()
            for x in PLATFORMS
        ]:
            continue

        if cleaned.lower() in [
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
                cleaned,
                href
            )
        )

    if not candidates:
        return None, None

    # Prefer links that look like Binged title/detail URLs.
    for title, href in candidates:

        href_lower = href.lower()

        if (
            "binged.com" in href_lower
            and (
                "/movie" in href_lower
                or "/series" in href_lower
                or "/web-series" in href_lower
                or "/streaming" in href_lower
            )
        ):

            return title, href

    # Otherwise first reasonable title.
    return candidates[0]


# ============================================================
# CARD PARSER
# ============================================================

def parse_cards(html):

    print("Parsing Binged release cards...")

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
        ["article", "div", "li", "tr"]
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
            (
                element,
                text
            )
        )

    # Smallest containers first.
    candidates.sort(
        key=lambda x: len(x[1])
    )

    cards = []
    used_titles = set()

    for element, text in candidates:

        rating = find_rating(text)

        release_date = find_date(text)

        media_type = find_type(text)

        if not rating or not release_date:
            continue

        title, binged_link = find_title_link(
            element
        )

        if not title:
            continue

        title = clean_title(title)

        if not title:
            continue

        title_key = normal_key(title)

        if not title_key:
            continue

        if title_key in used_titles:
            continue

        # ----------------------------------------------------
        # Remove obvious accidental UI/title contamination.
        # ----------------------------------------------------

        if title.lower() in [
            "title",
            "stream date",
            "streaming platform",
            "search",
            "filters"
        ]:
            continue

        # ----------------------------------------------------
        # Extract metadata from the card.
        # ----------------------------------------------------

        platform = extract_platform_from_element(
            element
        )

        if not platform:
            platform = find_platform(text)

        language = find_language(text)

        genres = find_genres(text)

        # ----------------------------------------------------
        # Normalize Binged URL.
        # ----------------------------------------------------

        if binged_link:

            if binged_link.startswith("/"):
                binged_link = (
                    "https://www.binged.com"
                    + binged_link
                )

            elif binged_link.startswith("//"):
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

        used_titles.add(title_key)

        cards.append(
            {
                "title": title,
                "rating": rating,
                "date": release_date,
                "type": media_type or "Not listed",
                "genre": genres or "Not listed",
                "language": language or "Not listed",
                "platform": platform or "Not listed",
                "binged_link": binged_link
            }
        )

    print(
        f"Parsed release cards: {len(cards)}"
    )

    return cards


# ============================================================
# STREMIO LINKS
# ============================================================

def stremio_search_link(title):

    # Official Stremio search deep-link format.
    #
    # stremio:///search?search={query}
    #
    # This opens Stremio's search page and does not require
    # an IMDb ID.

    return (
        "stremio:///search?search="
        + quote(
            title,
            safe=""
        )
    )


def stremio_web_link(title):

    # Browser fallback.
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

    title = card["title"]

    app_link = stremio_search_link(
        title
    )

    web_link = stremio_web_link(
        title
    )

    return (
        f"🎬 {title}\n\n"
        f"⭐ Rating: {card['rating']}\n"
        f"📅 Release: {card['date']}\n"
        f"🎞 Type: {card['type']}\n"
        f"🎭 Genre: {card['genre']}\n"
        f"🗣 Language: {card['language']}\n"
        f"📺 Platform: {card['platform']}\n\n"
        f"▶ Open in Stremio App:\n"
        f"{app_link}\n\n"
        f"🌐 Open Stremio Web:\n"
        f"{web_link}\n\n"
        f"🔗 Binged:\n"
        f"{card['binged_link']}"
    )


# ============================================================
# SEEN TITLES
# ============================================================

def load_seen():

    if not os.path.exists(SEEN_FILE):
        return set()

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        return set(data)

    except Exception:
        return set()


def save_seen(seen):

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
# TELEGRAM /latest COMMAND
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
            f"Telegram getUpdates error: {e}"
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
            message.get("text")
            or ""
        ).strip()

        if not text:
            continue

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

        if now - message_date > COMMAND_MAX_AGE_SECONDS:
            continue

        latest_command = message

    return latest_command


def handle_latest(message):

    chat_id = message["chat"]["id"]

    print(
        f"/latest requested by chat {chat_id}"
    )

    try:

        send_message(
            chat_id,
            "🔄 Fetching the latest filtered Binged list..."
        )

        html = fetch_binged()

        cards = parse_cards(html)

        if not cards:

            send_message(
                chat_id,
                "❌ Binged was reached, but no release "
                "cards could be extracted."
            )

            return

        for card in cards:

            send_message(
                chat_id,
                make_message(card)
            )

            time.sleep(0.2)

        send_message(
            chat_id,
            f"✅ Current filtered list: "
            f"{len(cards)} title(s)."
        )

    except Exception as e:

        print(
            f"/latest error: {e}"
        )

        send_message(
            chat_id,
            "❌ Could not fetch the Binged list.\n\n"
            f"Error: {str(e)[:500]}"
        )


# ============================================================
# AUTOMATIC NEW TITLE NOTIFICATIONS
# ============================================================

def automatic_update():

    print(
        "Checking Binged for new releases..."
    )

    seen = load_seen()

    html = fetch_binged()

    cards = parse_cards(html)

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
            f"New title: {card['title']}"
        )

        try:

            send_message(
                TELEGRAM_CHAT_ID,
                make_message(card)
            )

            seen.add(title_key)

            new_count += 1

        except Exception as e:

            print(
                f"Telegram send failed: {e}"
            )

    save_seen(seen)

    print(
        f"New Telegram alerts: {new_count}"
    )

    print(
        f"Total seen titles: {len(seen)}"
    )


# ============================================================
# MAIN
# ============================================================

def run():

    print("")
    print("========================================")
    print("BINGED → TELEGRAM")
    print("========================================")

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

    # First check whether /latest was sent.
    command = get_latest_command()

    if command:

        handle_latest(command)

        return

    # Otherwise perform scheduled update.
    automatic_update()


if __name__ == "__main__":
    run()
