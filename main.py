import os
import re
import json
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# CONFIG
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

SEEN_FILE = "seen_titles.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is missing.")
        return False

    if not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_CHAT_ID is missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    import urllib.request
    import urllib.parse

    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": "false"
    }).encode("utf-8")

    try:
        request = urllib.request.Request(
            url,
            data=data,
            method="POST"
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            result = response.read().decode("utf-8")

        result_json = json.loads(result)

        if result_json.get("ok"):
            return True

        print("Telegram API error:")
        print(result)
        return False

    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# ============================================================
# SEEN TITLES
# ============================================================

def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return set(data)

    except Exception as e:
        print(f"Could not read seen list: {e}")
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, indent=2, ensure_ascii=False)


# ============================================================
# TEXT CLEANING
# ============================================================

RATINGS = [
    "Must Watch",
    "Satisfactory",
    "Passable",
    "Good",
    "Poor",
    "Skip"
]

TYPES = [
    "Film",
    "Tv show",
    "TV show",
    "TV Show"
]

KNOWN_PLATFORMS = [
    "Netflix",
    "Prime Video",
    "Amazon Prime Video",
    "Disney+ Hotstar",
    "JioHotstar",
    "JioCinema",
    "SonyLIV",
    "ZEE5",
    "aha",
    "MX Player",
    "MXPLAYER",
    "Apple TV+",
    "Apple TV",
    "Sun NXT",
    "Hoichoi",
    "Lionsgate Play",
    "Discovery+",
    "Discovery Plus",
    "Voot",
    "ALTBalaji",
    "ZEE5",
    "YouTube"
]

BAD_LINES = {
    "streaming now",
    "streaming soon",
    "today's releases",
    "this week's releases",
    "all",
    "search",
    "filters",
    "apply filters",
    "clear",
    "trending on binged",
    "binged",
}


def clean_line(line):
    line = re.sub(r"\s+", " ", line).strip()
    return line


def is_date(line):
    return bool(
        re.search(
            r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",
            line
        )
    )


def find_rating(lines):
    for rating in RATINGS:
        for line in lines:
            if line.strip().lower() == rating.lower():
                return rating
    return None


def find_type(lines):
    for line in lines:
        if line.strip().lower() in [x.lower() for x in TYPES]:
            return "TV Show" if line.lower() == "tv show" else "Film"
    return None


def find_date(lines):
    for line in lines:
        match = re.search(
            r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b",
            line
        )
        if match:
            return match.group(1)
    return None


def find_platform(lines):
    # First look for exact known platform names.
    for platform in KNOWN_PLATFORMS:
        for line in lines:
            if line.strip().lower() == platform.lower():
                return platform

    # Then look for common platform text.
    for line in lines:
        lower = line.lower()

        if "prime video" in lower:
            return "Prime Video"

        if "netflix" in lower:
            return "Netflix"

        if "hotstar" in lower:
            return "JioHotstar"

        if "sonyliv" in lower:
            return "SonyLIV"

        if "zee5" in lower:
            return "ZEE5"

        if lower == "aha":
            return "aha"

        if "mxplayer" in lower or "mx player" in lower:
            return "MX Player"

        if "apple tv" in lower:
            return "Apple TV+"

    return None


def find_language(lines):
    languages = [
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
        "Mandarin",
        "Korean",
        "Japanese"
    ]

    found = []

    for line in lines:
        parts = [
            x.strip()
            for x in re.split(r",|\||/", line)
        ]

        for part in parts:
            for language in languages:
                if part.lower() == language.lower():
                    if language not in found:
                        found.append(language)

    return ", ".join(found) if found else None


def find_genre(lines, title, date, rating, media_type, language, platform):
    excluded = {
        title.lower() if title else "",
        date.lower() if date else "",
        rating.lower() if rating else "",
        media_type.lower() if media_type else "",
        language.lower() if language else "",
        platform.lower() if platform else "",
    }

    excluded.update(BAD_LINES)

    possible = []

    for line in lines:
        value = line.strip()

        if not value:
            continue

        if value.lower() in excluded:
            continue

        if is_date(value):
            continue

        if value.lower() in [x.lower() for x in RATINGS]:
            continue

        if value.lower() in [x.lower() for x in TYPES]:
            continue

        # Do not treat obvious platform names as genre.
        if any(value.lower() == p.lower() for p in KNOWN_PLATFORMS):
            continue

        # Genres usually contain multiple comma-separated terms.
        if "," in value:
            possible.append(value)

    if possible:
        return possible[0]

    return None


