import os
import re
import json
import time
import requests

from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
from datetime import datetime


# ============================================================
# BINGED CONFIGURATION
# ============================================================

BINGED_BASE = (
    "https://www.binged.com/streaming-premiere-dates/"
)

# /latest uses this URL.
# It deliberately requests all six recommendation categories
# on the first page only.

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
# CATEGORY URLS
# ============================================================

CATEGORY_VALUES = {
    "mustwatch": "Must_Watch",
    "good": "Good",
    "satisfactory": "Satisfactory",
    "passable": "Passable",
    "poor": "Poor",
    "skip": "Skip",
}


def make_category_url(category):

    binged_category = CATEGORY_VALUES[category]

    return (
        BINGED_BASE
        + "?category%5B%5D=Film"
        + "&category%5B%5D=Tv%20show"
        + "&language%5B%5D=Hindi"
        + "&language%5B%5D=Punjabi"
        + "&mode=streaming-now"
        + "&recommendation%5B%5D="
        + binged_category
    )


# ============================================================
# SECRETS
# ============================================================

SCRAPER_API_KEY = os.environ.get(
    "SCRAPER_API_KEY"
)

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID"
)

SEEN_FILE = "seen_titles.json"


# ============================================================
# SETTINGS
# ============================================================

# Category commands can follow pagination.
# This is a safety limit so a pagination problem cannot
# consume unlimited ScraperAPI requests.

MAX_CATEGORY_PAGES = 20

# Small delay between category-page requests.

PAGE_DELAY_SECONDS = 2

# Telegram command age.
# This prevents an old /latest command from being executed
# again on a later scheduled GitHub Actions run.

COMMAND_MAX_AGE_SECONDS = 10 * 60


# ============================================================
# RATINGS / LANGUAGES / GENRES
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

    return None


def find_date(text):

    match = re.search(
        r"\b"
        r"\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}"
        r"\b",
        text,
        re.IGNORECASE,
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

    return ", ".join(found) or "Not listed"


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

    return ", ".join(found) or "Not listed"


# ============================================================
# PLATFORM EXTRACTION
# ============================================================

def find_platform(text):

    if not text:
        return None

    normalized = str(text)

    normalized = normalized.replace(
        "\\/",
        "/"
    )

    normalized = re.sub(
        r"[-_+/]+",
        " ",
        normalized
    )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized
    ).strip().lower()

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
        key=lambda item: len(item[0]),
        reverse=True
    )

    for alias, display_name in platforms:

        if alias in normalized:

            return display_name

    return None


