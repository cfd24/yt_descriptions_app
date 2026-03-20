"""
discover_channels_api.py

Discover YouTube channels related to card games, roguelike games, Steam Next Fest, and indie/demo games.
Fetch channel descriptions and extract emails using YouTube Data API v3.
Output CSV with channel info and emails.
"""

import csv
import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
from datetime import datetime, timedelta

# Default Queries for discovery
QUERIES = [
    "hearthstone", "magic the gathering", "pokemon card game",
    "slay the spire", "balatro", "hades game", "binding of isaac",
    "steam next fest", "indie games", "demo games", "new games"
]

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

def discover_channels(output_file, max_new=1000, queries=None, include_recent_date=False, include_avg_views=False, existing_csv=None, api_keys=None):
    if queries is None:
        queries = QUERIES
        
    yt_manager = YouTubeAPIClient(api_keys)
    youtube = yt_manager.get()
    
    # Load existing channel IDs to skip duplicates
    channels = {}
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
    
    max_total = len(channels) + max_new  # Allow unlimited existing, add up to max_new new
    total_channels = len(channels)
    
    # Collect new channels (skip if already in channels)
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
                        total_channels += 1
                        if total_channels >= max_total:
                            break
                    else:
                        # Add overlapping query tagging
                        if query not in channels[channel_id].get('queries', []):
                            channels[channel_id].setdefault('queries', []).append(query)
                
                page_token = search_response.get('nextPageToken')
                if not page_token or total_channels >= max_total:
                    break
            except HttpError as e:
                if e.resp.status in [403, 429]:  # Quota exceeded or too many requests
                    print(f"Quota exceeded backing off or swapping keys...")
                    try:
                        youtube = yt_manager.next()
                        print("Swapped to next API key.")
                        continue  # Retry with new key
                    except Exception:
                        print("All keys exhausted.")
                        break
                else:
                    print(f"Error searching for {query}: {e}")
                break
    
    # Fetch descriptions and stats for new channels only (existing already have data)
    for channel_id, data in list(channels.items())[:max_total]:
        if not data['channel_description']:  # Only fetch if not already loaded
            try:
                channel_request = youtube.channels().list(
                    part='snippet,statistics',
                    id=channel_id
                )
                channel_response = channel_request.execute()
                if 'items' in channel_response and channel_response['items']:
                    item = channel_response['items'][0]
                    
                    # Extract everything from snippet/statistics
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
    
    # Write to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'channel_id', 'channel_name', 'channel_url', 'custom_url', 'subscribers', 
            'view_count', 'video_count', 'country', 'default_language', 'published_at',
            'channel_description', 'emails', 'links', 'queries', 
            'recent_video_date', 'avg_views_last_month'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for channel_id, data in channels.items():
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
    args = parser.parse_args()
    
    queries = [args.query] if args.query else QUERIES
    keys = [k.strip() for k in args.api_keys.split(',')]
    discover_channels(args.output, args.max_channels, queries, args.include_recent_date, args.include_avg_views, args.existing_csv, keys)