# ============================================================
# CARD EXTRACTION
# ============================================================

def extract_cards(page):

    print("Searching rendered Binged page for release cards...")

    # We deliberately inspect the rendered DOM rather than making
    # a normal requests/curl request.
    candidates = page.evaluate("""
    () => {
        const dateRegex = /\\b\\d{1,2}\\s+[A-Za-z]{3,9}\\s+\\d{4}\\b/;
        const ratings = [
            "Must Watch",
            "Good",
            "Satisfactory",
            "Passable",
            "Poor",
            "Skip"
        ];

        const results = [];
        const seen = new Set();

        for (const el of document.querySelectorAll("*")) {

            const text = (el.innerText || "").trim();

            if (!text) continue;

            if (text.length < 30 || text.length > 1200) continue;

            if (!dateRegex.test(text)) continue;

            const hasRating = ratings.some(
                r => text.toLowerCase().includes(r.toLowerCase())
            );

            if (!hasRating) continue;

            let node = el;

            // Move upward until we find the likely release card.
            for (let level = 0; level < 8 && node; level++) {

                const candidate = (node.innerText || "").trim();

                if (
                    candidate.length >= 50 &&
                    candidate.length <= 900 &&
                    dateRegex.test(candidate)
                ) {

                    const key = candidate
                        .replace(/\\s+/g, " ")
                        .trim();

                    if (!seen.has(key)) {
                        seen.add(key);
                        results.push(key);
                    }

                    break;
                }

                node = node.parentElement;
            }
        }

        return results;
    }
    """)

    print(f"Raw card candidates found: {len(candidates)}")

    cards = []

    for raw in candidates:

        lines = [
            clean_line(x)
            for x in raw.splitlines()
        ]

        lines = [
            x for x in lines
            if x and x.lower() not in BAD_LINES
        ]

        # Remove duplicates while maintaining order.
        cleaned = []
        for line in lines:
            if line not in cleaned:
                cleaned.append(line)

        lines = cleaned

        rating = find_rating(lines)
        date = find_date(lines)
        media_type = find_type(lines)
        platform = find_platform(lines)
        language = find_language(lines)

        if not date or not rating or not media_type:
            continue

        # ----------------------------------------------------
        # Find title.
        # Usually it is the first useful line before rating.
        # ----------------------------------------------------

        title = None

        for line in lines:

            lower = line.lower()

            if is_date(line):
                continue

            if lower in [x.lower() for x in RATINGS]:
                continue

            if lower in [x.lower() for x in TYPES]:
                continue

            if platform and lower == platform.lower():
                continue

            if language and lower == language.lower():
                continue

            if lower in BAD_LINES:
                continue

            # Skip obvious UI/platform text.
            if lower in [
                "prime video",
                "netflix",
                "jiohotstar",
                "sonyliv",
                "zee5",
                "aha",
                "mx player",
                "mxplayer"
            ]:
                continue

            # A title is normally reasonably short.
            if 2 <= len(line) <= 150:
                title = line
                break

        if not title:
            continue

        genre = find_genre(
            lines,
            title,
            date,
            rating,
            media_type,
            language,
            platform
        )

        cards.append({
            "title": title,
            "rating": rating,
            "date": date,
            "type": media_type,
            "genre": genre or "Not listed",
            "language": language or "Not listed",
            "platform": platform or "Not listed"
        })

    # Deduplicate by title.
    unique = {}

    for card in cards:
        key = re.sub(
            r"[^a-z0-9]+",
            "",
            card["title"].lower()
        )

        if key and key not in unique:
            unique[key] = card

    final_cards = list(unique.values())

    print(f"Usable Binged cards: {len(final_cards)}")

    return final_cards


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def make_message(card):

    title = card["title"]
    rating = card["rating"]
    date = card["date"]
    media_type = card["type"]
    genre = card["genre"]
    language = card["language"]
    platform = card["platform"]

    binged_link = BINGED_URL
    stremio_link = (
        "https://stremio.app/#/search?search="
        + quote(title)
    )

    return (
        f"🎬 {title}\n\n"
        f"⭐ Rating: {rating}\n"
        f"📅 Release: {date}\n"
        f"🎞 Type: {media_type}\n"
        f"🎭 Genre: {genre}\n"
        f"🗣 Language: {language}\n"
        f"📺 Platform: {platform}\n\n"
        f"▶ Stremio: {stremio_link}\n"
        f"🔗 Binged: {binged_link}"
    )


