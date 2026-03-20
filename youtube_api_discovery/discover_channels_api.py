"""
discover_channels_api.py

Discover YouTube channels related to card games, roguelike games, Steam Next Fest, and indie/demo games.
Fetch channel descriptions and extract emails using YouTube Data API v3.
Output CSV with channel info and emails, or append directly to a Google Sheet.
"""

import csv
import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

import random

def generate_queries():
    """Procedurally generate an infinite matrix of unique gaming queries."""
    topics = [
        "hearthstone", "magic the gathering", "pokemon tcg", "yu-gi-oh", 
        "slay the spire", "balatro", "hades", "binding of isaac", "roblox", 
        "marvel snap", "gwent", "legends of runeterra", "inscryption", 
        "monster train", "deckbuilder", "indie game", "roguelike", 
        "roguelite", "metroidvania", "gacha", "rpg maker", 
        "cozy game", "pixel art", "survivor.io", "strategy card"
    ]
    modifiers = [
        "gameplay", "demo", "review", "showcase", "devlog", "trailer", 
        "speedrun", "hidden gem", "walkthrough", "let's play", "tips", 
        "guide", "box break", "packs", "pulls", "beta", "early access",
        "first impressions", "update", "new content"
    ]
    
    # Generate cross-product (e.g. "roblox devlog", "hades speedrun") = 500+ combos
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

class YouTubeAPIClient:
    def __init__(self, api_keys):
        self.api_keys = [k.strip() for k in api_keys if k.strip()]
        self.current_idx = 0
        if not self.api_keys:
            raise ValueError("No valid API keys.")
        self.client = build('youtube', 'v3', developerKey=self.api_keys[self.current_idx])

    def get(self):
        return self.client

    def next(self):
        self.current_idx += 1
        if self.current_idx >= len(self.api_keys):
            raise Exception("All API keys exhausted.")
        self.client = build('youtube', 'v3', developerKey=self.api_keys[self.current_idx])
        return self.client

def get_gspread_client(creds_file="google_credentials.json"):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
    client = gspread.authorize(creds)
    return client

def discover_channels(output_file, max_new=1000, queries=None, include_recent_date=False, include_avg_views=False, existing_csv=None, api_keys=None, google_sheet=None):
    if queries is None:
        queries = QUERIES
        
    yt_manager = YouTubeAPIClient(api_keys)
    youtube = yt_manager.get()
    
    channels = {}
    new_channel_ids = set()
    sheet_obj = None
    
    fieldnames = [
        'channel_id', 'channel_name', 'channel_url', 'custom_url', 'subscribers', 
        'view_count', 'video_count', 'country', 'default_language', 'published_at',
        'channel_description', 'emails', 'links', 'queries', 
        'recent_video_date', 'avg_views_last_month'
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
    
    # Collect new channels
    for query in queries:
        if total_channels >= max_total:
            break
        page_token = None
        while total_channels < max_total:
            try:
                search_request = youtube.search().list(
                    q=query,
                    type='video',
                    part='snippet',
                    maxResults=50,
                    order='relevance',
                    pageToken=page_token
                )
                search_response = search_request.execute()
                
                for item in search_response['items']:
                    channel_id = item['snippet']['channelId']
                    if channel_id not in channels:
                        channels[channel_id] = {
                            'channel_name': item['snippet']['channelTitle'],
                            'channel_url': f'https://www.youtube.com/channel/{channel_id}',
                            'channel_description': '',
                            'emails': [],
                            'links': [],
                            'subscribers': 'N/A',
                            'recent_video_date': 'N/A',
                            'avg_views_last_month': 'N/A',
                            'queries': [query],
                            'custom_url': '',
                            'country': '',
                            'default_language': '',
                            'published_at': '',
                            'view_count': '',
                            'video_count': ''
                        }
                        new_channel_ids.add(channel_id)
                        total_channels += 1
                        if total_channels >= max_total:
                            break
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
                if not page_token or total_channels >= max_total:
                    break
            except HttpError as e:
                if e.resp.status in [403, 429]:
                    print(f"Quota exceeded backing off or swapping keys...")
                    try:
                        youtube = yt_manager.next()
                        print("Swapped to next API key.")
                        continue
                    except Exception:
                        print("All keys exhausted.")
                        break
                else:
                    print(f"Error searching for {query}: {e}")
                break
    
    # Fetch descriptions and stats for new channels only
    for channel_id in list(new_channel_ids):
        data = channels[channel_id]
        if not data.get('channel_description'):
            try:
                channel_request = youtube.channels().list(
                    part='snippet,statistics',
                    id=channel_id
                )
                channel_response = channel_request.execute()
                if 'items' in channel_response and channel_response['items']:
                    item = channel_response['items'][0]
                    
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
                    
                    if include_recent_date:
                        recent_request = youtube.search().list(
                            channelId=channel_id,
                            type='video',
                            part='snippet',
                            order='date',
                            maxResults=1
                        )
                        recent_response = recent_request.execute()
                        if recent_response['items']:
                            data['recent_video_date'] = recent_response['items'][0]['snippet']['publishedAt']
                    
                    if include_avg_views:
                        one_month_ago = (datetime.utcnow() - timedelta(days=30)).isoformat() + 'Z'
                        views_request = youtube.search().list(
                            channelId=channel_id,
                            type='video',
                            part='id',
                            publishedAfter=one_month_ago,
                            maxResults=50
                        )
                        views_response = views_request.execute()
                        video_ids = [vid['id']['videoId'] for vid in views_response['items']]
                        if video_ids:
                            videos_request = youtube.videos().list(
                                part='statistics',
                                id=','.join(video_ids)
                            )
                            videos_response = videos_request.execute()
                            total_views = sum(int(video['statistics'].get('viewCount', 0)) for video in videos_response['items'])
                            data['avg_views_last_month'] = total_views / len(videos_response['items']) if videos_response['items'] else 'N/A'
            except HttpError as e:
                if e.resp.status in [403, 429]:
                    try:
                        youtube = yt_manager.next()
                    except Exception:
                        pass
                print(f"Error fetching channel {channel_id}: {e}")
                continue
    
    # Write to Google Sheet contextually
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
                    data['recent_video_date'],
                    data['avg_views_last_month']
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
                    'recent_video_date': data['recent_video_date'],
                    'avg_views_last_month': data['avg_views_last_month']
                })

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', help='Single query to search (optional, overrides default list)')
    parser.add_argument('--max-channels', type=int, default=1000, help='Max new channels to add')
    parser.add_argument('--output', default='outputs/discovered_channels.csv', help='Output CSV file')
    parser.add_argument('--include-recent-date', action='store_true', help='Include most recent video date')
    parser.add_argument('--include-avg-views', action='store_true', help='Include average views last month')
    parser.add_argument('--existing-csv', help='Path to existing CSV with channel_id column')
    parser.add_argument('--api-keys', help='Comma-separated YouTube API keys', required=True)
    parser.add_argument('--google-sheet', help='Name of the Google Sheet (e.g. YT_Scraper_DB) to append to instead of saving CSV')
    args = parser.parse_args()
    
    queries = [args.query] if args.query else QUERIES
    keys = [k.strip() for k in args.api_keys.split(',')]
    discover_channels(args.output, args.max_channels, queries, args.include_recent_date, args.include_avg_views, args.existing_csv, keys, args.google_sheet)