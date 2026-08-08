import os
import json
import re
from urllib.parse import quote

from bs4 import BeautifulSoup
from curl_cffi import requests


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
    "&recommendation%5B%5D=Good"
    "&recommendation%5B%5D=Satisfactory"
    "&recommendation%5B%5D=Passable"
)

SEEN_FILE = "seen_titles.json"

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")


# ============================================================
# SEEN TITLES
# ============================================================

def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception as e:
        print(f"Could not read seen_titles.json: {e}")
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(
            sorted(seen),
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# HELPERS
# ============================================================

def clean_text(text):
    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def title_id(title):
    return re.sub(
        r"[^a-z0-9]+",
        "-",
        title.lower()
    ).strip("-")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(title, binged_url):

    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN secret is missing.")
        return False

    if not CHANNEL_ID:
        print("ERROR: CHANNEL_ID secret is missing.")
        return False

    stremio_url = (
        "https://stremio.app/#/search?search="
        + quote(title)
    )

    message = (
        f"<b>🎬 {title}</b>\n\n"
        f"🗣 <b>Language:</b> Hindi / Punjabi\n"
        f"📺 <b>Source:</b> Binged\n\n"
        f"▶ <a href=\"{stremio_url}\">"
        f"Open in Stremio"
        f"</a>\n"
        f"🔗 <a href=\"{binged_url}\">"
        f"View on Binged"
        f"</a>"
    )

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            data={
                "chat_id": CHANNEL_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            },
            timeout=20,
            impersonate="chrome120"
        )

        print(
            "Telegram:",
            response.status_code,
            response.text[:300]
        )

        return response.status_code == 200

    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# ============================================================
# BINGED SCRAPER
# ============================================================

def fetch_binged():

    print("Fetching filtered Binged URL...")
    print(BINGED_URL)

    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.google.com/",
        "Upgrade-Insecure-Requests": "1"
    }

    try:

        response = requests.get(
            BINGED_URL,
            headers=headers,
            timeout=30,
            impersonate="chrome120"
        )

        print(
            "Binged HTTP status:",
            response.status_code
        )

        if response.status_code != 200:
            print(
                "Binged response:",
                response.text[:500]
            )
            return []

        soup = BeautifulSoup(
            response.content,
            "html.parser"
        )

        results = []
        seen = set()

        # Look for links belonging to Binged release/title pages.
        for a in soup.find_all("a", href=True):

            href = a.get("href", "").strip()

            text = clean_text(
                a.get_text(" ", strip=True)
            )

            if not text:
                continue

            if len(text) < 2 or len(text) > 200:
                continue

            # Ignore obvious navigation/UI text.
            ignored = {
                "streaming now",
                "streaming soon",
                "today's releases",
                "view all",
                "filters",
                "apply filters",
                "clear",
                "login",
                "sign up",
                "privacy policy",
                "terms"
            }

            if text.lower() in ignored:
                continue

            # Only accept Binged internal links.
            if href.startswith("/"):
                full_url = "https://www.binged.com" + href
            elif href.startswith("https://www.binged.com/"):
                full_url = href
            else:
                continue

            # Exclude the filter page itself and obvious navigation.
            if "streaming-premiere-dates" in full_url:
                continue

            key = title_id(text)

            if not key:
                continue

            if key in seen:
                continue

            seen.add(key)

            results.append({
                "title": text,
                "url": full_url
            })

        print(
            f"Extracted {len(results)} possible titles."
        )

        return results

    except Exception as e:

        print(
            f"Binged request error: {repr(e)}"
        )

        return []


# ============================================================
# MAIN
# ============================================================

def run():

    print("=" * 60)
    print("BINGED → TELEGRAM")
    print("=" * 60)

    seen = load_seen()

    print(
        f"Previously sent titles: {len(seen)}"
    )

    results = fetch_binged()

    if not results:

        print(
            "No Binged titles extracted."
        )

        save_seen(seen)

        return

    new_count = 0

    for item in results:

        title = item["title"]
        url = item["url"]

        key = title_id(title)

        if key in seen:

            print(
                f"Already sent: {title}"
            )

            continue

        print(
            f"NEW: {title}"
        )

        if send_telegram(title, url):

            seen.add(key)
            new_count += 1

            print(
                f"Telegram notification sent: {title}"
            )

        else:

            print(
                f"Telegram notification FAILED: {title}"
            )

    save_seen(seen)

    print("=" * 60)
    print(
        f"New Telegram alerts: {new_count}"
    )
    print(
        f"Total seen titles: {len(seen)}"
    )
    print("=" * 60)


if __name__ == "__main__":
    run()
