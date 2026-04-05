# YouTube API Quota Extension Request — Ready-to-Submit Answers
# Form: https://support.google.com/youtube/contact/yt_api_form
# Project ID: yt-scraper-490819
# Submit AFTER Google Trust & Safety clears your violation appeal.

---

## Describe your application and how it uses the YouTube Data API

Our application is an internal gaming content creator discovery tool used by a small marketing and outreach team. It helps us identify YouTube channels in specific gaming niches — such as card games, roguelikes, indie games, and game development — for potential sponsorship and collaboration opportunities.

The application uses the following YouTube Data API v3 endpoints:

- **search.list** — to discover channels by searching gaming-related keywords (e.g. "slay the spire review", "indie game showcase"). Each call costs 100 quota units.
- **channels.list** — to retrieve channel metadata (subscriber count, description, country, contact emails) in efficient batches of 50 channel IDs per request. Each call costs 1 quota unit.

All data is stored in a private Google Sheet for internal use only. The tool runs once per day via an automated GitHub Actions workflow. No data is resold, redistributed, or made publicly accessible. No user authentication or OAuth is used — only a single server-side API key.

---

## How many users does your application have?

This is an internal tool used by 1-2 team members. It is not a consumer-facing or public application. There is no user-facing frontend that makes YouTube API calls.

---

## Why do you need additional quota?

Our daily discovery workflow exhausts the default 10,000 unit quota within approximately 1 minute due to the high cost of search.list calls (100 units each). This limits us to roughly 100 search queries per day, which is insufficient to cover the breadth of gaming niches we need to monitor for outreach.

With 50,000 units per day, we could perform approximately 450-500 search queries daily, allowing us to rotate through our full keyword set (70+ gaming topics combined with 25+ modifiers = 1,750+ unique queries) over a 3-4 day cycle instead of requiring weeks.

We have already implemented the following optimizations to minimize quota waste:

1. Deduplication — All previously discovered channel IDs are loaded into memory before any API calls. We never make redundant requests for channels already in our database.
2. Batched channels.list — Channel metadata is fetched in batches of 50 IDs per call, reducing quota cost to 1 unit per 50 channels.
3. Graceful quota handling — The script detects quotaExceeded errors and stops immediately rather than retrying or using backoff.
4. Single project, single key — We use exactly one Google Cloud project (yt-scraper-490819) with one API key, fully compliant with the Terms of Service.

---

## What is the URL of your application?

This is a private, server-side Python script executed via GitHub Actions. There is no public-facing URL. The source code repository is private.

---

## Requested quota amount

50,000 units per day.

---

## Quota breakdown estimate

| Operation        | Cost/call | Est. daily calls | Daily units |
|------------------|-----------|------------------|-------------|
| search.list      | 100       | ~450             | ~45,000     |
| channels.list    | 1         | ~35              | ~35         |
| **Total**        |           |                  | **~45,035** |
