"""
discover_channels_api.py

Discover YouTube channels related to card games, roguelike games, Steam Next Fest, and indie/demo games.
Fetch channel descriptions and extract emails using YouTube Data API v3.
Output CSV with channel info and emails, or append directly to a Google Sheet.
"""

import csv
import os
import json
import re
from datetime import datetime, timedelta, timezone
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import random
import requests
from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

def send_discord_notification(webhook_url, summary):
    """Sends a formatted summary to a Discord webhook."""
    if not webhook_url:
        print("No DISCORD_WEBHOOK_URL provided, skipping notification.")
        return
        
    status_emoji = "✅" if not summary['api_exhausted'] else "⚠️"
    error_summary = ""
    if summary.get('errors'):
        # Truncate each error to max 150 chars just to be safe
        truncated_errors = []
        for err in summary['errors'][:5]:
            err_str = str(err)
            if len(err_str) > 150:
                err_str = err_str[:147] + "..."
            truncated_errors.append(err_str)
        error_summary = "\n**Errors Encountered:**\n" + "\n".join([f"- {err}" for err in truncated_errors])
        if len(summary['errors']) > 5:
            error_summary += f"\n- ...and {len(summary['errors']) - 5} more errors."

    duration = summary.get('duration', 'unknown')
    niche_summary = ""
    if summary.get('top_niches'):
        niche_summary = "\n**Top Niches:**\n" + "\n".join([f"- {n}: {c} found" for n, c in summary['top_niches']])

    efficiency = 0
    if summary.get('searches_performed', 0) > 0:
        efficiency = round(summary['new_channels_found'] / summary['searches_performed'], 2)

    content = f"""
**{status_emoji} YouTube Scraper Run Complete**
- **New Channels Found:** {summary['new_channels_found']}
- **Sources:** Scrape ({summary.get('scrape_count',0)}), Crawl ({summary.get('crawl_count',0)}), Search ({summary.get('search_count',0)})
- **API Keys Used:** {summary['api_keys_used']} / {summary['total_keys']}
- **Run Duration:** {duration}
- **Quota Status:** {'EXHAUSTED' if summary['api_exhausted'] else 'OK'}
{niche_summary}
{error_summary}
    """.strip()
    
    # Discord has a hard 2000 character limit for messages.
    if len(content) > 1950:
        content = content[:1950] + "\n... [TRUNCATED DUE TO DISCORD LIMIT]"
    
    print("\nAttempting to push summary to Discord webhook...")
    try:
        response = requests.post(webhook_url.strip(), json={"content": content})
        response.raise_for_status()
        print(f"Discord notification successfully sent! (HTTP {response.status_code})")
    except Exception as e:
        print(f"FAILED to send Discord notification! Error: {e}")
        try:
            print(f"Discord Response Details: {response.text}")
        except:
            pass

