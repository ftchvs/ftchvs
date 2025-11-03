#!/usr/bin/env python3
"""
Fetch latest episodes from favorite podcasts and generate summaries.
Podcasts: All In, Pivot, Lenny Podcast, Joe Rogan (from YouTube).
"""

import os
import sys
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import requests
from openai import OpenAI


def get_openai_key() -> str:
    """Get OpenAI API key from environment."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    return key


def get_youtube_api_key() -> Optional[str]:
    """Get YouTube Data API key from environment."""
    return os.getenv("YOUTUBE_API_KEY")


def validate_url(url: str) -> bool:
    """Validate that a URL is properly formatted."""
    try:
        from urllib.parse import urlparse
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


# Podcast channel IDs or handles (can be found via YouTube API or channel URLs)
PODCAST_CHANNELS = {
    "All In": {
        "channel_id": "UCESLZhusAkFfsNsApnjF_Cg",  # All-In Podcast channel ID
        "search_terms": ["all in podcast", "all-in podcast", "chamath", "sacks", "friedberg", "calacanis"],
    },
    "Pivot": {
        "channel_handle": "pivot",  # Pivot with Kara Swisher and Scott Galloway - https://www.youtube.com/@pivot
        "search_terms": ["pivot podcast", "kara swisher", "scott galloway"],
    },
    "Lenny Podcast": {
        "channel_id": "UCfqYL1WGZ1YpBfXqOOc5YVQ",  # Lenny's Newsletter channel (may need adjustment)
        "search_terms": ["lenny podcast", "lenny rachitsky", "product management podcast"],
    },
    "Joe Rogan": {
        "channel_id": "UCzQUP1qoWDoEbmsQxvdjxgQ",  # Joe Rogan Experience channel ID
        "search_terms": ["joe rogan experience", "JRE"],
    },
}


def resolve_channel_id_from_handle(handle: str, api_key: str) -> Optional[str]:
    """Resolve a YouTube handle (e.g., 'pivot' or '@pivot') to a channel ID."""
    try:
        # Remove @ if present
        handle = handle.lstrip('@')
        
        channels_url = "https://www.googleapis.com/youtube/v3/channels"
        params = {
            "part": "id",
            "forHandle": handle,
            "key": api_key,
        }
        
        response = requests.get(channels_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("items", [])
        if items:
            return items[0].get("id")
        
        return None
    except Exception as e:
        print(f"Error resolving handle @{handle}: {e}", file=sys.stderr)
        return None


def fetch_latest_podcast_episode(channel_name: str, channel_info: Dict, api_key: str, days_back: int = 30) -> Optional[Dict]:
    """Fetch the latest episode from a podcast YouTube channel."""
    try:
        # Resolve channel ID if we have a handle
        channel_id = None
        if "channel_handle" in channel_info:
            channel_id = resolve_channel_id_from_handle(channel_info["channel_handle"], api_key)
            if not channel_id:
                print(f"Could not resolve channel handle for {channel_name}, falling back to search", file=sys.stderr)
                return fetch_latest_podcast_by_search(channel_name, channel_info, api_key, days_back)
        elif "channel_id" in channel_info:
            channel_id = channel_info["channel_id"]
        else:
            # No channel ID or handle, use search
            return fetch_latest_podcast_by_search(channel_name, channel_info, api_key, days_back)
        
        # Get videos from the channel using channel ID
        channel_url = "https://www.googleapis.com/youtube/v3/search"
        
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "maxResults": 10,
            "order": "date",
            "publishedAfter": (datetime.now() - timedelta(days=days_back)).isoformat() + "Z",
            "key": api_key,
        }
        
        response = requests.get(channel_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("items", [])
        
        if not items:
            # Try searching by channel name if channel ID doesn't work
            return fetch_latest_podcast_by_search(channel_name, channel_info, api_key, days_back)
        
        # Get the most recent video
        latest_video = items[0]
        snippet = latest_video.get("snippet", {})
        video_id = latest_video.get("id", {}).get("videoId", "")
        
        if not video_id:
            return None
        
        # Get video details for duration, view count, etc.
        video_url_api = "https://www.googleapis.com/youtube/v3/videos"
        video_params = {
            "part": "contentDetails,statistics",
            "id": video_id,
            "key": api_key,
        }
        
        video_response = requests.get(video_url_api, params=video_params, timeout=30)
        video_response.raise_for_status()
        video_data = video_response.json()
        
        video_details = video_data.get("items", [{}])[0] if video_data.get("items") else {}
        stats = video_details.get("statistics", {})
        
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        return {
            "title": snippet.get("title", ""),
            "url": video_url,
            "channel": channel_name,
            "published_at": snippet.get("publishedAt", ""),
            "description": snippet.get("description", "")[:500],  # First 500 chars
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            "views": int(stats.get("viewCount", 0)),
            "duration": video_details.get("contentDetails", {}).get("duration", ""),
        }
        
    except Exception as e:
        print(f"Error fetching {channel_name} podcast: {e}", file=sys.stderr)
        # Fallback to search
        return fetch_latest_podcast_by_search(channel_name, channel_info, api_key, days_back)


def fetch_latest_podcast_by_search(channel_name: str, channel_info: Dict, api_key: str, days_back: int = 30) -> Optional[Dict]:
    """Fallback: Fetch latest podcast episode by searching for channel name."""
    try:
        search_url = "https://www.googleapis.com/youtube/v3/search"
        
        # Use the first search term
        query = channel_info["search_terms"][0] if channel_info.get("search_terms") else channel_name
        
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": 5,
            "order": "date",
            "publishedAfter": (datetime.now() - timedelta(days=days_back)).isoformat() + "Z",
            "key": api_key,
        }
        
        response = requests.get(search_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("items", [])
        if not items:
            return None
        
        # Get the most recent video that matches our channel
        latest_video = items[0]
        snippet = latest_video.get("snippet", {})
        video_id = latest_video.get("id", {}).get("videoId", "")
        
        if not video_id:
            return None
        
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        return {
            "title": snippet.get("title", ""),
            "url": video_url,
            "channel": channel_name,
            "published_at": snippet.get("publishedAt", ""),
            "description": snippet.get("description", "")[:500],
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
        }
        
    except Exception as e:
        print(f"Error searching for {channel_name} podcast: {e}", file=sys.stderr)
        return None


def generate_podcast_summary(episode: Dict, api_key: str) -> str:
    """Generate a summary of a podcast episode using OpenAI."""
    if not episode:
        return ""
    
    prompt = f"""Summarize this podcast episode in 2-3 sentences. Focus on the key topics, insights, or discussions covered:

