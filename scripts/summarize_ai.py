#!/usr/bin/env python3
"""
Fetch top AI stories from multiple sources (Hacker News, Reddit, TechCrunch)
and generate AI summary via OpenAI.
"""

import os
import sys
import json
from typing import List, Dict, Optional
from urllib.parse import urlparse
from datetime import datetime, timedelta
import requests
import feedparser
from openai import OpenAI


def get_openai_key() -> str:
    """Get OpenAI API key from environment."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    return key


def validate_url(url: str) -> bool:
    """Validate that a URL is properly formatted."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def ensure_hn_url(object_id: Optional[str], title: str = "") -> str:
    """Ensure we have a valid Hacker News URL, create one if objectID is missing."""
    if object_id:
        hn_url = f"https://news.ycombinator.com/item?id={object_id}"
        if validate_url(hn_url):
            return hn_url
    
    # Fallback: search HN for the story (though this won't work perfectly)
    # For now, return a valid HN URL structure even if objectID is missing
    # This ensures we always have a valid URL format
    return "https://news.ycombinator.com/newest"  # Safe fallback


def fetch_hacker_news_ai_stories(limit: int = 5) -> List[Dict]:
    """Fetch top AI-related stories from Hacker News via Algolia API."""
    # Hacker News Algolia search API
    url = "https://hn.algolia.com/api/v1/search"
    
    params = {
        "query": "AI artificial intelligence machine learning LLM",
        "tags": "story",
        "numericFilters": "created_at_i>0",
        "hitsPerPage": limit * 2,  # Get more to filter
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        hits = data.get("hits", [])
        
        # Filter for AI-related stories (title contains AI keywords)
        ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", "anthropic", "claude", "neural", "deep learning"]
        ai_stories = []
        
        for hit in hits:
            title = hit.get("title", "").lower()
            if any(keyword in title for keyword in ai_keywords):
                object_id = hit.get("objectID")
                title_text = hit.get("title", "")
                
                # Ensure we always have a valid HN URL
                hn_url = ensure_hn_url(object_id, title_text)
                
                # Validate external URL if present, otherwise use HN URL
                external_url = hit.get("url", "")
                if external_url and validate_url(external_url):
                    final_url = external_url
                else:
                    final_url = hn_url
                
                ai_stories.append({
                    "title": title_text,
                    "url": final_url,
                    "points": hit.get("points", 0),
                    "comments": hit.get("num_comments", 0),
                    "author": hit.get("author", ""),
                    "hn_url": hn_url,  # Always use HN URL as primary link
                    "objectID": object_id,  # Store for reference
                })
                
                if len(ai_stories) >= limit:
                    break
        
        return ai_stories[:limit]
        
    except Exception as e:
        print(f"Error fetching Hacker News stories: {e}", file=sys.stderr)
        return []


def fetch_reddit_ai_stories(limit: int = 5) -> List[Dict]:
    """Fetch top AI-related stories from Reddit (r/MachineLearning, r/artificial)."""
    subreddits = ["MachineLearning", "artificial", "singularity", "artificial_intelligence"]
    ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", "anthropic", "claude", "neural", "deep learning"]
    all_stories = []
    
    headers = {
        "User-Agent": "AI-News-Aggregator/1.0 (contact: ftchvs)"
    }
    
    for subreddit in subreddits:
        try:
            # Reddit JSON API (no auth required for public access)
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            posts = data.get("data", {}).get("children", [])
            
            for post in posts:
                post_data = post.get("data", {})
                title = post_data.get("title", "").lower()
                
                # Filter for AI-related content
                if any(keyword in title for keyword in ai_keywords):
                    reddit_url = f"https://www.reddit.com{post_data.get('permalink', '')}"
                    external_url = post_data.get("url_overridden_by_dest", "")
                    
                    # Use external URL if valid, otherwise Reddit discussion
                    if external_url and validate_url(external_url) and "reddit.com" not in external_url:
                        final_url = external_url
                    else:
                        final_url = reddit_url
                    
                    all_stories.append({
                        "title": post_data.get("title", ""),
                        "url": final_url,
                        "points": post_data.get("score", 0),
                        "comments": post_data.get("num_comments", 0),
                        "author": post_data.get("author", ""),
                        "hn_url": reddit_url,  # Reddit discussion as backup
                        "source": f"r/{subreddit}",
                        "subreddit": subreddit,
                    })
                    
        except Exception as e:
            print(f"Error fetching from r/{subreddit}: {e}", file=sys.stderr)
            continue
    
    # Sort by score (points) and return top stories
    all_stories.sort(key=lambda x: x.get("points", 0), reverse=True)
    return all_stories[:limit]


def fetch_techcrunch_ai_stories(limit: int = 5) -> List[Dict]:
    """Fetch AI-related stories from TechCrunch RSS feed."""
    try:
        import feedparser
        
        # TechCrunch AI tag RSS feed
        rss_url = "https://techcrunch.com/tag/artificial-intelligence/feed/"
        
        feed = feedparser.parse(rss_url)
        
        if feed.bozo:
            print(f"Warning: Feed parsing issue: {feed.bozo_exception}", file=sys.stderr)
        
        ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", "anthropic", "claude", "neural", "deep learning"]
        stories = []
        
        # Get entries from last 24 hours
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        
        for entry in feed.entries:
            title = entry.get("title", "").lower()
            published = entry.get("published_parsed")
            
            # Check if AI-related
            if any(keyword in title for keyword in ai_keywords):
                # Check date if available
                if published:
                    pub_date = datetime(*published[:6])
                    if pub_date < day_ago:
                        continue  # Skip if older than 24 hours
                
                link = entry.get("link", "")
                
                stories.append({
                    "title": entry.get("title", ""),
                    "url": link if validate_url(link) else "https://techcrunch.com",
                    "points": 0,  # RSS feeds don't have upvotes
                    "comments": 0,
                    "author": entry.get("author", "TechCrunch"),
                    "hn_url": link if validate_url(link) else "https://techcrunch.com",
                    "source": "TechCrunch",
                })
        
        return stories[:limit]
        
    except Exception as e:
        print(f"Error fetching TechCrunch stories: {e}", file=sys.stderr)
        return []


def get_source_priority(source: str) -> int:
    """Get priority value for source (lower number = higher priority)."""
    source_lower = source.lower()
    if "techcrunch" in source_lower:
        return 1  # Highest priority
    elif "reddit" in source_lower or source_lower.startswith("r/"):
        return 2  # Second priority
    elif "hacker news" in source_lower or "hn" in source_lower:
        return 3  # Lowest priority
    return 4  # Unknown sources


def deduplicate_stories(all_stories: List[Dict]) -> List[Dict]:
    """Remove duplicate stories based on title similarity, prioritizing Reddit and TechCrunch."""
    seen_titles = set()
    unique_stories = []
    
    # Process stories in priority order: TechCrunch > Reddit > Hacker News
    # Sort by source priority first, then process
    all_stories_sorted = sorted(all_stories, key=lambda x: get_source_priority(x.get("source", "Unknown")))
    
    for story in all_stories_sorted:
        # Normalize title for comparison (lowercase, remove extra spaces)
        title_key = story.get("title", "").lower().strip()
        
        # Check if we've seen a similar title (simple substring matching)
        is_duplicate = False
        for seen_title in seen_titles:
            # If one title contains the other (or vice versa), consider it duplicate
            if title_key in seen_title or seen_title in title_key:
                is_duplicate = True
                break
        
        if not is_duplicate:
            seen_titles.add(title_key)
            unique_stories.append(story)
    
    # Sort by source priority first, then by engagement (points/comments)
    unique_stories.sort(key=lambda x: (
        get_source_priority(x.get("source", "Unknown")),  # Priority: TechCrunch (1) > Reddit (2) > HN (3)
        -x.get("points", 0),  # Higher points = better (negative for descending)
        -x.get("comments", 0)  # Higher comments = better (negative for descending)
    ))
    
    return unique_stories


def generate_ai_summary(stories: List[Dict], api_key: str) -> str:
    """Generate AI summary of the top AI stories using OpenAI."""
    if not stories:
        return "No AI stories found today."
    
    # Format stories for the prompt with source info
    stories_text = "\n\n".join([
        f"{i+1}. {story['title']} ({story.get('source', 'Unknown')})"
        for i, story in enumerate(stories)
    ])
    
    prompt = f"""Based on these top AI stories from Hacker News, Reddit, and TechCrunch, provide a concise 2-3 sentence summary of the key AI trends and developments:

{stories_text}

Summarize the main themes, breakthroughs, or noteworthy developments in the AI space today."""

    try:
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a technical writer who summarizes AI industry news concisely and accurately."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.7,
        )
        
        summary = response.choices[0].message.content.strip()
        return summary
        
    except Exception as e:
        print(f"Error generating AI summary: {e}", file=sys.stderr)
        # Fallback to simple summary
        sources = set(s.get('source', 'Unknown') for s in stories)
        return f"Today's top AI stories cover {len(stories)} trending topics from {', '.join(sorted(sources))}."


