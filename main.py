import os
import json
import re
from urllib.parse import quote
from bs4 import BeautifulSoup
from curl_cffi import requests

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
        res = requests.get(url, timeout=10, impersonate="chrome120").json()
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
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configuration missing.")
        return False
        
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
    res = requests.post(url, data=payload, timeout=10, impersonate="chrome120")
    return res.status_code == 200

def run_scraper():
    config = load_config()
    seen_titles = load_seen()
    
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/"
    }
    
    print("Fetching Binged page using Chrome TLS impersonation...")
    try:
        response = requests.get(
            BINGED_URL, 
            headers=headers, 
            impersonate="chrome120", 
            timeout=15
        )
        print(f"Page Load Response Status: {response.status_code}")
        if response.status_code != 200:
            print("Failed to load page.")
            return
    except Exception as e:
        print(f"Request Error: {e}")
        return

    soup = BeautifulSoup(response.content, "html.parser")
    items = []

    for tag in soup.find_all(["h2", "h3", "a"]):
        text = tag.get_text(strip=True)
        if text and len(text) > 2:
            if not any(x in text.lower() for x in ["trending", "streaming", "release", "view all", "binged", "privacy", "terms", "filters", "clear"]):
                clean_title = re.sub(r'\s+', ' ', text)
                if clean_title not in [i['title'] for i in items]:
                    items.append({'title': clean_title})

    print(f"Extracted {len(items)} titles from Binged.")
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

    save_seen(seen_titles)
    print(f"Process complete. {new_additions} alerts posted.")

if __name__ == "__main__":
    run_scraper()
