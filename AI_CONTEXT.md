# AI Context: YouTube Channel Discovery System

> **🚨 CRITICAL AI DIRECTIVE 🚨**
> **READ THIS ENTIRE FILE BEFORE TAKING ANY ACTION.**
> To save the user's API credits, this document is designed to be **"sufficient sufficient"** context. 
> You should NOT need to read or scan the entire repository to understand the project architecture, environment, or rules.
> 
> **YOUR OBLIGATIONS:**
> 1. **ALWAYS KEEP THIS DOCUMENT TURBO UP-TO-DATE.** If you make *any* structural changes, fix major bugs, add new files, change environment variables, or run workflows, you **MUST** update this file immediately.
> 2. **ALWAYS ADD TO THE CHANGELOG** at the bottom of this file. Do not alter past changelog entries, just append to them.

---

## 🏗️ Project Overview & Architecture
This is an automated, scalable YouTube scraping engine that locates gaming-related YouTube channels (specifically card games, roguelikes, and indie games). It extracts channel metadata and populates a live database in a private Google Sheet.

**Key Technical Details:**
- **Language**: Python 3.12 
- **Dependencies**: `google-api-python-client`, `gspread`, `oauth2client`, `playwright`, `langdetect`, `requests`, `streamlit`.

### 📂 Directory Structure & Core Files
- **`youtube_api_discovery/discover_channels_api.py`** 
  - *The Workhorse Script.* Leverages the YouTube Data API v3 to search for channels.
  - Extracts full channel stats/descriptions using batched API requests (50 per batch).
  - Handles deduplication and quota management gracefully. 
  - **Discovery Modes:** Contains 3 hybrid discovery modes: Playwright scraping (frontend), API Crawling (checking subscriptions), and API Search (randomized procedural queries).
- **`yt_descriptions_ui.py`** 
  - A Streamlit dashboard used for manually triggering the scraper and providing a UI wrapper. Includes custom `hmac` password protection.
- **`.github/workflows/daily_scrape.yml`** 
  - A scheduled GitHub Action that runs daily at `10:00 UTC` to trigger the Python script automatically.

---

## ⚙️ Key Mechanics & Rules

1. **Google Sheets Database (`YT_Scraper_DB`)**
   - We do *not* rely primarily on CSVs. The script natively talks to the user's Google Sheet via `gspread`.
   - **Deduplication:** When the script boots, it reads all `channel_id`s from the Sheet into memory to prevent searching for or parsing duplicates. 
   - **Overlap Tagging:** If a previously known channel is found under a *new* search query, the script intelligently uses `batch_update` to append the new query tag to the existing row instead of making duplicate rows.
   - **Anchoring:** Uses `table_range="A1"` when appending rows to prevent horizontal shifting bugs in Sheets API.

2. **Google Cloud / Quota Compliance (CRITICAL)**
   - **DO NOT INTRODUCE MULTI-KEY OR MULTI-PROJECT ROTATION.** The project was previously suspended for quota circumvention. Ensure it strictly abides by the 10,000 unit daily limit using exactly **one project** and **one API key**. 
   - The script exits cleanly when it receives a `quotaExceeded` or `403/429` error.

3. **Procedural Query Generator**
   - The script creates 1,750+ unique search phrases by cross-multiplying 70+ base gaming terms with 25+ modifier phrases. It uses random shuffling to ensure varying paths of discovery every single day.

4. **Discord Webhook Notifications**
   - After each run, a Discord notification is fired indicating the run duration, exhaustion status, errors, and top-performing niches. 
   - **Warning**: Discord has a strict 2000-character payload limit. The Python script truncates text to 1950 chars to avoid a `400 Bad Request` silent drop.

---

## 🔐 Environment & Secrets
This project relies on environmental secrets for security and auth.

1. **`YOUTUBE_API_KEYS`**: Singular Google Data API v3 key.
2. **`GOOGLE_CREDENTIALS`**: Raw JSON payload for a Google Service Account (used to authorize `gspread` writes to the spreadsheet).
3. **`DISCORD_WEBHOOK_URL`**: Used by `requests.post()` in the final completion steps.

*(In local dev environments, Streamlit uses `.streamlit/secrets.toml`, and the script expects a `google_credentials.json` fallback, which are all git-ignored).*

---

## 📝 Changelog (AIs, append your changes here!)

- **2026-04-05 (Current)**:
  - Deep-rewrote `AI_CONTEXT.md` to be the "sufficient sufficient" master document to save AI token reading costs. Added explicit AI modification rules to ensure it remains turbo up-to-date.
  - Investigated Discord message failure reported by user. Reminded user that local test runs will silently skip the webhook if the `DISCORD_WEBHOOK_URL` environment variable is not explicitly exported in their terminal session.
- **2026-04-05**: Fixed silent failure with Discord webhook notifications (Discord returns 400 Bad Request on >2000 chars). Added content length truncation and explicit `raise_for_status()`. 
- **2026-04-04**: Fixed NameError crash in summary generator and consolidated from multi-project rotation to a single active GCP project to comply with Google Trust & Safety bounds. Scraping logic was made hyper-resilient to errors.