def format_ai_markdown(stories: List[Dict], summary: str, date: str) -> str:
    """Format AI news section as markdown."""
    lines = [
        f"## 🤖 AI Industry Snapshot - {date}",
        "",
        "### Top AI Stories",
        "",
    ]
    
    for i, story in enumerate(stories, 1):
        # Use the primary URL (hn_url for HN/Reddit, or url for others)
        # This ensures we always have a valid link
        primary_url = story.get('hn_url') or story.get('url', 'https://news.ycombinator.com/newest')
        
        # Double-check URL is valid before using it
        if not validate_url(primary_url):
            primary_url = 'https://news.ycombinator.com/newest'  # Safe fallback
        
        lines.append(f"{i}. [{story['title']}]({primary_url})")
        lines.append("")
    
    lines.extend([
        "### AI Trends Summary",
        "",
        summary,
        "",
    ])
    
    return "\n".join(lines)


def main():
    """Main execution function."""
    try:
        openai_key = get_openai_key()
        
        all_stories = []
        
        # Fetch from Reddit (priority source)
        print("Fetching AI stories from Reddit...", file=sys.stderr)
        reddit_stories = fetch_reddit_ai_stories(limit=5)
        all_stories.extend(reddit_stories)
        print(f"Found {len(reddit_stories)} stories from Reddit", file=sys.stderr)
        
        # Fetch from TechCrunch (priority source)
        print("Fetching AI stories from TechCrunch...", file=sys.stderr)
        tc_stories = fetch_techcrunch_ai_stories(limit=5)
        all_stories.extend(tc_stories)
        print(f"Found {len(tc_stories)} stories from TechCrunch", file=sys.stderr)
        
        # Fetch from Hacker News (lower priority)
        print("Fetching AI stories from Hacker News...", file=sys.stderr)
        hn_stories = fetch_hacker_news_ai_stories(limit=5)
        for story in hn_stories:
            story['source'] = 'Hacker News'
        all_stories.extend(hn_stories)
        print(f"Found {len(hn_stories)} stories from Hacker News", file=sys.stderr)
        
        # Deduplicate and select top stories
        unique_stories = deduplicate_stories(all_stories)
        top_stories = unique_stories[:5]  # Take top 5 after deduplication
        
        if not top_stories:
            print("Warning: No AI stories found. Generating fallback summary.", file=sys.stderr)
            summary = "No AI stories found today. Check back tomorrow for the latest AI developments."
        else:
            print(f"Total unique stories: {len(top_stories)}", file=sys.stderr)
            print("Generating AI summary...", file=sys.stderr)
            summary = generate_ai_summary(top_stories, openai_key)
        
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        markdown = format_ai_markdown(top_stories, summary, date_str)
        
        # Output JSON for other scripts to consume (to stdout only)
        output = {
            "date": date_str,
            "markdown": markdown,
            "stories": top_stories,
            "summary": summary,
        }
        
        print(json.dumps(output))
        
    except ValueError as e:
        # Missing API key
        print(f"Configuration Error: {e}", file=sys.stderr)
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        fallback = {
            "date": date_str,
            "markdown": f"## 🤖 AI Industry Snapshot - {date_str}\n\n*Error: {str(e)}. Please configure OPENAI_API_KEY in GitHub secrets.*\n",
            "stories": [],
            "summary": ""
        }
        print(json.dumps(fallback))
        sys.exit(1)
    except Exception as e:
        # Other errors
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        fallback = {
            "date": date_str,
            "markdown": f"## 🤖 AI Industry Snapshot - {date_str}\n\n*Error fetching AI news: {str(e)}*\n",
            "stories": [],
            "summary": ""
        }
        print(json.dumps(fallback))
        sys.exit(1)


if __name__ == "__main__":
    main()

