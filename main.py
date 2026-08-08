name: Binged OTT Tracker

on:
  schedule:
    - cron: '0 */1 * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scrape-and-notify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run Scraper Script
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          TMDB_API_KEY: ${{ secrets.TMDB_API_KEY }}
        run: python main.py

      - name: Save Updated Seen List
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add seen_titles.json || true
          git pull --rebase origin main || true
          git commit -m "Auto-update seen list" || true
          git push
