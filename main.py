import os
import json
import re
import requests
from urllib.parse import quote
from playwright.sync_api import sync_playwright

# ---------------- CONFIGURATION ----------------
BINGED_URL = "https://www.binged.com/streaming-premiere-dates/"
SEEN_FILE = "seen_titles.json"
CONFIG_FILE = "config.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config.json: {e}")
    return {
        "language": ["Hindi", "Punjabi"],
        "category": ["Film", "Tv show"],
        "rating": ["Must Watch", "Good", "Satisfactory", "Passable"]
    }

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen(seen_titles):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_titles), f, indent=2)

def get_tmdb_data(title):
    if not TMDB_API_KEY:
        return "N/A", None
    
    url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={quote(title)}&language=en-US"
    try:
        res = requests.get(url, timeout=10).json()
        results = res.get("results", [])
        if results:
            first = results[0]
            rating = round(first.get("vote_average", 0), 1)
            rating_str = f"{rating}/10" if rating > 0 else "N/A"
            poster_path = first.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            return rating_str, poster_url
    except Exception as e:
        print(f"TMDB Fetch Error: {e}")
    
    return "N/A", None

def send_telegram(text, poster_url=None):
    if poster_url:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": poster_url,
            "caption": text,
            "parse_mode": "Markdown"
        }
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }
    res = requests.post(url, data=payload, timeout=10)
    return res.status_code == 200

def run_scraper():
    config = load_config()
    seen_titles = load_seen()
    items = []

    print("Launching Chromium via Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # Navigate to Binged
        response = page.goto(BINGED_URL, wait_until="domcontentloaded", timeout=30000)
        print(f"Page Load Response Status: {response.status if response else 'No Response'}")
        
        # Wait for dynamic titles to load
        page.wait_for_timeout(5000)
        
        # Parse titles
        elements = page.query_selector_all("a, h2, h3")
        for elem in elements:
            text = elem.inner_text().strip()
            if text and len(text) > 2:
                if not any(x in text.lower() for x in ["trending", "streaming", "release", "view all", "binged", "privacy", "terms", "filters", "clear"]):
                    clean_title = re.sub(r'\s+', ' ', text)
                    if clean_title not in [i['title'] for i in items]:
                        items.append({'title': clean_title})
                        
        browser.close()

    print(f"Playwright extracted {len(items)} titles.")
    new_additions = 0

    for item in items[:15]:
        title = item['title']
        item_id = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
        
        if item_id in seen_titles:
            continue
        
        rating, poster_url = get_tmdb_data(title)
        stremio_link = f"https://stremio.app/#/search?search={quote(title)}"
        binged_search_link = f"https://www.binged.com/?s={quote(title)}"
        
        languages_str = ", ".join(config.get("language", []))
        message = (
            f"🎬 *{title}*\n\n"
            f"⭐ *IMDb / TMDB:* {rating}\n"
            f"🗣 *Languages:* {languages_str}\n"
            f"📺 *Source:* Binged Release\n\n"
            f"▶ [Open in Stremio]({stremio_link})\n"
            f"🔗 [View on Binged]({binged_search_link})"
        )
        
        if send_telegram(message, poster_url):
            seen_titles.add(item_id)
            new_additions += 1
            print(f"Telegram alert sent for: {title}")

    # Ensure file is saved even if empty to prevent git errors
    save_seen(seen_titles)
    print(f"Process complete. {new_additions} alerts posted.")

if __name__ == "__main__":
    run_scraper()