# ============================================================
# MAIN
# ============================================================

def run():

    print("")
    print("========================================")
    print("BINGED → TELEGRAM")
    print("========================================")
    print("")

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN secret is missing."
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID secret is missing."
        )

    seen = load_seen()

    print(f"Previously sent titles: {len(seen)}")
    print("")

    with sync_playwright() as p:

        print("Launching Chromium...")

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = browser.new_context(
            viewport={
                "width": 1365,
                "height": 900
            },
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Kolkata"
        )

        page = context.new_page()

        print("Opening filtered Binged page...")
        print(BINGED_URL)

        try:

            response = page.goto(
                BINGED_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            if response:
                print(
                    f"Initial HTTP status: {response.status}"
                )

        except PlaywrightTimeoutError:
            print(
                "Page load timed out; checking rendered page anyway."
            )

        except Exception as e:
            print(f"Page navigation error: {e}")

        # Allow JavaScript-rendered content to appear.
        print("Waiting for Binged content...")

        try:
            page.wait_for_load_state(
                "networkidle",
                timeout=30000
            )
        except Exception:
            pass

        page.wait_for_timeout(5000)

        page_title = page.title()

        print(f"Browser page title: {page_title}")

        body_text = page.locator("body").inner_text(
            timeout=10000
        )

        print("")
        print("Checking page...")

        lower_body = body_text.lower()

        challenge_words = [
            "verify you are human",
            "checking your browser",
            "just a moment",
            "access denied",
            "forbidden"
        ]

        challenge_detected = any(
            word in lower_body
            for word in challenge_words
        )

        if challenge_detected:
            print("")
            print("BINGED BLOCKED THE GITHUB BROWSER.")
            print("A verification/403 page was returned.")
            print("")
            print("First page text:")
            print(body_text[:1500])

            page.screenshot(
                path="binged_debug.png",
                full_page=True
            )

            browser.close()

            raise RuntimeError(
                "Binged returned a verification/blocked page."
            )

        cards = extract_cards(page)

        if not cards:

            print("")
            print("NO BINGED CARDS FOUND.")
            print("")
            print("Page title:")
            print(page_title)
            print("")
            print("Visible page text:")
            print(body_text[:3000])

            page.screenshot(
                path="binged_debug.png",
                full_page=True
            )

            browser.close()

            raise RuntimeError(
                "Binged loaded, but no release cards could be extracted."
            )

        print("")
        print("========================================")
        print(f"TOTAL CARDS: {len(cards)}")
        print("========================================")
        print("")

        new_count = 0

        for card in cards:

            title = card["title"]

            title_key = re.sub(
                r"[^a-z0-9]+",
                "",
                title.lower()
            )

            print(
                f"{title} | "
                f"{card['rating']} | "
                f"{card['date']} | "
                f"{card['type']} | "
                f"{card['language']} | "
                f"{card['platform']}"
            )

            if title_key in seen:
                continue

            message = make_message(card)

            print(f"Sending Telegram: {title}")

            if send_telegram(message):

                seen.add(title_key)
                new_count += 1

                print(
                    f"Telegram sent successfully: {title}"
                )

            else:

                print(
                    f"Telegram FAILED: {title}"
                )

        browser.close()

    save_seen(seen)

    print("")
    print("========================================")
    print(f"New Telegram alerts: {new_count}")
    print(f"Total seen titles: {len(seen)}")
    print("========================================")


if __name__ == "__main__":
    run()
