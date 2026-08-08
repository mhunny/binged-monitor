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

# Only commands received within this period are considered.
COMMAND_MAX_AGE_SECONDS = 10 * 60


# ============================================================
# TELEGRAM
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

    bad_text = html[:15000].lower()

    if "access denied" in bad_text:
        raise RuntimeError(
            "Binged returned Access Denied."
        )

    if "<title>forbidden</title>" in bad_text:
        raise RuntimeError(
            "Binged returned Forbidden."
        )

    if "verify you are human" in bad_text:
        raise RuntimeError(
            "Binged returned a verification challenge."
        )

    return html


# ============================================================
# TEXT HELPERS
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
    "JioHotstar",
    "Disney+ Hotstar",
    "Jio Cinema",
    "JioCinema",
    "Sony LIV",
    "SonyLIV",
    "ZEE5",
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
    "Tata Sky"
]


def clean_text(value):

    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        value
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

    for platform in PLATFORMS:

        if re.search(
            rf"\b{re.escape(platform)}\b",
            text,
            re.IGNORECASE
        ):

            return platform

    return None


# ============================================================
# CARD PARSER
# ============================================================

def parse_cards(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    cards = []

    # --------------------------------------------------------
    # First attempt:
    # identify repeated containers containing a release date.
    # --------------------------------------------------------

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
        ["div", "article", "li", "tr"]
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

    # --------------------------------------------------------
    # Prefer the smallest useful containers.
    # --------------------------------------------------------

    candidates.sort(
        key=lambda item: len(item[1])
    )

    used_titles = set()

    for element, text in candidates:

        rating = find_rating(text)
        release_date = find_date(text)
        media_type = find_type(text)
        language = find_language(text)
        platform = find_platform(text)

        if not rating or not release_date:
            continue

        # ----------------------------------------------------
        # Extract links from this candidate.
        # Binged title cards normally contain a title link.
        # ----------------------------------------------------

        links = []

        for a in element.find_all(
            "a",
            href=True
        ):

            title_text = clean_text(
                a.get_text(
                    " ",
                    strip=True
                )
            )

            href = a.get("href")

            if not title_text:
                continue

            if not href:
                continue

            if len(title_text) > 150:
                continue

            if title_text.lower() in [
                x.lower()
                for x in RATINGS
            ]:
                continue

            if is_date(title_text):
                continue

            links.append(
                (
                    title_text,
                    href
                )
            )

        # ----------------------------------------------------
        # Choose likely title.
        # ----------------------------------------------------

        title = None
        binged_link = None

        for title_text, href in links:

            lower = title_text.lower()

            if lower in [
                "view all",
                "read more",
                "streaming dates"
            ]:
                continue

            if lower in [
                x.lower()
                for x in PLATFORMS
            ]:
                continue

            if lower in [
                x.lower()
                for x in LANGUAGES
            ]:
                continue

            if lower in [
                x.lower()
                for x in RATINGS
            ]:
                continue

            if lower in [
                "film",
                "tv show"
            ]:
                continue

            # Avoid navigation/header links.
            if len(title_text) < 2:
                continue

            title = title_text
            binged_link = href
            break

        if not title:

            # Fallback: inspect text lines.
            lines = [
                clean_text(x)
                for x in element.get_text(
                    "\n",
                    strip=True
                ).splitlines()
            ]

            for line in lines:

                if not line:
                    continue

                if is_date(line):
                    continue

                if line.lower() in [
                    x.lower()
                    for x in RATINGS
                ]:
                    continue

                if line.lower() in [
                    x.lower()
                    for x in TYPE_VALUES
                ]:
                    continue

                if line.lower() in [
                    x.lower()
                    for x in LANGUAGES
                ]:
                    continue

                if line.lower() in [
                    x.lower()
                    for x in PLATFORMS
                ]:
                    continue

                if len(line) >= 2 and len(line) <= 150:
                    title = line
                    break

        if not title:
            continue

        title_key = normal_key(title)

        if not title_key:
            continue

        if title_key in used_titles:
            continue

        used_titles.add(title_key)

        # ----------------------------------------------------
        # Genre
        # ----------------------------------------------------

        genre = find_genre(
            element,
            title,
            rating,
            release_date,
            media_type,
            language,
            platform
        )

        if binged_link:

            if binged_link.startswith("/"):
                binged_link = (
                    "https://www.binged.com"
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

        cards.append(
            {
                "title": title,
                "rating": rating,
                "date": release_date,
                "type": media_type or "Not listed",
                "genre": genre or "Not listed",
                "language": language or "Not listed",
                "platform": platform or "Not listed",
                "binged_link": binged_link or BINGED_URL
            }
        )

    print(
        f"Parsed release cards: {len(cards)}"
    )

    return cards


def find_genre(
    element,
    title,
    rating,
    release_date,
    media_type,
    language,
    platform
):

    possible = []

    genre_words = [
        "Action",
        "Adventure",
        "Animation",
        "Biography",
        "Comedy",
        "Crime",
        "Drama",
        "Family",
        "Fantasy",
        "Horror",
        "Kids",
        "Music",
        "Musical",
        "Mystery",
        "Romance",
        "Sci-Fi",
        "Social",
        "Sports",
        "Thriller",
        "War",
        "Western"
    ]

    text = clean_text(
        element.get_text(
            " ",
            strip=True
        )
    )

    for genre in genre_words:

        if re.search(
            rf"\b{re.escape(genre)}\b",
            text,
            re.IGNORECASE
        ):

            if genre not in possible:
                possible.append(genre)

    # Don't return one generic genre if there are none.
    return ", ".join(possible)


# ============================================================
# FORMAT MESSAGE
# ============================================================

def make_message(card):

    title = card["title"]

    stremio_link = (
        "https://stremio.app/#/search?search="
        + quote(title)
    )

    return (
        f"🎬 {title}\n\n"
        f"⭐ Rating: {card['rating']}\n"
        f"📅 Release: {card['date']}\n"
        f"🎞 Type: {card['type']}\n"
        f"🎭 Genre: {card['genre']}\n"
        f"🗣 Language: {card['language']}\n"
        f"📺 Platform: {card['platform']}\n\n"
        f"▶ Open in Stremio:\n"
        f"{stremio_link}\n\n"
        f"🔗 Binged:\n"
        f"{card['binged_link']}"
    )


# ============================================================
# SEEN LIST
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
# GET /latest COMMAND
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

    now = int(time.time())

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

        if not text.lower().startswith(
            "/latest"
        ):
            continue

        message_date = message.get(
            "date",
            0
        )

        # Ignore old commands.
        if now - message_date > COMMAND_MAX_AGE_SECONDS:
            continue

        latest_command = message

    return latest_command


# ============================================================
# HANDLE /latest
# ============================================================

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
                "❌ Binged was reached, but I could not "
                "identify the release cards."
            )

            return

        # Limit Telegram response size.
        # Send individual messages instead of one huge message.
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
            f"❌ Could not fetch Binged.\n\n"
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

        message = make_message(card)

        print(
            f"New title: {card['title']}"
        )

        try:

            send_message(
                TELEGRAM_CHAT_ID,
                message
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

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN secret is missing."
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID secret is missing."
        )

    # --------------------------------------------------------
    # FIRST: check for /latest command.
    # --------------------------------------------------------

    command = get_latest_command()

    if command:

        handle_latest(command)

        # Do not also perform automatic scraping
        # in the same run.
        return

    # --------------------------------------------------------
    # OTHERWISE: automatic update check.
    # --------------------------------------------------------

    automatic_update()


if __name__ == "__main__":
    run()
