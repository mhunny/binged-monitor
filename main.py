import os
import json
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# CONFIG
# ============================================================

BINGED_URL = "https://www.binged.com/streaming-premiere-dates/"

CONFIG_FILE = "config.json"
SEEN_FILE = "seen_titles.json"

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")

SCREENSHOT_FILE = "binged_debug.png"
HTML_FILE = "binged_debug.html"


# ============================================================
# LOAD CONFIG
# ============================================================

def load_config():
    default_config = {
        "language": ["Hindi"],
        "category": ["Film", "Tv show"],
        "rating": [
            "Must Watch",
            "Good",
            "Satisfactory",
            "Passable"
        ],
        "release_mode": "today"
    }

    if not os.path.exists(CONFIG_FILE):
        print("config.json not found. Using default configuration.")
        return default_config

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)

        for key, value in default_config.items():
            if key not in config:
                config[key] = value

        return config

    except Exception as e:
        print(f"Error loading config.json: {e}")
        return default_config


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
        print(f"Could not load seen_titles.json: {e}")
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(
            sorted(list(seen)),
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""

    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalise(value):
    return clean_text(value).lower()


def slug_id(title):
    return re.sub(
        r"[^a-z0-9]+",
        "-",
        title.lower()
    ).strip("-")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_message(text, poster_url=None):

    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN secret is missing.")
        return False

    if not CHANNEL_ID:
        print("ERROR: CHANNEL_ID secret is missing.")
        return False

    try:

        if poster_url:

            url = (
                f"https://api.telegram.org/"
                f"bot{BOT_TOKEN}/sendPhoto"
            )

            data = {
                "chat_id": CHANNEL_ID,
                "photo": poster_url,
                "caption": text,
                "parse_mode": "HTML"
            }

        else:

            url = (
                f"https://api.telegram.org/"
                f"bot{BOT_TOKEN}/sendMessage"
            )

            data = {
                "chat_id": CHANNEL_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }

        response = requests.post(
            url,
            data=data,
            timeout=20
        )

        print(
            "Telegram response:",
            response.status_code,
            response.text[:500]
        )

        return response.status_code == 200

    except Exception as e:

        print(f"Telegram error: {e}")
        return False


# ============================================================
# TMDB
# ============================================================

def get_tmdb_data(title):

    if not TMDB_API_KEY:
        return "N/A", None

    try:

        response = requests.get(
            "https://api.themoviedb.org/3/search/multi",
            params={
                "api_key": TMDB_API_KEY,
                "query": title,
                "language": "en-US",
                "include_adult": "false"
            },
            timeout=15
        )

        if response.status_code != 200:
            print(
                "TMDB error:",
                response.status_code
            )
            return "N/A", None

        data = response.json()

        results = data.get("results", [])

        if not results:
            return "N/A", None

        # Prefer movie/tv results.
        valid_results = [
            x for x in results
            if x.get("media_type") in ("movie", "tv")
        ]

        if valid_results:
            result = valid_results[0]
        else:
            result = results[0]

        vote = result.get("vote_average")

        if vote:
            rating = f"{float(vote):.1f}/10"
        else:
            rating = "N/A"

        poster_path = result.get("poster_path")

        if poster_path:
            poster = (
                "https://image.tmdb.org/t/p/w500"
                + poster_path
            )
        else:
            poster = None

        return rating, poster

    except Exception as e:

        print(f"TMDB exception: {e}")
        return "N/A", None


# ============================================================
# PLAYWRIGHT HELPERS
# ============================================================

def visible_text_locator(page, text):

    locator = page.get_by_text(
        text,
        exact=True
    )

    count = locator.count()

    for i in range(count):

        item = locator.nth(i)

        try:
            if item.is_visible():
                return item
        except Exception:
            pass

    return None


def click_visible_text(page, text, timeout=5000):

    locator = visible_text_locator(
        page,
        text
    )

    if locator is None:
        print(
            f"Could not find visible text: {text}"
        )
        return False

    try:

        locator.click(
            timeout=timeout
        )

        time.sleep(0.5)

        return True

    except Exception as e:

        print(
            f"Could not click '{text}': {e}"
        )

        return False


def click_dropdown_containing(page, label):

    """
    Attempts to locate the filter section containing
    the requested label and click its dropdown.
    """

    print(f"Opening filter: {label}")

    # First try exact label.
    label_locator = page.get_by_text(
        label,
        exact=True
    )

    count = label_locator.count()

    for i in range(count):

        item = label_locator.nth(i)

        try:

            if not item.is_visible():
                continue

            # Look around the label for a clickable parent.
            parent = item.locator("..")

            if parent.count():

                try:
                    parent.click(timeout=2500)
                    time.sleep(0.5)
                    return True
                except Exception:
                    pass

            try:
                item.click(timeout=2500)
                time.sleep(0.5)
                return True
            except Exception:
                pass

        except Exception:
            continue

    print(
        f"Could not automatically open {label} filter."
    )

    return False


# ============================================================
# SELECT FILTER VALUES
# ============================================================

def select_filter_values(page, values):

    for value in values:

        print(f"Selecting: {value}")

        locator = page.get_by_text(
            value,
            exact=True
        )

        found = False

        for i in range(locator.count()):

            item = locator.nth(i)

            try:

                if not item.is_visible():
                    continue

                item.click(timeout=3000)

                found = True

                time.sleep(0.3)

                break

            except Exception:
                continue

        if not found:
            print(
                f"WARNING: Could not select {value}"
            )


# ============================================================
# APPLY BINGED FILTERS
# ============================================================

def apply_binged_filters(page, config):

    print("Applying Binged filters...")

    # --------------------------------------------------------
    # Category
    # --------------------------------------------------------

    if click_dropdown_containing(
        page,
        "Category"
    ):

        select_filter_values(
            page,
            config.get(
                "category",
                []
            )
        )

    # Close/open state is handled by clicking next filter.

    # --------------------------------------------------------
    # Language
    # --------------------------------------------------------

    if click_dropdown_containing(
        page,
        "Language"
    ):

        select_filter_values(
            page,
            config.get(
                "language",
                []
            )
        )

    # --------------------------------------------------------
    # Rating
    # --------------------------------------------------------

    if click_dropdown_containing(
        page,
        "Rating"
    ):

        select_filter_values(
            page,
            config.get(
                "rating",
                []
            )
        )

    # --------------------------------------------------------
    # Today's Releases
    # --------------------------------------------------------

    release_mode = config.get(
        "release_mode",
        "today"
    )

    if release_mode == "today":

        print("Selecting Today's Releases...")

        today = page.get_by_text(
            "Today's Releases",
            exact=True
        )

        for i in range(today.count()):

            item = today.nth(i)

            try:

                if item.is_visible():

                    item.click(timeout=3000)

                    time.sleep(1)

                    break

            except Exception:
                continue

    # --------------------------------------------------------
    # Apply Filters
    # --------------------------------------------------------

    print("Looking for APPLY FILTERS button...")

    apply_button = page.get_by_text(
        "APPLY FILTERS",
        exact=True
    )

    clicked = False

    for i in range(apply_button.count()):

        item = apply_button.nth(i)

        try:

            if item.is_visible():

                item.click(timeout=5000)

                clicked = True

                print(
                    "APPLY FILTERS clicked."
                )

                break

        except Exception:
            continue

    if not clicked:

        # Try case-insensitive CSS/text fallback.
        try:

            button = page.locator(
                "button",
                has_text="APPLY FILTERS"
            ).first

            if button.is_visible():

                button.click(timeout=5000)

                clicked = True

        except Exception:
            pass

    if not clicked:

        print(
            "ERROR: APPLY FILTERS button could not be clicked."
        )

        return False

    # Wait for AJAX filtering.
    print(
        "Waiting for Binged AJAX results..."
    )

    try:

        page.wait_for_load_state(
            "networkidle",
            timeout=15000
        )

    except PlaywrightTimeoutError:
        pass

    time.sleep(3)

    return True


# ============================================================
# EXTRACT RESULTS
# ============================================================

def extract_results(page):

    print("Extracting filtered Binged results...")

    results = []

    # Give the AJAX content time to render.
    time.sleep(2)

    # Find links under the streaming-premiere-dates section.
    links = page.locator(
        'a[href*="/streaming-premiere-dates/"]'
    )

    count = links.count()

    print(
        f"Potential Binged result links: {count}"
    )

    seen_urls = set()

    for i in range(count):

        try:

            link = links.nth(i)

            if not link.is_visible():
                continue

            href = link.get_attribute("href")

            if not href:
                continue

            if href.rstrip("/") == BINGED_URL.rstrip("/"):
                continue

            if href in seen_urls:
                continue

            title = clean_text(
                link.inner_text()
            )

            if not title:
                continue

            # Ignore navigation links.
            ignored = {
                "view all",
                "streaming now",
                "streaming soon",
                "today's releases"
            }

            if title.lower() in ignored:
                continue

            seen_urls.add(href)

            results.append(
                {
                    "title": title,
                    "url": href
                }
            )

        except Exception:
            continue

    # Remove obvious duplicate/navigation entries.
    final_results = []

    title_seen = set()

    for item in results:

        key = normalise(
            item["title"]
        )

        if len(key) < 2:
            continue

        if key in title_seen:
            continue

        title_seen.add(key)

        final_results.append(item)

    print(
        f"Filtered results extracted: {len(final_results)}"
    )

    return final_results


# ============================================================
# FALLBACK RESULT PARSER
# ============================================================

def extract_from_html(page):

    print(
        "Running fallback HTML extraction..."
    )

    html = page.content()

    soup = BeautifulSoup(
        html,
        "lxml"
    )

    results = []

    for a in soup.select(
        'a[href*="/streaming-premiere-dates/"]'
    ):

        title = clean_text(
            a.get_text(" ", strip=True)
        )

        href = a.get("href")

        if not title or not href:
            continue

        if len(title) < 2:
            continue

        if title.lower() in {
            "view all",
            "streaming now",
            "streaming soon",
            "today's releases"
        }:
            continue

        results.append(
            {
                "title": title,
                "url": href
            }
        )

    unique = {}

    for item in results:

        key = normalise(
            item["title"]
        )

        if key not in unique:
            unique[key] = item

    return list(unique.values())


# ============================================================
# TELEGRAM MESSAGE
# ============================================================

def make_message(
    item,
    tmdb_rating,
    config
):

    title = item["title"]

    binged_url = item["url"]

    if binged_url.startswith("/"):
        binged_url = (
            "https://www.binged.com"
            + binged_url
        )

    stremio_url = (
        "https://stremio.app/"
        "#/search?search="
        + quote(title)
    )

    languages = ", ".join(
        config.get(
            "language",
            ["Hindi"]
        )
    )

    message = (
        f"<b>🎬 {title}</b>\n\n"
        f"⭐ <b>TMDB:</b> {tmdb_rating}\n"
        f"🗣 <b>Language:</b> {languages}\n"
        f"📺 <b>Source:</b> Binged\n\n"
        f"▶ <a href=\"{stremio_url}\">"
        f"Open in Stremio"
        f"</a>\n"
        f"🔗 <a href=\"{binged_url}\">"
        f"View on Binged"
        f"</a>"
    )

    return message


# ============================================================
# MAIN SCRAPER
# ============================================================

def run_scraper():

    print("=" * 60)
    print("BINGED OTT TRACKER")
    print("=" * 60)

    config = load_config()

    print(
        "Configuration:",
        json.dumps(
            config,
            indent=2
        )
    )

    seen = load_seen()

    print(
        f"Previously seen titles: {len(seen)}"
    )

    with sync_playwright() as p:

        print(
            "Launching Chromium via Playwright..."
        )

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
                "width": 1440,
                "height": 1200
            },
            locale="en-US",
            timezone_id="Asia/Kolkata",
            user_agent=(
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 "
                "Safari/537.36"
            )
        )

        page = context.new_page()

        try:

            print(
                f"Opening {BINGED_URL}"
            )

            response = page.goto(
                BINGED_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            if response:

                print(
                    "Initial HTTP status:",
                    response.status
                )

                if response.status >= 400:

                    print(
                        "Binged returned HTTP",
                        response.status
                    )

            page.wait_for_timeout(5000)

            # Save initial debugging files.
            page.screenshot(
                path=SCREENSHOT_FILE,
                full_page=True
            )

            with open(
                HTML_FILE,
                "w",
                encoding="utf-8"
            ) as f:
                f.write(
                    page.content()
                )

            # ------------------------------------------------
            # Apply filters
            # ------------------------------------------------

            filter_success = apply_binged_filters(
                page,
                config
            )

            if not filter_success:

                print(
                    "WARNING: Filter application failed."
                )

            # ------------------------------------------------
            # Extract
            # ------------------------------------------------

            results = extract_results(page)

            if not results:

                print(
                    "No results from primary extraction."
                )

                results = extract_from_html(
                    page
                )

            print(
                f"Total results found: {len(results)}"
            )

            # ------------------------------------------------
            # Process new titles
            # ------------------------------------------------

            new_count = 0

            for item in results:

                title = item["title"]

                item_key = slug_id(
                    title
                )

                if not item_key:
                    continue

                if item_key in seen:

                    print(
                        f"Already sent: {title}"
                    )

                    continue

                print(
                    f"NEW: {title}"
                )

                tmdb_rating, poster = (
                    get_tmdb_data(title)
                )

                message = make_message(
                    item,
                    tmdb_rating,
                    config
                )

                sent = send_telegram_message(
                    message,
                    poster
                )

                if sent:

                    seen.add(item_key)

                    new_count += 1

                    print(
                        f"Telegram alert sent: {title}"
                    )

                else:

                    print(
                        f"Telegram failed: {title}"
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

        except Exception as e:

            print(
                "SCRAPER ERROR:",
                repr(e)
            )

            try:

                page.screenshot(
                    path=SCREENSHOT_FILE,
                    full_page=True
                )

                with open(
                    HTML_FILE,
                    "w",
                    encoding="utf-8"
                ) as f:
                    f.write(
                        page.content()
                    )

                print(
                    "Debug screenshot and HTML saved."
                )

            except Exception:
                pass

            raise

        finally:

            context.close()
            browser.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_scraper()