def generate_queries():
    """Procedurally generate an infinite matrix of unique gaming queries."""
    topics = [
        # Digital card games
        "hearthstone", "magic the gathering", "pokemon tcg", "yu-gi-oh", 
        "marvel snap", "gwent", "legends of runeterra",
        # Roguelikes / deckbuilders
        "slay the spire", "balatro", "hades", "binding of isaac",
        "inscryption", "monster train", "deckbuilder", "roguelike", 
        "roguelite", "metroidvania",
        # Specific roguelike titles (to catch roguelike reviewers)
        "dead cells", "enter the gungeon", "vampire survivors", "risk of rain",
        "cult of the lamb", "noita", "spelunky",
        # TCG / Physical card games
        "tcg", "trading card game", "card opening", "pokemon cards",
        "one piece tcg", "flesh and blood tcg", "digimon tcg", "card unboxing",
        # Board / tabletop games
        "board game", "tabletop game", "tabletop rpg", "dungeons and dragons",
        # Indie game discovery
        "indie game", "indie game review", "hidden gem game", "steam indie",
        "upcoming indie games",
        # Game dev
        "game development", "game design", "godot game", "unity game dev",
        # Cozy / life sim
        "cozy game", "farming sim", "stardew valley", "animal crossing",
        "cozy indie game",
        # Strategy / 4X
        "civilization game", "total war", "grand strategy", "4x game",
        # Horror
        "indie horror game", "psychological horror game",
        # General reviews / news
        "game review", "gaming news", "steam game review",
        # Mobile
        "mobile indie game",
        # Steam / PC
        "steam deck game", "pc game review",
        # Other
        "roblox", "gacha", "rpg maker", "pixel art", "survivor.io",
        "strategy card",
        # NEW NICHES TO CAPTURE OLD KOLs
        "minecraft", "roblox", "fortnite", "valorant", "league of legends",
        "personal finance", "investing", "financial audit", "money talk",
        "board game review", "tabletop simulator",
        "jogos", "videojuegos", "gaming brasil", "gaming españa", "gaming mexico", "gaming france",
        "indie game dev", "gamedev log", "how to make a game"
    ]
    modifiers = [
        "gameplay", "demo", "review", "showcase", "devlog", "trailer", 
        "speedrun", "hidden gem", "walkthrough", "let's play", "tips", 
        "guide", "box break", "packs", "pulls", "beta", "early access",
        "first impressions", "update", "new content",
        # New modifiers for broader reach
        "top 10", "best games", "new releases", "worth playing", "underrated",
        "in 2026", "news", "explained", "tier list", "versus"
    ]
    
    # Generate cross-product = 1700+ combos
    all_combos = [f"{t} {m}" for t in topics for m in modifiers]
    all_combos.extend(topics) # Add base topics
    all_combos.append("steam next fest")
    
    # Shuffle so every time the github action starts up, it searches a totally unique path!
    random.shuffle(all_combos)
    
    return all_combos

# Default Queries for discovery
QUERIES = generate_queries()

def extract_emails(text):
    """Extract email addresses from text."""
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    return list(set(emails))

def extract_links(text):
    """Extract URLs from text."""
    url_pattern = r'https?://[^\s]+'
    links = re.findall(url_pattern, text)
    return list(set(links))

