import os
import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

# ---------------- PATHS & CONFIG ----------------
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
            "parse_mode": "Markdown",
            "disable_web_page_preview": False
        }
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False
        }
    res = requests.post(url, data=payload, timeout=10)
    return res.status_code == 200

def run_scraper():
    config = load_config()
    seen_titles = load_seen()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    params = {
        "language": ",".join(config.get("language", [])),
        "category": ",".join(config.get("category", [])),
        "rating": ",".join(config.get("rating", []))
    }
    
    try:
        response = requests.get(BINGED_URL, headers=headers, params=params, timeout=15)
        if response.status_code != 200:
            print(f"Failed to fetch Binged releases. HTTP Status: {response.status_code}")
            return
    except Exception as e:
        print(f"Request Error: {e}")
        return

    soup = BeautifulSoup(response.content, "html.parser")
    items = []

    for tag in soup.find_all(["h2", "h3", "a"]):
        title_text = tag.get_text(strip=True)
        if title_text and len(title_text) > 2 and not any(x in title_text.lower() for x in ["trending", "streaming", "release", "view all", "binged", "privacy"]):
            clean_title = re.sub(r'\s+', ' ', title_text)
            if clean_title not in [i['title'] for i in items]:
                items.append({'title': clean_title})

    new_additions = 0

    for item in items[:10]:
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
            f"🗣 *Filter Match:* {languages_str}\n"
            f"📺 *Source:* Binged Release\n\n"
            f"▶ [Open in Stremio]({stremio_link})\n"
            f"🔗 [View on Binged]({binged_search_link})"
        )
        
        if send_telegram(message, poster_url):
            seen_titles.add(item_id)
            new_additions += 1
            print(f"Alert sent for: {title}")

    if new_additions > 0:
        save_seen(seen_titles)
    else:
        print("No new releases matching criteria.")

if __name__ == "__main__":
    run_scraper()
