#!/usr/bin/env python3
"""
Fetch content from multiple sources:
- AI News (Hacker News, Reddit, TechCrunch)
- Business News (CNN, Fox News, NBC, WSJ, NYTimes)
- Tech News (TechCrunch, Hacker News, Reddit)
- Motivation Quotes (Reddit subreddits)
- Wise Knowledge (Reddit subreddits)
Generate summaries via OpenAI and archive logs.
"""

import os
import sys
import json
import time
from typing import List, Dict, Optional
from urllib.parse import urlparse
from datetime import datetime, timedelta
import requests
import feedparser
from openai import OpenAI

# Try to import Firecrawl, but make it optional
try:
    from firecrawl import FirecrawlApp
    FIRECRAWL_AVAILABLE = True
except ImportError:
    FIRECRAWL_AVAILABLE = False


# Reddit API headers - Reddit requires a descriptive User-Agent
REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DailyDigestBot/1.0; +https://github.com/ftchvs/ftchvs) by /u/ftchvs"
}


def get_openai_key() -> str:
    """Get OpenAI API key from environment."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    return key


def get_firecrawl_key() -> Optional[str]:
    """Get Firecrawl API key from environment (optional)."""
    return os.getenv("FIRECRAWL_API_KEY")


def validate_url(url: str) -> bool:
    """Validate that a URL is properly formatted."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def ensure_hn_url(object_id: Optional[str], title: str = "") -> str:
    """Ensure we have a valid Hacker News URL."""
    if object_id:
        hn_url = f"https://news.ycombinator.com/item?id={object_id}"
        if validate_url(hn_url):
            return hn_url
    return "https://news.ycombinator.com/newest"


# ============ AI NEWS FUNCTIONS ============