def scrape_channels_frontend(queries, max_new, existing_ids):
    scraped_ids = set()
    errors = []
    import urllib.parse
    print("Starting Playwright Scraping Mode...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            for query in queries[:5]:
                if len(scraped_ids) >= max_new: break
                try:
                    q = urllib.parse.quote(query)
                    page.goto(f"https://www.youtube.com/results?search_query={q}&sp=EgIQAg%253D%253D", timeout=15000)
                    page.wait_for_selector('ytd-channel-renderer', timeout=5000)
                    hrefs = page.evaluate('''() => {
                        return Array.from(document.querySelectorAll('ytd-channel-renderer a#main-link')).map(a => a.href);
                    }''')
                    for href in hrefs:
                        if href and '/@' in href:
                            try:
                                r = requests.get(href, timeout=5)
                                match = re.search(r'"channelId":"(UC[\w-]{22})"', r.text)
                                if match:
                                    cid = match.group(1)
                                    if cid not in existing_ids: scraped_ids.add(cid)
                            except: pass
                        elif href and '/channel/' in href:
                            cid = href.split('/channel/')[-1].split('/')[0]
                            if cid not in existing_ids: scraped_ids.add(cid)
                except Exception as e:
                    errors.append(f"Scrape warning '{query}': {str(e)}")
            browser.close()
    except Exception as e:
        errors.append(f"Playwright failed: {str(e)}")
        
    return scraped_ids, errors

def crawl_channels_api(youtube, seed_ids, max_new, existing_ids):
    crawled_ids = set()
    errors = []
    print("Starting API Crawling Mode...")
    if not seed_ids: return crawled_ids, errors
        
    seeds = random.sample(list(seed_ids), min(10, len(seed_ids)))
    for seed in seeds:
        if len(crawled_ids) >= max_new: break
        try:
            req = youtube.subscriptions().list(channelId=seed, part='snippet', maxResults=50)
            res = req.execute()
            for item in res.get('items', []):
                cid = item['snippet']['resourceId'].get('channelId')
                if cid and cid not in existing_ids:
                    crawled_ids.add(cid)
        except HttpError as e:
            try:
                err_data = json.loads(e.content)
                reason = err_data.get('error', {}).get('errors', [{}])[0].get('reason', '')
                if reason == 'subscriptionForbidden': continue
            except: pass
        except Exception as e:
             errors.append(f"Crawl error on {seed}: {e}")
    return crawled_ids, errors

def batch_populate_channels(youtube, target_ids, channels_dict, include_recent_date, include_avg_views):
    errors = []
    target_ids = list(target_ids)
    for i in range(0, len(target_ids), 50):
        batch = target_ids[i:i+50]
        try:
            req = youtube.channels().list(part='snippet,statistics', id=','.join(batch))
            res = req.execute()
            for item in res.get('items', []):
                cid = item['id']
                data = channels_dict.get(cid)
                if not data: continue
                
                snippet = item.get('snippet', {})
                stats = item.get('statistics', {})
                description = snippet.get('description', '')
                
                data['channel_description'] = description
                data['emails'] = extract_emails(description)
                data['links'] = extract_links(description)
                data['subscribers'] = stats.get('subscriberCount', 'N/A')
                data['view_count'] = stats.get('viewCount', 'N/A')
                data['video_count'] = stats.get('videoCount', 'N/A')
                data['custom_url'] = snippet.get('customUrl', '')
                data['country'] = snippet.get('country', '')
                data['default_language'] = snippet.get('defaultLanguage', '')
                data['published_at'] = snippet.get('publishedAt', '')
                
                data['description_language'] = 'unknown'
                if description.strip():
                    try: data['description_language'] = detect(description)
                    except LangDetectException: pass
                
                # Heavy Optional Loops
                if include_recent_date:
                    try:
                        r = youtube.search().list(channelId=cid, type='video', part='snippet', order='date', maxResults=1).execute()
                        if r['items']: data['recent_video_date'] = r['items'][0]['snippet']['publishedAt']
                    except: pass
                
                if include_avg_views:
                    try:
                        oma = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat() + 'Z'
                        v_req = youtube.search().list(channelId=cid, type='video', part='id', publishedAfter=oma, maxResults=50)
                        v_res = v_req.execute()
                        vids = [v['id']['videoId'] for v in v_res['items']]
                        if vids:
                            vstat = youtube.videos().list(part='statistics', id=','.join(vids)).execute()
                            tot = sum(int(v['statistics'].get('viewCount', 0)) for v in vstat['items'])
                            data['avg_views_last_month'] = tot / len(vstat['items'])
                    except: pass
                    
                data['populated'] = True
        except Exception as e:
            errors.append(f"Batch populate error: {e}")
            
    return errors



def get_gspread_client(creds_file="google_credentials.json"):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
    client = gspread.authorize(creds)
    return client

def discover_channels(output_file, max_new=1000, queries=None, include_recent_date=False, include_avg_views=False, existing_csv=None, api_key=None, google_sheet=None, dry_run=False):
    if queries is None:
        queries = QUERIES
        
    if not api_key:
        raise ValueError("No valid API key provided.")
    youtube = build('youtube', 'v3', developerKey=api_key.strip())
    
    channels = {}
    new_channel_ids = set()
    sheet_obj = None
    run_errors = []
    start_time = datetime.now(timezone.utc)
    searches_performed = 0
    niche_performance = {} # Track new channels found per topic
    
    fieldnames = [
        'channel_id', 'channel_name', 'channel_url', 'custom_url', 'subscribers', 
        'view_count', 'video_count', 'country', 'default_language', 'published_at',
        'channel_description', 'emails', 'links', 'queries', 
        'recent_video_date', 'avg_views_last_month', 'discovered_at', 'description_language'
    ]

    # Google Sheets Initialization
    if google_sheet:
        try:
            gc = get_gspread_client()
            sheet_obj = gc.open(google_sheet).sheet1
            data = sheet_obj.get_all_values()
            if not data:
                sheet_obj.append_row(fieldnames)
            else:
                # Validate header row — if row 1 doesn't match expected fieldnames, insert it
                header_row = data[0]
                if header_row != fieldnames:
                    if header_row[0].strip().startswith('UC'):
                        # Row 1 is data, not a header — insert header above it
                        sheet_obj.insert_row(fieldnames, index=1)
                        print("Inserted missing header row into Google Sheet.")
                        # Re-fetch data after header insertion (indices shifted by 1)
                        data = sheet_obj.get_all_values()
                    else:
                        # Header exists but may be outdated — update it
                        sheet_obj.update(values=[fieldnames], range_name='A1')
                        print("Updated header row in Google Sheet.")

                for idx, row in enumerate(data[1:], start=2): # 1-based indexing in sheets, row 1 is header
                    if len(row) > 0 and row[0].strip():
                        existing_qs = row[13].split(';') if len(row) > 13 else []
                        channels[row[0]] = {
                            'is_remote': True,
                            'row_idx': idx,
                            'queries': [q.strip() for q in existing_qs if q.strip()],
                            'updated_queries': False
                        }
        except Exception as e:
            print(f"Error connecting to Google Sheets: {e}")
            return

    # Load existing CSV (fallback or addition)
    if existing_csv and os.path.exists(existing_csv):
        try:
            with open(existing_csv, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'channel_id' in row:
                        channels[row['channel_id']] = {
                            'channel_name': row.get('channel_name', ''),
                            'channel_url': row.get('channel_url', ''),
                            'channel_description': row.get('channel_description', ''),
                            'emails': row.get('emails', '').split(';') if row.get('emails') else [],
                            'links': row.get('links', '').split(';') if row.get('links') else [],
                            'subscribers': row.get('subscribers', 'N/A'),
                            'recent_video_date': row.get('recent_video_date', 'N/A'),
                            'avg_views_last_month': row.get('avg_views_last_month', 'N/A'),
                            'queries': row.get('queries', '').split(';') if row.get('queries') else [],
                            'custom_url': row.get('custom_url', ''),
                            'country': row.get('country', ''),
                            'default_language': row.get('default_language', ''),
                            'published_at': row.get('published_at', ''),
                            'view_count': row.get('view_count', ''),
                            'video_count': row.get('video_count', '')
                        }
        except Exception as e:
            print(f"Error loading existing CSV: {e}")
    
    max_total = len(channels) + max_new
    total_channels = len(channels)
    all_existing_ids = set(channels.keys())
    
    mode_stats = {'scrape': 0, 'crawl': 0, 'search': 0}

    def init_channel_stub(cid, name, query_tag):
        return {
            'channel_name': name,
            'channel_url': f'https://www.youtube.com/channel/{cid}',
            'channel_description': '',
            'emails': [],
            'links': [],
            'subscribers': 'N/A',
            'recent_video_date': 'N/A',
            'avg_views_last_month': 'N/A',
            'queries': [query_tag],
            'custom_url': '',
            'country': '',
            'default_language': '',
            'published_at': '',
            'view_count': '',
            'video_count': '',
            'discovered_at': datetime.now(timezone.utc).isoformat() + 'Z',
            'populated': False
        }

    # MODE 1: Scrape
    if not dry_run and max_new > 0 and len(new_channel_ids) < max_new:
        scraped_ids, scrape_errs = scrape_channels_frontend(queries, min(10, max_new), all_existing_ids)
        run_errors.extend(scrape_errs)
        for cid in scraped_ids:
            channels[cid] = init_channel_stub(cid, 'Scraped Channel', 'scrape:playwright')
            new_channel_ids.add(cid)
            all_existing_ids.add(cid)
            total_channels += 1
            mode_stats['scrape'] += 1

    # MODE 2: Crawl
    if not dry_run and max_new > 0 and len(new_channel_ids) < max_new:
        seed_pool = [k for k, v in channels.items() if v.get('is_remote')]
        crawled_ids, crawl_errs = crawl_channels_api(youtube, seed_pool, min(50, max_new - len(new_channel_ids)), all_existing_ids)
        run_errors.extend(crawl_errs)
        for cid in crawled_ids:
            channels[cid] = init_channel_stub(cid, 'Crawled Channel', 'crawl:subscriptions')
            new_channel_ids.add(cid)
            all_existing_ids.add(cid)
            total_channels += 1
            mode_stats['crawl'] += 1
    
    # API Exhaustion tracker
    api_exhausted = False
    
    # Setup rotation parameters (7, 30, 90 days, or None/All-Time)
    date_windows = [
        (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%dT00:00:00Z'),
        (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%dT00:00:00Z'),
        (datetime.now(timezone.utc) - timedelta(days=90)).strftime('%Y-%m-%dT00:00:00Z'),
        None # All-time
    ]
    search_orders = ['relevance', 'date', 'viewCount', 'rating']
    
    # Collect new channels
    for query in queries:
        if total_channels >= max_total or api_exhausted:
            break
            
        # Rotate search order, date window, and type for each query
        current_order = random.choice(search_orders)
        current_date_window = random.choice(date_windows)
        # Occasionally search for type='channel' directly (bypass date filters)
        search_types = ['video', 'channel'] if random.random() < 0.3 else ['video']
        
        for s_type in search_types:
            page_token = None
            page_count = 0
            while total_channels < max_total and page_count < 2: # Limit to 2 pages per query to spread quota
                if dry_run:
                    print(f"[DRY-RUN] Would search: query='{query}', type='{s_type}', order='{current_order}', publishedAfter='{current_date_window}'")
                    page_count = 2 # Stop after one "page" log
                    continue
                    
                try:
                    search_params = {
                        'q': query,
                        'type': s_type,
                        'part': 'snippet',
                        'maxResults': 50,
                        'order': current_order,
                        'pageToken': page_token
                    }
                    # Only apply date filter to 'video' searches (channels don't have publishedAfter in search.list)
                    if s_type == 'video' and current_date_window:
                        search_params['publishedAfter'] = current_date_window
                        
                    try:
                        search_request = youtube.search().list(**search_params)
                        search_response = search_request.execute()
                    except Exception as e:
                        if isinstance(e, HttpError): raise e
                        run_errors.append(f"Network error during search.list '{query}': {e}")
                        break
                        
                    searches_performed += 1
                    
                    niche = query.split(' ')[0]
                    for item in search_response.get('items', []):
                        if s_type == 'video':
                            channel_id = item['snippet']['channelId']
                            channel_name = item['snippet']['channelTitle']
                        else:
                            channel_id = item['snippet']['channelId']
                            channel_name = item['snippet']['title']
                            
                        if channel_id not in all_existing_ids:
                            channels[channel_id] = init_channel_stub(channel_id, channel_name, f"search:{query}")
                            new_channel_ids.add(channel_id)
                            all_existing_ids.add(channel_id)
                            total_channels += 1
                            mode_stats['search'] += 1
                            niche_performance[niche] = niche_performance.get(niche, 0) + 1
                            if total_channels >= max_total: break
                        else:
                            # Add overlapping query tagging (both for remote & newly discovered records)
                            c_data = channels[channel_id]
                            if c_data.get('is_remote'):
                                if query not in c_data['queries']:
                                    c_data['queries'].append(query)
                                    c_data['updated_queries'] = True
                            else:
                                if query not in c_data.get('queries', []):
                                    c_data.setdefault('queries', []).append(query)
                
                    page_token = search_response.get('nextPageToken')
                    page_count += 1
                    if not page_token or total_channels >= max_total:
                        break
                except HttpError as e:
                    try:
                        error_data = json.loads(e.content)
                        reason = error_data.get('error', {}).get('errors', [{}])[0].get('reason', 'unknown')
                        message = error_data.get('error', {}).get('message', 'No message')
                    except Exception:
                        reason = 'unknown'
                        message = str(e.content)
                    
                    if e.resp.status in [403, 429] and (reason == 'quotaExceeded' or 'quota' in message.lower()):
                        print(f"Quota exceeded. Stopping for today. (Reason: {reason})")
                        api_exhausted = True
                        break
                    else:
                        err_msg = f"[{e.resp.status}] {reason} - {message}"
                        print(f"Error searching for {query} ({s_type}): {err_msg}")
                        run_errors.append(err_msg)
                    break
    
    # Populate all new channels at the end
    if new_channel_ids and not dry_run:
        print(f"Batch populating details for {len(new_channel_ids)} newly discovered channels...")
        pop_errs = batch_populate_channels(youtube, new_channel_ids, channels, include_recent_date, include_avg_views)
        run_errors.extend(pop_errs)
        
    # Exclude any channels that failed to populate (if any)
    new_channel_ids = {cid for cid in new_channel_ids if channels[cid].get('populated', False)}
    
    # Final summary stats
    sample_names = []
    for cid in list(new_channel_ids)[:5]:
        if cid in channels:
            sample_names.append(channels[cid]['channel_name'])

    end_time = datetime.now(timezone.utc)
    duration_secs = (end_time - start_time).total_seconds()
    duration_str = f"{int(duration_secs // 60)}m {int(duration_secs % 60)}s"
    
    # Sort and get top 3 niches
    top_niches = sorted(niche_performance.items(), key=lambda x: x[1], reverse=True)[:3]

    summary = {
        'new_channels_found': len(new_channel_ids),
        'scrape_count': mode_stats['scrape'],
        'crawl_count': mode_stats['crawl'],
        'search_count': mode_stats['search'],
        'sample_channels': sample_names,
        'api_keys_used': 1,
        'total_keys': 1,
        'api_exhausted': api_exhausted,
        'errors': list(set(run_errors)), # Unique errors list
        'duration': duration_str,
        'searches_performed': searches_performed,
        'top_niches': top_niches
    }

    if dry_run:
        print("[DRY-RUN] Skipping Google Sheets/CSV write.")
        # Print summary and return early
        print("\n" + "="*40)
        print("       YOUTUBE SCRAPER DRY-RUN SUMMARY")
        print("="*40)
        print(f"Date Window:         Rotating (7d, 30d, 90d, All-Time)")
        print("="*40 + "\n")
        return

    if google_sheet and sheet_obj:
        if new_channel_ids:
            new_rows = []
            for channel_id in new_channel_ids:
                data = channels.get(channel_id)
                if not data: continue
                new_rows.append([
                    channel_id,
                    data['channel_name'],
                    data['channel_url'],
                    data.get('custom_url', ''),
                    data['subscribers'],
                    data.get('view_count', ''),
                    data.get('video_count', ''),
                    data.get('country', ''),
                    data.get('default_language', ''),
                    data.get('published_at', ''),
                    data['channel_description'],
                    ';'.join(data['emails']),
                    ';'.join(data['links']),
                    ';'.join(data.get('queries', [])),
                    data.get('recent_video_date', 'N/A'),
                    data.get('avg_views_last_month', 'N/A'),
                    data.get('discovered_at', ''),
                    data.get('description_language', 'unknown')
                ])
            try:
                # table_range="A1" ensures it anchors the append to column A, preventing horizontal shifting!
                sheet_obj.append_rows(new_rows, table_range="A1")
                print(f"Appended {len(new_rows)} new channels to Google Sheet: {google_sheet}")
            except Exception as e:
                print(f"Error appending row to Google Sheets: {e}")
        else:
            print("No new channels found to append.")
            
        # Update existing channels' queries if there were overlaps
        updates = []
        for channel_id, c_data in channels.items():
            if c_data.get('is_remote') and c_data.get('updated_queries'):
                cell_ref = f"N{c_data['row_idx']}"
                updates.append({
                    'range': cell_ref,
                    'values': [[';'.join(c_data['queries'])]]
                })
        
        if updates:
            try:
                sheet_obj.batch_update(updates)
                print(f"Updated query tags for {len(updates)} existing channels in the Google Sheet.")
            except Exception as e:
                print(f"Error batch updating queries: {e}")
                
        # Handle the new column header in the Google Sheet if it's missing
        try:
            header_row = sheet_obj.row_values(1)
            if 'description_language' not in header_row:
                # Add the new header to column R (18th column)
                sheet_obj.update_cell(1, 18, 'description_language')
                print("Added 'description_language' header to Google Sheet.")
        except Exception as e:
            print(f"Error updating header for description_language: {e}")
    
    else:
        # Write to local CSV
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for channel_id, data in channels.items():
                if not data: continue # Skip stubs loaded from sheets
                writer.writerow({
                    'channel_id': channel_id,
                    'channel_name': data['channel_name'],
                    'channel_url': data['channel_url'],
                    'custom_url': data.get('custom_url', ''),
                    'subscribers': data['subscribers'],
                    'view_count': data.get('view_count', ''),
                    'video_count': data.get('video_count', ''),
                    'country': data.get('country', ''),
                    'default_language': data.get('default_language', ''),
                    'published_at': data.get('published_at', ''),
                    'channel_description': data['channel_description'],
                    'emails': ';'.join(data['emails']),
                    'links': ';'.join(data['links']),
                    'queries': ';'.join(data.get('queries', [])),
                    'recent_video_date': data.get('recent_video_date', 'N/A'),
                    'avg_views_last_month': data.get('avg_views_last_month', 'N/A'),
                    'discovered_at': data.get('discovered_at', ''),
                    'description_language': data.get('description_language', 'unknown')
                })

    # Print Final Run Summary
    print("\n" + "="*40)
    print("       YOUTUBE SCRAPER RUN SUMMARY")
    print("="*40)
    print(f"New Channels Found:  {summary['new_channels_found']}")
    print(f"API Keys Used:       {summary['api_keys_used']} / {summary['total_keys']}")
    print(f"Quota Status:        {'EXHAUSTED' if summary['api_exhausted'] else 'OK'}")
    print(f"Date Window:         Rotating (7d, 30d, 90d, All-Time)")
    print("="*40 + "\n")
    
    # Send Discord notification (if webhook is provided in env)
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if webhook_url:
        send_discord_notification(webhook_url, summary)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', help='Single query to search (optional, overrides default list)')
    parser.add_argument('--max-channels', type=int, default=1000, help='Max new channels to add')
    parser.add_argument('--output', default='outputs/discovered_channels.csv', help='Output CSV file')
    parser.add_argument('--include-recent-date', action='store_true', help='Include most recent video date')
    parser.add_argument('--include-avg-views', action='store_true', help='Include average views last month')
    parser.add_argument('--existing-csv', help='Path to existing CSV with channel_id column')
    parser.add_argument('--api-key', help='YouTube Data API key', required=True)
    parser.add_argument('--google-sheet', help='Name of the Google Sheet (e.g. YT_Scraper_DB) to append to instead of saving CSV')
    parser.add_argument('--dry-run', action='store_true', help='Dry run: print search parameters without calling API')
    args = parser.parse_args()
    
    queries = [args.query] if args.query else QUERIES
    discover_channels(args.output, args.max_channels, queries, args.include_recent_date, args.include_avg_views, args.existing_csv, args.api_key, args.google_sheet, args.dry_run)