Title: {episode.get('title', 'Unknown')}
Channel: {episode.get('channel', 'Unknown')}
Description: {episode.get('description', 'No description available')[:800]}

Provide a concise summary of what was discussed in this episode."""

    try:
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a podcast summary writer who creates concise, informative summaries of podcast episodes."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7,
        )
        
        summary = response.choices[0].message.content.strip()
        return summary
        
    except Exception as e:
        print(f"Error generating podcast summary: {e}", file=sys.stderr)
        return f"Latest episode: {episode.get('title', 'Unknown')}"


def format_podcasts_markdown(podcasts: List[Dict], date: str) -> str:
    """Format podcast summaries as markdown."""
    if not podcasts:
        return f"## 🎙️ Podcast Summaries - {date}\n\nNo recent podcast episodes found."
    
    lines = [
        f"## 🎙️ Podcast Summaries - {date}",
        "",
    ]
    
    for podcast in podcasts:
        episode = podcast.get("episode", {})
        summary = podcast.get("summary", "")
        
        if not episode:
            continue
        
        # Format published date if available
        pub_date = ""
        if episode.get("published_at"):
            try:
                pub_dt = datetime.fromisoformat(episode["published_at"].replace("Z", "+00:00"))
                pub_date = pub_dt.strftime("%Y-%m-%d")
            except:
                pub_date = ""
        
        lines.append(f"### {episode.get('channel', 'Unknown')} - {episode.get('title', 'Unknown')}")
        if pub_date:
            lines.append(f"*Published: {pub_date}*")
        lines.append("")
        
        if summary:
            lines.append(summary)
            lines.append("")
        
        video_url = episode.get("url", "")
        if video_url and validate_url(video_url):
            lines.append(f"[Watch on YouTube]({video_url})")
        
        lines.append("")
        lines.append("---")
        lines.append("")
    
    return "\n".join(lines)


def main():
    """Main execution function."""
    try:
        openai_key = get_openai_key()
        youtube_key = get_youtube_api_key()
        
        if not youtube_key:
            print("YOUTUBE_API_KEY not found. Skipping podcast summaries.", file=sys.stderr)
            date_str = datetime.now().strftime("%Y-%m-%d")
            fallback = {
                "date": date_str,
                "markdown": f"## 🎙️ Podcast Summaries - {date_str}\n\n*YouTube API key required. Please configure YOUTUBE_API_KEY in environment.*\n",
                "podcasts": [],
            }
            print(json.dumps(fallback))
            sys.exit(0)
        
        podcasts = []
        
        for channel_name, channel_info in PODCAST_CHANNELS.items():
            print(f"Fetching latest episode from {channel_name}...", file=sys.stderr)
            episode = fetch_latest_podcast_episode(channel_name, channel_info, youtube_key, days_back=30)
            
            if episode:
                print(f"Found episode: {episode.get('title', 'Unknown')}", file=sys.stderr)
                print(f"Generating summary for {channel_name}...", file=sys.stderr)
                summary = generate_podcast_summary(episode, openai_key)
                
                podcasts.append({
                    "channel": channel_name,
                    "episode": episode,
                    "summary": summary,
                })
            else:
                print(f"No recent episode found for {channel_name}", file=sys.stderr)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        markdown = format_podcasts_markdown(podcasts, date_str)
        
        # Output JSON for other scripts to consume
        output = {
            "date": date_str,
            "markdown": markdown,
            "podcasts": podcasts,
        }
        
        print(json.dumps(output))
        
    except ValueError as e:
        # Missing API key
        print(f"Configuration Error: {e}", file=sys.stderr)
        date_str = datetime.now().strftime("%Y-%m-%d")
        fallback = {
            "date": date_str,
            "markdown": f"## 🎙️ Podcast Summaries - {date_str}\n\n*Error: {str(e)}. Please configure required API keys.*\n",
            "podcasts": [],
        }
        print(json.dumps(fallback))
        sys.exit(1)
    except Exception as e:
        # Other errors
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
        date_str = datetime.now().strftime("%Y-%m-%d")
        fallback = {
            "date": date_str,
            "markdown": f"## 🎙️ Podcast Summaries - {date_str}\n\n*Error fetching podcasts: {str(e)}*\n",
            "podcasts": [],
        }
        print(json.dumps(fallback))
        sys.exit(1)


if __name__ == "__main__":
    main()