def fetch_hacker_news_ai_stories(limit: int = 5) -> List[Dict]:
    """Fetch top AI-related stories from Hacker News via Algolia API."""
    url = "https://hn.algolia.com/api/v1/search"
    
    params = {
        "query": "AI artificial intelligence machine learning LLM",
        "tags": "story",
        "numericFilters": "created_at_i>0",
        "hitsPerPage": limit * 2,
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        hits = data.get("hits", [])
        ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", "anthropic", "claude", "neural", "deep learning"]
        ai_stories = []
        
        for hit in hits:
            title = hit.get("title", "").lower()
            if any(keyword in title for keyword in ai_keywords):
                object_id = hit.get("objectID")
                title_text = hit.get("title", "")
                hn_url = ensure_hn_url(object_id, title_text)
                external_url = hit.get("url", "")
                
                final_url = external_url if (external_url and validate_url(external_url)) else hn_url
                
                ai_stories.append({
                    "title": title_text,
                    "url": final_url,
                    "points": hit.get("points", 0),
                    "comments": hit.get("num_comments", 0),
                    "author": hit.get("author", ""),
                    "hn_url": hn_url,
                    "source": "Hacker News",
                })
                
                if len(ai_stories) >= limit:
                    break
        
        return ai_stories[:limit]
        
    except Exception as e:
        print(f"Error fetching Hacker News AI stories: {e}", file=sys.stderr)
        return []


def fetch_reddit_ai_stories(limit: int = 5) -> List[Dict]:
    """Fetch top AI-related stories from Reddit."""
    # AI-specific subreddits - all posts are relevant
    ai_subreddits = ["MachineLearning", "artificial", "singularity", "artificial_intelligence", "LocalLLaMA", "ChatGPT", "GPT3"]
    # General tech subreddits where we need keyword filtering
    general_subreddits = ["technology", "programming", "computerscience"]
    ai_keywords = [
        "ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", 
        "anthropic", "claude", "neural", "deep learning", "transformer", "diffusion",
        "generative ai", "genai", "langchain", "prompt engineering", "agent", "agi"
    ]
    all_stories = []
    
    # Fetch from AI-specific subreddits (include all posts since they're AI-focused)
    for subreddit in ai_subreddits:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
            response = requests.get(url, headers=REDDIT_HEADERS, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                print(f"Reddit API error for r/{subreddit}: {data.get('message', 'Unknown error')}", file=sys.stderr)
                continue
            
            posts = data.get("data", {}).get("children", [])
            print(f"Fetched {len(posts)} posts from r/{subreddit}", file=sys.stderr)
            
            for post in posts:
                post_data = post.get("data", {})
                
                # Skip stickied/pinned posts
                if post_data.get("stickied", False):
                    continue
                
                # Skip deleted/removed posts
                if post_data.get("selftext") in ["[deleted]", "[removed]"]:
                    continue
                
                reddit_url = f"https://www.reddit.com{post_data.get('permalink', '')}"
                external_url = post_data.get("url_overridden_by_dest", "")
                
                final_url = external_url if (external_url and validate_url(external_url) and "reddit.com" not in external_url) else reddit_url
                
                all_stories.append({
                    "title": post_data.get("title", ""),
                    "url": final_url,
                    "points": post_data.get("score", 0),
                    "comments": post_data.get("num_comments", 0),
                    "author": post_data.get("author", ""),
                    "source": f"r/{subreddit}",
                })
            
            # Rate limiting for Reddit
            time.sleep(0.5)
                    
        except requests.exceptions.RequestException as e:
            print(f"Request error fetching from r/{subreddit}: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"Error fetching from r/{subreddit}: {e}", file=sys.stderr)
            continue
    
    # Fetch from general subreddits with keyword filtering
    for subreddit in general_subreddits:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
            response = requests.get(url, headers=REDDIT_HEADERS, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                continue
            
            posts = data.get("data", {}).get("children", [])
            
            for post in posts:
                post_data = post.get("data", {})
                
                if post_data.get("stickied", False):
                    continue
                
                title = post_data.get("title", "").lower()
                selftext = post_data.get("selftext", "").lower()
                
                # Check if AI-related in title or selftext
                content = title + " " + selftext
                if any(keyword in content for keyword in ai_keywords):
                    reddit_url = f"https://www.reddit.com{post_data.get('permalink', '')}"
                    external_url = post_data.get("url_overridden_by_dest", "")
                    
                    final_url = external_url if (external_url and validate_url(external_url) and "reddit.com" not in external_url) else reddit_url
                    
                    all_stories.append({
                        "title": post_data.get("title", ""),
                        "url": final_url,
                        "points": post_data.get("score", 0),
                        "comments": post_data.get("num_comments", 0),
                        "author": post_data.get("author", ""),
                        "source": f"r/{subreddit}",
                    })
            
            time.sleep(0.5)
                    
        except Exception as e:
            print(f"Error fetching from r/{subreddit}: {e}", file=sys.stderr)
            continue
    
    # Sort by score and return top stories
    all_stories.sort(key=lambda x: x.get("points", 0), reverse=True)
    print(f"Total Reddit AI stories found: {len(all_stories)}", file=sys.stderr)
    return all_stories[:limit]


def fetch_techcrunch_ai_stories(limit: int = 5) -> List[Dict]:
    """Fetch AI-related stories from TechCrunch RSS feed."""
    try:
        rss_url = "https://techcrunch.com/tag/artificial-intelligence/feed/"
        feed = feedparser.parse(rss_url)
        
        if feed.bozo:
            print(f"Warning: Feed parsing issue: {feed.bozo_exception}", file=sys.stderr)
        
        ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", "anthropic", "claude", "neural", "deep learning"]
        stories = []
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        
        for entry in feed.entries:
            title = entry.get("title", "").lower()
            published = entry.get("published_parsed")
            
            if any(keyword in title for keyword in ai_keywords):
                if published:
                    pub_date = datetime(*published[:6])
                    if pub_date < day_ago:
                        continue
                
                link = entry.get("link", "")
                stories.append({
                    "title": entry.get("title", ""),
                    "url": link if validate_url(link) else "https://techcrunch.com",
                    "points": 0,
                    "comments": 0,
                    "author": entry.get("author", "TechCrunch"),
                    "source": "TechCrunch",
                })
        
        return stories[:limit]
        
    except Exception as e:
        print(f"Error fetching TechCrunch AI stories: {e}", file=sys.stderr)
        return []


def fetch_youtube_ai_stories(limit: int = 5) -> List[Dict]:
    """Fetch AI-related videos from YouTube."""
    ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", "anthropic", "claude", "neural", "deep learning"]
    stories = []
    
    try:
        youtube_api_key = os.getenv("YOUTUBE_API_KEY")
        if not youtube_api_key:
            return []
        
        search_url = "https://www.googleapis.com/youtube/v3/search"
        
        params = {
            "part": "snippet",
            "q": "AI artificial intelligence machine learning LLM",
            "type": "video",
            "maxResults": limit * 2,
            "order": "relevance",
            "publishedAfter": (datetime.now() - timedelta(days=7)).isoformat() + "Z",
            "key": youtube_api_key,
        }
        
        response = requests.get(search_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("items", [])
        
        for item in items:
            snippet = item.get("snippet", {})
            title = snippet.get("title", "").lower()
            
            if any(keyword in title for keyword in ai_keywords):
                video_id = item.get("id", {}).get("videoId", "")
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                
                stories.append({
                    "title": snippet.get("title", ""),
                    "url": video_url,
                    "points": 0,
                    "comments": 0,
                    "author": snippet.get("channelTitle", ""),
                    "source": "YouTube",
                })
                
                if len(stories) >= limit:
                    break
        
        return stories[:limit]
        
    except Exception as e:
        print(f"Error fetching YouTube stories: {e}", file=sys.stderr)
        return []


def fetch_twitter_ai_stories(limit: int = 5) -> List[Dict]:
    """Fetch AI-related tweets/posts from Twitter/X."""
    # Note: Twitter API requires authentication
    # For now, return empty list - can be implemented with API keys
    print("Twitter/X integration requires API keys. Skipping Twitter fetch.", file=sys.stderr)
    return []


# ============ BUSINESS NEWS FUNCTIONS ============

def fetch_rss_business_news(rss_url: str, source_name: str, limit: int = 10) -> List[Dict]:
    """Generic function to fetch business news from RSS feeds."""
    try:
        feed = feedparser.parse(rss_url)
        
        if feed.bozo:
            print(f"Warning: Feed parsing issue for {source_name}: {feed.bozo_exception}", file=sys.stderr)
        
        stories = []
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        
        for entry in feed.entries:
            published = entry.get("published_parsed")
            
            # Check date if available
            if published:
                pub_date = datetime(*published[:6])
                if pub_date < day_ago:
                    continue
            
            link = entry.get("link", "")
            title = entry.get("title", "")
            
            stories.append({
                "title": title,
                "url": link if validate_url(link) else "",
                "source": source_name,
                "author": entry.get("author", source_name),
                "published": entry.get("published", ""),
            })
        
        return stories[:limit]
        
    except Exception as e:
        print(f"Error fetching {source_name}: {e}", file=sys.stderr)
        return []


def fetch_business_news(limit: int = 10) -> List[Dict]:
    """Fetch business news from multiple sources."""
    all_stories = []
    
    # CNN Business
    print("Fetching CNN Business...", file=sys.stderr)
    cnn_stories = fetch_rss_business_news(
        "http://rss.cnn.com/rss/money_latest.rss",
        "CNN Business",
        limit=limit
    )
    all_stories.extend(cnn_stories)
    
    # Fox Business
    print("Fetching Fox Business...", file=sys.stderr)
    fox_stories = fetch_rss_business_news(
        "https://feeds.foxnews.com/foxnews/business",
        "Fox Business",
        limit=limit
    )
    all_stories.extend(fox_stories)
    
    # NBC News Business
    print("Fetching NBC News Business...", file=sys.stderr)
    nbc_stories = fetch_rss_business_news(
        "https://feeds.nbcnews.com/nbcnews/public/business",
        "NBC News",
        limit=limit
    )
    all_stories.extend(nbc_stories)
    
    # WSJ - Using WSJ RSS (may require subscription for some feeds)
    print("Fetching WSJ Business...", file=sys.stderr)
    wsj_stories = fetch_rss_business_news(
        "https://feeds.a.dj.com/rss/RSSOpinion.xml",  # WSJ Opinion as fallback
        "WSJ",
        limit=limit
    )
    all_stories.extend(wsj_stories)
    
    # NYTimes Business
    print("Fetching NYTimes Business...", file=sys.stderr)
    nyt_stories = fetch_rss_business_news(
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "NYTimes",
        limit=limit
    )
    all_stories.extend(nyt_stories)
    
    # Deduplicate by title
    seen_titles = set()
    unique_stories = []
    for story in all_stories:
        title_key = story.get("title", "").lower().strip()
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_stories.append(story)
    
    return unique_stories[:limit]


# ============ TECH NEWS FUNCTIONS ============

def fetch_hacker_news_tech_stories(limit: int = 10) -> List[Dict]:
    """Fetch top tech stories (non-AI) from Hacker News."""
    url = "https://hn.algolia.com/api/v1/search_by_date"
    
    params = {
        "tags": "story",
        "numericFilters": "created_at_i>0",
        "hitsPerPage": limit * 2,
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        hits = data.get("hits", [])
        ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", "anthropic", "claude"]
        tech_stories = []
        
        for hit in hits:
            title = hit.get("title", "").lower()
            # Exclude AI stories
            if not any(keyword in title for keyword in ai_keywords):
                object_id = hit.get("objectID")
                title_text = hit.get("title", "")
                hn_url = ensure_hn_url(object_id, title_text)
                external_url = hit.get("url", "")
                
                final_url = external_url if (external_url and validate_url(external_url)) else hn_url
                
                tech_stories.append({
                    "title": title_text,
                    "url": final_url,
                    "points": hit.get("points", 0),
                    "comments": hit.get("num_comments", 0),
                    "author": hit.get("author", ""),
                    "source": "Hacker News",
                })
                
                if len(tech_stories) >= limit:
                    break
        
        return tech_stories[:limit]
        
    except Exception as e:
        print(f"Error fetching Hacker News tech stories: {e}", file=sys.stderr)
        return []


def fetch_techcrunch_tech_stories(limit: int = 10) -> List[Dict]:
    """Fetch general tech stories from TechCrunch (non-AI)."""
    try:
        rss_url = "https://techcrunch.com/feed/"
        feed = feedparser.parse(rss_url)
        
        if feed.bozo:
            print(f"Warning: Feed parsing issue: {feed.bozo_exception}", file=sys.stderr)
        
        ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm"]
        stories = []
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        
        for entry in feed.entries:
            title = entry.get("title", "").lower()
            # Exclude AI-specific stories
            if not any(keyword in title for keyword in ai_keywords):
                published = entry.get("published_parsed")
                
                if published:
                    pub_date = datetime(*published[:6])
                    if pub_date < day_ago:
                        continue
                
                link = entry.get("link", "")
                stories.append({
                    "title": entry.get("title", ""),
                    "url": link if validate_url(link) else "https://techcrunch.com",
                    "source": "TechCrunch",
                    "author": entry.get("author", "TechCrunch"),
                })
        
        return stories[:limit]
        
    except Exception as e:
        print(f"Error fetching TechCrunch tech stories: {e}", file=sys.stderr)
        return []


def fetch_reddit_tech_stories(limit: int = 10) -> List[Dict]:
    """Fetch tech stories from Reddit tech subreddits."""
    subreddits = ["technology", "programming", "gadgets", "technews"]
    all_stories = []
    
    for subreddit in subreddits:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
            response = requests.get(url, headers=REDDIT_HEADERS, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            posts = data.get("data", {}).get("children", [])
            
            for post in posts:
                post_data = post.get("data", {})
                reddit_url = f"https://www.reddit.com{post_data.get('permalink', '')}"
                external_url = post_data.get("url_overridden_by_dest", "")
                
                final_url = external_url if (external_url and validate_url(external_url) and "reddit.com" not in external_url) else reddit_url
                
                all_stories.append({
                    "title": post_data.get("title", ""),
                    "url": final_url,
                    "points": post_data.get("score", 0),
                    "comments": post_data.get("num_comments", 0),
                    "author": post_data.get("author", ""),
                    "source": f"r/{subreddit}",
                })
            
            time.sleep(0.5)
                    
        except Exception as e:
            print(f"Error fetching from r/{subreddit}: {e}", file=sys.stderr)
            continue
    
    all_stories.sort(key=lambda x: x.get("points", 0), reverse=True)
    return all_stories[:limit]


def fetch_tech_news(limit: int = 10) -> List[Dict]:
    """Fetch tech news from multiple sources."""
    all_stories = []
    
    print("Fetching TechCrunch tech stories...", file=sys.stderr)
    tc_stories = fetch_techcrunch_tech_stories(limit=limit)
    all_stories.extend(tc_stories)
    
    print("Fetching Hacker News tech stories...", file=sys.stderr)
    hn_stories = fetch_hacker_news_tech_stories(limit=limit)
    all_stories.extend(hn_stories)
    
    print("Fetching Reddit tech stories...", file=sys.stderr)
    reddit_stories = fetch_reddit_tech_stories(limit=limit)
    all_stories.extend(reddit_stories)
    
    # Deduplicate
    seen_titles = set()
    unique_stories = []
    for story in all_stories:
        title_key = story.get("title", "").lower().strip()
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_stories.append(story)
    
    # Sort by points/engagement
    unique_stories.sort(key=lambda x: x.get("points", 0), reverse=True)
    return unique_stories[:limit]


# ============ MOTIVATION QUOTES FUNCTIONS ============

def fetch_reddit_quotes_with_firecrawl(subreddits: List[str], limit: int = 10, api_key: Optional[str] = None) -> List[Dict]:
    """
    Fetch quotes from Reddit subreddits using Firecrawl to scrape actual post content.
    First gets post URLs from Reddit JSON API, then uses Firecrawl to scrape full content.
    """
    if not FIRECRAWL_AVAILABLE or not api_key:
        return []
    
    all_items = []
    
    try:
        app = FirecrawlApp(api_key=api_key)
        
        # First, get post URLs from Reddit JSON API
        post_urls = []
        for subreddit in subreddits:
            try:
                url = f"https://www.reddit.com/r/{subreddit}/hot.json"
                params = {"limit": 25}
                response = requests.get(url, headers=REDDIT_HEADERS, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                posts = data.get("data", {}).get("children", [])
                
                for post in posts:
                    post_data = post.get("data", {})
                    # Skip stickied posts
                    if post_data.get("stickied", False):
                        continue
                    
                    # Get post URL
                    permalink = post_data.get("permalink", "")
                    if permalink:
                        reddit_url = f"https://www.reddit.com{permalink}"
                        post_urls.append({
                            "url": reddit_url,
                            "title": post_data.get("title", ""),
                            "subreddit": subreddit,
                            "score": post_data.get("score", 0),
                            "comments": post_data.get("num_comments", 0),
                            "author": post_data.get("author", ""),
                        })
                
                time.sleep(0.5)  # Rate limiting for Reddit API
                
            except Exception as e:
                print(f"Error fetching post URLs from r/{subreddit}: {e}", file=sys.stderr)
                continue
        
        # Now use Firecrawl to scrape content from each post
        print(f"Scraping {len(post_urls)} Reddit posts with Firecrawl...", file=sys.stderr)
        for i, post_info in enumerate(post_urls[:limit * 2]):  # Get more than needed, filter later
            try:
                print(f"Scraping post {i+1}/{min(len(post_urls), limit * 2)}: {post_info['url']}", file=sys.stderr)
                
                result = app.scrape_url(
                    post_info["url"],
                    params={
                        "formats": ["markdown"],
                        "onlyMainContent": True,
                    }
                )
                
                if not result or not result.get("content"):
                    continue
                
                content = result.get("content", "").strip()
                
                # Extract meaningful content (skip if too short)
                if len(content) < 20:
                    continue
                
                # Use title from Reddit API, content from Firecrawl
                all_items.append({
                    "content": content[:500],  # Limit length
                    "title": post_info["title"][:200],
                    "url": post_info["url"],
                    "points": post_info["score"],
                    "comments": post_info["comments"],
                    "author": post_info["author"],
                    "source": f"r/{post_info['subreddit']}",
                })
                
                # Rate limiting for Firecrawl
                time.sleep(1)
                
            except Exception as e:
                print(f"Error scraping post {post_info['url']}: {e}", file=sys.stderr)
                continue
        
        print(f"Total items collected via Firecrawl: {len(all_items)}", file=sys.stderr)
        
        # Sort by score and return top items
        all_items.sort(key=lambda x: (x.get("points", 0), x.get("comments", 0)), reverse=True)
        return all_items[:limit]
        
    except Exception as e:
        print(f"Error in Firecrawl fetching: {e}", file=sys.stderr)
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
        return []


def fetch_reddit_quotes(subreddits: List[str], limit: int = 10) -> List[Dict]:
    """Fetch quotes from Reddit subreddits."""
    all_items = []
    
    for subreddit in subreddits:
        try:
            # Reddit JSON API endpoint
            url = f"https://www.reddit.com/r/{subreddit}/hot.json"
            params = {"limit": 25}
            
            response = requests.get(url, headers=REDDIT_HEADERS, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            posts = data.get("data", {}).get("children", [])
            print(f"Fetched {len(posts)} posts from r/{subreddit}", file=sys.stderr)
            
            for post in posts:
                post_data = post.get("data", {})
                selftext = post_data.get("selftext", "").strip()
                title = post_data.get("title", "").strip()
                
                # Skip if post is deleted or removed
                if selftext == "[deleted]" or selftext == "[removed]":
                    continue
                
                # Skip stickied posts (usually mod announcements)
                if post_data.get("stickied", False):
                    continue
                
                # For quotes/knowledge, use selftext if meaningful, otherwise use title
                # But make title work even if short - some good quotes are in titles
                if selftext and len(selftext) > 15:  # Reduced minimum length
                    content = selftext[:500]  # Limit length
                elif title and len(title) > 10:  # Ensure title has some content
                    content = title
                else:
                    continue
                
                # Skip if content is too short overall
                if len(content.strip()) < 10:
                    continue
                
                if content:
                    reddit_url = f"https://www.reddit.com{post_data.get('permalink', '')}"
                    
                    all_items.append({
                        "content": content,
                        "title": title,
                        "url": reddit_url,
                        "points": post_data.get("score", 0),
                        "comments": post_data.get("num_comments", 0),
                        "author": post_data.get("author", ""),
                        "source": f"r/{subreddit}",
                    })
            
            # Rate limiting - be nice to Reddit
            time.sleep(1)
                    
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error fetching from r/{subreddit}: {e} (Status: {e.response.status_code})", file=sys.stderr)
            if e.response.status_code == 403:
                print(f"Access forbidden for r/{subreddit} - might be private or banned", file=sys.stderr)
            continue
        except requests.exceptions.RequestException as e:
            print(f"Request error fetching from r/{subreddit}: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"Error fetching from r/{subreddit}: {e}", file=sys.stderr)
            import traceback
            print(traceback.format_exc(), file=sys.stderr)
            continue
    
    print(f"Total items collected: {len(all_items)}", file=sys.stderr)
    
    # Sort by score and return top items
    all_items.sort(key=lambda x: (x.get("points", 0), x.get("comments", 0)), reverse=True)
    return all_items[:limit]


def fetch_motivation_quotes(limit: int = 10) -> List[Dict]:
    """Fetch motivation quotes from Reddit, using Firecrawl if available."""
    print("Fetching motivation quotes...", file=sys.stderr)
    # Try multiple subreddits - Reddit is case-insensitive but some subreddits may have different names
    subreddits = ["GetMotivated", "motivation", "quotes", "inspiration", "motivational", "DecidingToBeBetter"]
    
    # Try Firecrawl first if available
    firecrawl_key = get_firecrawl_key()
    if FIRECRAWL_AVAILABLE and firecrawl_key:
        print("Using Firecrawl to fetch motivation quotes...", file=sys.stderr)
        firecrawl_items = fetch_reddit_quotes_with_firecrawl(subreddits, limit=limit, api_key=firecrawl_key)
        if firecrawl_items:
            return firecrawl_items
    
    # Fallback to JSON API
    print("Using Reddit JSON API to fetch motivation quotes...", file=sys.stderr)
    return fetch_reddit_quotes(subreddits, limit=limit)


# ============ WISE KNOWLEDGE FUNCTIONS ============

def fetch_wise_knowledge(limit: int = 10) -> List[Dict]:
    """Fetch wise knowledge from Reddit philosophy/stoicism subreddits, using Firecrawl if available."""
    print("Fetching wise knowledge...", file=sys.stderr)
    subreddits = ["Stoicism", "philosophy", "ZenHabits", "Meditation", "Mindfulness", "zen", "taoism", "selfimprovement"]
    
    # Try Firecrawl first if available
    firecrawl_key = get_firecrawl_key()
    if FIRECRAWL_AVAILABLE and firecrawl_key:
        print("Using Firecrawl to fetch wise knowledge...", file=sys.stderr)
        firecrawl_items = fetch_reddit_quotes_with_firecrawl(subreddits, limit=limit, api_key=firecrawl_key)
        if firecrawl_items:
            return firecrawl_items
    
    # Fallback to JSON API
    print("Using Reddit JSON API to fetch wise knowledge...", file=sys.stderr)
    return fetch_reddit_quotes(subreddits, limit=limit)


# ============ SUMMARY GENERATION ============

def generate_ai_summary(stories: List[Dict], api_key: str, content_type: str = "AI") -> str:
    """Generate AI summary using OpenAI."""
    if not stories:
        return f"No {content_type} content found today."
    
    stories_text = "\n\n".join([
        f"{i+1}. {story.get('title', story.get('content', 'N/A'))}"
        for i, story in enumerate(stories[:5])  # Limit to top 5 for summary
    ])
    
    prompt = f"""Based on these top {content_type} items, provide a concise 2-3 sentence summary:

{stories_text}

Summarize the main themes, key insights, or noteworthy developments."""

    try:
        client = OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": f"You are a concise writer who summarizes {content_type} content accurately."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.7,
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"Error generating {content_type} summary: {e}", file=sys.stderr)
        sources = set(s.get('source', 'Unknown') for s in stories)
        return f"Today's {content_type} content includes {len(stories)} items from {', '.join(sorted(sources))}."


# ============ MARKDOWN FORMATTING ============

def format_ai_markdown(stories: List[Dict], summary: str, date: str) -> str:
    """Format AI news section as markdown."""
    lines = [
        f"## 🤖 AI Industry Snapshot - {date}",
        "",
        "### Top AI Stories",
        "",
    ]
    
    for i, story in enumerate(stories, 1):
        primary_url = story.get('hn_url') or story.get('url', 'https://news.ycombinator.com/newest')
        if not validate_url(primary_url):
            primary_url = 'https://news.ycombinator.com/newest'
        
        lines.append(f"{i}. [{story['title']}]({primary_url})")
        lines.append("")
    
    lines.extend([
        "### AI Trends Summary",
        "",
        summary,
        "",
    ])
    
    return "\n".join(lines)


def format_news_markdown(stories: List[Dict], summary: str, date: str, section_title: str, emoji: str) -> str:
    """Format news section (business/tech) as markdown."""
    lines = [
        f"## {emoji} {section_title} - {date}",
        "",
        "### Top Stories",
        "",
    ]
    
    for i, story in enumerate(stories, 1):
        url = story.get('url', '#')
        if not validate_url(url):
            url = '#'
        lines.append(f"{i}. [{story['title']}]({url})")
        lines.append("")
    
    lines.extend([
        "### Summary",
        "",
        summary,
        "",
    ])
    
    return "\n".join(lines)


def format_quotes_markdown(items: List[Dict], summary: str, date: str, section_title: str, emoji: str) -> str:
    """Format quotes/knowledge section as markdown."""
    lines = [
        f"## {emoji} {section_title} - {date}",
        "",
        "### Top Items",
        "",
    ]
    
    for i, item in enumerate(items, 1):
        content = item.get('content', item.get('title', ''))
        url = item.get('url', '#')
        if not validate_url(url):
            url = '#'
        source = item.get('source', 'Unknown')
        
        lines.append(f"{i}. {content}")
        lines.append(f"   *Source: [{source}]({url})*")
        lines.append("")
    
    lines.extend([
        "### Summary",
        "",
        summary,
        "",
    ])
    
    return "\n".join(lines)


# ============ MAIN FUNCTION ============

def main():
    """Main execution function."""
    try:
        openai_key = get_openai_key()
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        output = {
            "date": date_str,
            "ai_news": {"markdown": "", "stories": [], "summary": ""},
            "business_news": {"markdown": "", "stories": [], "summary": ""},
            "tech_news": {"markdown": "", "stories": [], "summary": ""},
            "podcasts": {"markdown": "", "podcasts": [], "summary": ""},
            "motivation_quotes": {"markdown": "", "items": [], "summary": ""},
            "wise_knowledge": {"markdown": "", "items": [], "summary": ""},
        }
        
        # Fetch AI News
        print("Fetching AI news...", file=sys.stderr)
        all_ai_stories = []
        
        # Fetch from YouTube (if API key available)
        try:
            youtube_ai = fetch_youtube_ai_stories(limit=5)
            all_ai_stories.extend(youtube_ai)
            print(f"Found {len(youtube_ai)} AI stories from YouTube", file=sys.stderr)
        except Exception as e:
            print(f"YouTube fetch skipped: {e}", file=sys.stderr)
        
        # Fetch from Twitter/X (if API key available)
        try:
            twitter_ai = fetch_twitter_ai_stories(limit=5)
            all_ai_stories.extend(twitter_ai)
            print(f"Found {len(twitter_ai)} AI stories from Twitter/X", file=sys.stderr)
        except Exception as e:
            print(f"Twitter fetch skipped: {e}", file=sys.stderr)
        
        reddit_ai = fetch_reddit_ai_stories(limit=5)
        tc_ai = fetch_techcrunch_ai_stories(limit=5)
        hn_ai = fetch_hacker_news_ai_stories(limit=5)
        all_ai_stories.extend(reddit_ai)
        all_ai_stories.extend(tc_ai)
        all_ai_stories.extend(hn_ai)
        
        # Deduplicate AI stories
        seen_ai = set()
        unique_ai = []
        for story in all_ai_stories:
            title_key = story.get("title", "").lower().strip()
            if title_key and title_key not in seen_ai:
                seen_ai.add(title_key)
                unique_ai.append(story)
        unique_ai = unique_ai[:10]
        
        if unique_ai:
            ai_summary = generate_ai_summary(unique_ai, openai_key, "AI")
        else:
            ai_summary = "No AI stories found today."
        
        output["ai_news"]["markdown"] = format_ai_markdown(unique_ai[:10], ai_summary, date_str)
        output["ai_news"]["stories"] = unique_ai[:10]
        output["ai_news"]["summary"] = ai_summary
        
        # Fetch Business News
        print("Fetching business news...", file=sys.stderr)
        business_stories = fetch_business_news(limit=10)
        if business_stories:
            business_summary = generate_ai_summary(business_stories, openai_key, "Business")
        else:
            business_summary = "No business news found today."
        
        output["business_news"]["markdown"] = format_news_markdown(business_stories, business_summary, date_str, "Business News", "💼")
        output["business_news"]["stories"] = business_stories
        output["business_news"]["summary"] = business_summary
        
        # Fetch Tech News
        print("Fetching tech news...", file=sys.stderr)
        tech_stories = fetch_tech_news(limit=10)
        if tech_stories:
            tech_summary = generate_ai_summary(tech_stories, openai_key, "Tech")
        else:
            tech_summary = "No tech news found today."
        
        output["tech_news"]["markdown"] = format_news_markdown(tech_stories, tech_summary, date_str, "Tech News", "💻")
        output["tech_news"]["stories"] = tech_stories
        output["tech_news"]["summary"] = tech_summary
        
        # Fetch Motivation Quotes
        print("Fetching motivation quotes...", file=sys.stderr)
        quotes = fetch_motivation_quotes(limit=10)
        if quotes:
            quotes_summary = generate_ai_summary(quotes, openai_key, "Motivation")
        else:
            quotes_summary = "No motivation quotes found today."
        
        output["motivation_quotes"]["markdown"] = format_quotes_markdown(quotes, quotes_summary, date_str, "Motivation Quotes", "💪")
        output["motivation_quotes"]["items"] = quotes
        output["motivation_quotes"]["summary"] = quotes_summary
        
        # Fetch Wise Knowledge
        print("Fetching wise knowledge...", file=sys.stderr)
        knowledge = fetch_wise_knowledge(limit=10)
        if knowledge:
            knowledge_summary = generate_ai_summary(knowledge, openai_key, "Wisdom")
        else:
            knowledge_summary = "No wise knowledge found today."
        
        output["wise_knowledge"]["markdown"] = format_quotes_markdown(knowledge, knowledge_summary, date_str, "Wise Knowledge", "🧠")
        output["wise_knowledge"]["items"] = knowledge
        output["wise_knowledge"]["summary"] = knowledge_summary
        
        # Fetch Podcasts (if summarize_podcasts.py output is available)
        # This will be populated by calling summarize_podcasts.py separately in the workflow
        # For now, set empty placeholder
        output["podcasts"]["markdown"] = ""
        output["podcasts"]["podcasts"] = []
        output["podcasts"]["summary"] = ""
        
        # Save to archive
        archive_dir = "archive"
        os.makedirs(archive_dir, exist_ok=True)
        archive_path = os.path.join(archive_dir, f"{date_str}-digest.json")
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"Archive saved to {archive_path}", file=sys.stderr)
        
        # Output JSON for other scripts
        print(json.dumps(output))
        
    except ValueError as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        date_str = datetime.now().strftime("%Y-%m-%d")
        fallback = {
            "date": date_str,
            "error": str(e),
            "ai_news": {"markdown": f"## 🤖 AI Industry Snapshot - {date_str}\n\n*Error: {str(e)}*\n", "stories": [], "summary": ""},
            "business_news": {"markdown": "", "stories": [], "summary": ""},
            "tech_news": {"markdown": "", "stories": [], "summary": ""},
            "motivation_quotes": {"markdown": "", "items": [], "summary": ""},
            "wise_knowledge": {"markdown": "", "items": [], "summary": ""},
        }
        print(json.dumps(fallback))
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
        date_str = datetime.now().strftime("%Y-%m-%d")
        fallback = {
            "date": date_str,
            "error": str(e),
            "ai_news": {"markdown": f"## 🤖 AI Industry Snapshot - {date_str}\n\n*Error: {str(e)}*\n", "stories": [], "summary": ""},
            "business_news": {"markdown": "", "stories": [], "summary": ""},
            "tech_news": {"markdown": "", "stories": [], "summary": ""},
            "motivation_quotes": {"markdown": "", "items": [], "summary": ""},
            "wise_knowledge": {"markdown": "", "items": [], "summary": ""},
        }
        print(json.dumps(fallback))
        sys.exit(1)


if __name__ == "__main__":
    main()

