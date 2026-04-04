# AI Context: YouTube Channel Discovery System

**Project Overview:**
This project is an automated, scalable YouTube scraping engine designed to find gaming-related YouTube channels (specifically card games, roguelikes, and indie games). It extracts channel metadata (subscribers, views, emails, external links) and maintains a deduplicated, live database in a private Google Sheet.

## 1. Core Architecture & Files
- **`youtube_api_discovery/discover_channels_api.py`**: The workhorse script. It leverages the YouTube Data API v3 to search for channels, extract full channel stats/descriptions using batched requests (50 per batch), and handles duplicate/quota management.
- **`yt_descriptions_ui.py`**: A Streamlit dashboard used for manually triggering the scraper and providing a UI wrapper. Includes custom `hmac` password protection (reading `app_password` from secrets).
- **`.github/workflows/daily_scrape.yml`**: A daily scheduled GitHub Action (runs every day at 10:00 UTC). It automatically triggers the python script, creating an invisible, zero-maintenance scraping pipeline.

## 2. Key Mechanics to Know
- **Procedural Query Generator**: Instead of a hardcoded list of search terms, `discover_channels_api.py` contains a procedural generator that multiplies a list of 25+ gaming keywords against 20+ modifier keywords to create over 500+ unique search phrases. The script shuffles this list every run to ensure diverse, randomized discovery.
- **Single API Key Usage**: To comply with Google Cloud Terms of Service, the script strictly uses one API key. It exits gracefully upon hitting the 10,000 unit daily limit per project to avoid quota circumvention flags.
- **Google Sheets Database (`YT_Scraper_DB`)**: Instead of writing to local CSVs, the script inherently talks to the user's `YT_Scraper_DB` Google Sheet via `gspread`. 
  - *Deduplication*: It reads the existing Sheet first, loads all `channel_id`s into memory, and strictly skips searching the API for channels we already have. 
  - *Overlap Tagging*: If a new search query discovers a channel we already have in the database, it uses `batch_update` to intelligently append the new query tag to the existing row without wasting YouTube API quotas.
  - *Anchoring*: The code utilizes `table_range="A1"` during `append_rows` to prevent the Google Sheets API from accidentally shifting new insertions horizontally.

## 3. Environment & Security
- **Secrets Management**: This project relies on Two Secrets:
    1. `YOUTUBE_API_KEY`: A single `AIzaSy...` key.
    2. `GOOGLE_CREDENTIALS`: A raw JSON payload representing a Google Service Account (which has Editor access to the specific Google Sheet).
- **Local Dev**: Handled by `.streamlit/secrets.toml` (which is safely `.gitignore`'d). The script also expects `google_credentials.json` at the root folder for Google Sheets auth.
- **Cloud Dev**: Handled directly via GitHub Repository Secrets injected continuously during the Action workflow.

## 4. Current State
- The system is fully operational and bug-free.
- The Python backend explicitly uses `Python 3.12` to satisfy Google API Core library requirements.
- The scraper operates cleanly and immediately dumps populated channels onto the Google Sheet, safely skipping any requests that exhaust quotas or timeout.