def extract_platform(element):

    if not element:
        return None

    # Search the entire HTML first.
    platform = find_platform(
        str(element)
    )

    if platform:

        return platform

    values = []

    # Visible text.
    values.append(
        element.get_text(
            " ",
            strip=True
        )
    )

    # Attributes frequently used by logos.
    attributes = [
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

    return None


# ============================================================
# TITLE EXTRACTION
# ============================================================

def clean_title(title):

    title = clean_text(
        title
    )

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

    return clean_text(
        title
    )


def find_title_link(element):

    candidates = []

    for anchor in element.find_all(
        "a",
        href=True
    ):

        raw_text = clean_text(
            anchor.get_text(
                " ",
                strip=True
            )
        )

        href = anchor.get(
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

        if lower in excluded:

            continue

        if lower in [
            rating.lower()
            for rating in RATINGS
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

    # Prefer actual Binged title pages.
    for title, href in candidates:

        href_lower = href.lower()

        if (
            "binged.com" in href_lower
            and (
                "/streaming-premiere-dates/"
                in href_lower
                or "/movie/"
                in href_lower
                or "/tv-show/"
                in href_lower
                or "/web-series/"
                in href_lower
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
        r"\b"
        r"\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+\d{4}"
        r"\b",
        re.IGNORECASE
    )

    rating_pattern = re.compile(
        r"\b"
        r"(?:Must Watch|Good|Satisfactory|Passable|Poor|Skip)"
        r"\b",
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
            (
                element,
                text
            )
        )

    # Smallest matching containers first.
    candidates.sort(
        key=lambda item: len(item[1])
    )

    cards = []

    used = set()

    for element, text in candidates:

        rating = find_rating(
            text
        )

        release_date = find_date(
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

        if title_key in used:

            continue

        platform = extract_platform(
            element
        )

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
            "platform": (
                platform
                or "Not listed"
            ),
            "binged_link": (
                urljoin(
                    BINGED_BASE,
                    binged_link
                )
                if binged_link
                else BINGED_BASE
            ),
        }

        cards.append(
            card
        )

        used.add(
            title_key
        )

    print(
        f"Extracted {len(cards)} title(s)"
    )

    return cards


# ============================================================
# NEXT PAGE DETECTION
# ============================================================

def find_next_page(
    html,
    current_url
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # --------------------------------------------------------
    # rel="next"
    # --------------------------------------------------------

    for anchor in soup.find_all(
        "a",
        href=True
    ):

        rel = anchor.get(
            "rel"
        )

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

    # --------------------------------------------------------
    # Visible Next button/link.
    # --------------------------------------------------------

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
                ]

                for phrase in blocked:

                    if phrase in lower:

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

            last_error = str(
                exc
            )

            print(
                f"Attempt failed: {exc}"
            )

        if attempt < attempts:

            wait = attempt * 8

            print(
                f"Retrying in {wait} seconds..."
            )

            time.sleep(
                wait
            )

    raise RuntimeError(
        last_error
        or "Could not fetch Binged."
    )


# ============================================================
# LATEST = ONE PAGE ONLY
# ============================================================

def fetch_latest():

    print(
        "Fetching latest Binged page..."
    )

    print(
        BINGED_LATEST_URL
    )

    html = fetch_binged(
        BINGED_LATEST_URL
    )

    cards = parse_cards(
        html
    )

    # Newest first.
    cards.sort(
        key=lambda card: (
            card["date_object"]
            or datetime.min
        ),
        reverse=True
    )

    return cards


# ============================================================
# CATEGORY = ALL PAGES
# ============================================================

def fetch_category_all_pages(
    category
):

    if category not in CATEGORY_VALUES:

        raise ValueError(
            f"Unknown category: {category}"
        )

    first_url = make_category_url(
        category
    )

    print("")
    print(
        "========================================"
    )
    print(
        f"FETCHING ALL: {category.upper()}"
    )
    print(
        "========================================"
    )

    print(
        first_url
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

        visited.add(
            current_url
        )

        print(
            f"Fetching category page "
            f"{page_number}..."
        )

        html = fetch_binged(
            current_url
        )

        page_cards = parse_cards(
            html
        )

        print(
            f"Page {page_number}: "
            f"{len(page_cards)} title(s)"
        )

        all_cards.extend(
            page_cards
        )

        next_url = find_next_page(
            html,
            current_url
        )

        if not next_url:

            print(
                "No next page."
            )

            break

        current_url = next_url

        time.sleep(
            PAGE_DELAY_SECONDS
        )

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Newest first
    # --------------------------------------------------------

    cards.sort(
        key=lambda card: (
            card["date_object"]
            or datetime.min
        ),
        reverse=True
    )

    print(
        f"Total unique "
        f"{category} titles: "
        f"{len(cards)}"
    )

    return cards


# ============================================================
# STREMIO
# ============================================================

def stremio_web_link(
    title
):

    return (
        "https://web.stremio.com/"
        "#/search?search="
        + quote(
            title,
            safe=""
        )
    )


# ============================================================
# TELEGRAM BUTTONS
# ============================================================

def make_keyboard(
    card
):

    return {
        "inline_keyboard": [

            [
                {
                    "text": "▶ Open Stremio",
                    "url": stremio_web_link(
                        card["title"]
                    )
                }
            ],

            [
                {
                    "text": "🔗 Open on Binged",
                    "url": card[
                        "binged_link"
                    ]
                }
            ],

        ]
    }


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def make_message(
    card
):

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
            f"Could not read "
            f"{SEEN_FILE}: {exc}"
        )

    return set()


def save_seen(
    seen
):

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
# TELEGRAM COMMANDS
# ============================================================

COMMANDS = {
    "/latest": None,
    "/mustwatch": "mustwatch",
    "/good": "good",
    "/satisfactory": "satisfactory",
    "/passable": "passable",
    "/poor": "poor",
    "/skip": "skip",
}


def get_recent_command():

    try:

        result = telegram_request(
            "getUpdates",
            {
                "limit": 20,
                "timeout": 0,
                "allowed_updates": [
                    "message"
                ],
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
                ""
            )
        )

        if not text:

            continue

        command = text.lower()

        # Ignore bot username suffix:
        # /latest@MyBot
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

        if (
            now - message_date
            > COMMAND_MAX_AGE_SECONDS
        ):

            continue

        latest = message

    return latest


# ============================================================
# SEND CARD LIST
# ============================================================

def send_cards(
    chat_id,
    cards,
    heading=None
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

    for card in cards:

        send_telegram(
            chat_id,
            make_message(card),
            make_keyboard(card)
        )

        # Avoid hitting Telegram too aggressively.
        time.sleep(
            0.15
        )

    send_telegram(
        chat_id,
        f"✅ {len(cards)} title(s) found."
    )


# ============================================================
# HANDLE /latest
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
        f"/latest requested "
        f"by {chat_id}"
    )

    send_telegram(
        chat_id,
        "🔄 Fetching latest filtered Binged page..."
    )

    cards = fetch_latest()

    send_cards(
        chat_id,
        cards,
        "🎬 LATEST — FILTERED BINGED RESULTS"
    )


# ============================================================
# HANDLE CATEGORY COMMAND
# ============================================================

def handle_category(
    message,
    category
):

    chat_id = message[
        "chat"
    ][
        "id"
    ]

    display_name = category.replace(
        "mustwatch",
        "Must Watch"
    ).replace(
        "satisfactory",
        "Satisfactory"
    ).replace(
        "passable",
        "Passable"
    ).replace(
        "good",
        "Good"
    ).replace(
        "poor",
        "Poor"
    ).replace(
        "skip",
        "Skip"
    )

    print(
        f"/{category} requested "
        f"by {chat_id}"
    )

    send_telegram(
        chat_id,
        f"🔄 Fetching ALL {display_name} "
        f"pages from Binged..."
    )

    cards = fetch_category_all_pages(
        category
    )

    # Make absolutely sure this command
    # only returns the requested rating.
    cards = [
        card
        for card in cards
        if card["rating"].lower()
        == display_name.lower()
    ]

    send_cards(
        chat_id,
        cards,
        f"🎬 {display_name.upper()} — ALL BINGED RESULTS"
    )


# ============================================================
# AUTOMATIC HOURLY NOTIFICATION
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
            f"{card['title']}"
        )

        send_telegram(
            TELEGRAM_CHAT_ID,
            make_message(card),
            make_keyboard(card)
        )

        seen.add(
            title_key
        )

        new_count += 1

        time.sleep(
            0.15
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
    # Check whether the Telegram user requested a command.
    # --------------------------------------------------------

    command_message = get_recent_command()

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

        if command == "/latest":

            handle_latest(
                command_message
            )

            return

        if command in COMMANDS:

            category = COMMANDS[
                command
            ]

            if category:

                handle_category(
                    command_message,
                    category
                )

                return

    # --------------------------------------------------------
    # No command = scheduled automatic check.
    # --------------------------------------------------------

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
