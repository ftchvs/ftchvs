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
    
    headers = {
        "User-Agent": "AI-News-Aggregator/1.0 (contact: ftchvs)"
    }
    
    # Fetch from AI-specific subreddits (include all posts since they're AI-focused)
    for subreddit in ai_subreddits:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
            response = requests.get(url, headers=headers, timeout=30)
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
            response = requests.get(url, headers=headers, timeout=30)
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
                        "hn_url": reddit_url,
                        "source": f"r/{subreddit}",
                        "subreddit": subreddit,
                    })
                    
        except Exception as e:
            print(f"Error fetching from r/{subreddit}: {e}", file=sys.stderr)
            continue
    
    # Sort by score (points) and return top stories
    all_stories.sort(key=lambda x: x.get("points", 0), reverse=True)
    print(f"Total Reddit AI stories found: {len(all_stories)}", file=sys.stderr)
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


def fetch_twitter_ai_stories(limit: int = 5) -> List[Dict]:
    """Fetch AI-related tweets/posts from Twitter/X using web scraping via Nitter or similar."""
    # Note: Twitter API v2 requires authentication and is rate-limited
    # This uses a public RSS feed approach via Nitter (a privacy-focused Twitter frontend)
    # Alternative: Use Twitter's search API if API keys are available
    ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", "anthropic", "claude", "neural", "deep learning"]
    stories = []
    
    try:
        # Try using Nitter RSS feeds for popular AI accounts
        # Nitter instances may be unreliable, so we'll try multiple approaches
        ai_accounts = [
            "@OpenAI",
            "@anthropicAI", 
            "@GoogleAI",
            "@DeepMind",
            "@sama",  # Sam Altman
            "@AndrewYNg",  # Andrew Ng
        ]
        
        # Try to fetch from public Twitter search via alternative APIs
        # For now, we'll return empty and log that Twitter requires API setup
        print("Twitter/X integration requires API keys. Skipping Twitter fetch.", file=sys.stderr)
        return []
        
    except Exception as e:
        print(f"Error fetching Twitter stories: {e}", file=sys.stderr)
        return []


def fetch_youtube_ai_stories(limit: int = 5) -> List[Dict]:
    """Fetch AI-related videos from YouTube."""
    ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai", "anthropic", "claude", "neural", "deep learning"]
    stories = []
    
    try:
        # Check for YouTube Data API key
        youtube_api_key = os.getenv("YOUTUBE_API_KEY")
        if not youtube_api_key:
            print("YOUTUBE_API_KEY not found. Skipping YouTube fetch.", file=sys.stderr)
            return []
        
        # YouTube Data API v3
        search_url = "https://www.googleapis.com/youtube/v3/search"
        
        params = {
            "part": "snippet",
            "q": "AI artificial intelligence machine learning LLM",
            "type": "video",
            "maxResults": limit * 2,  # Get more to filter
            "order": "relevance",
            "publishedAfter": (datetime.now() - timedelta(days=7)).isoformat() + "Z",  # Last week
            "key": youtube_api_key,
        }
        
        response = requests.get(search_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("items", [])
        
        for item in items:
            snippet = item.get("snippet", {})
            title = snippet.get("title", "").lower()
            
            # Filter for AI-related content
            if any(keyword in title for keyword in ai_keywords):
                video_id = item.get("id", {}).get("videoId", "")
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                
                stories.append({
                    "title": snippet.get("title", ""),
                    "url": video_url,
                    "points": 0,  # YouTube doesn't have upvotes in search
                    "comments": 0,
                    "author": snippet.get("channelTitle", ""),
                    "hn_url": video_url,
                    "source": "YouTube",
                    "channel_id": snippet.get("channelId", ""),
                })
                
                if len(stories) >= limit:
                    break
        
        return stories[:limit]
        
    except Exception as e:
        print(f"Error fetching YouTube stories: {e}", file=sys.stderr)
        return []


def get_source_priority(source: str) -> int:
    """Get priority value for source (lower number = higher priority)."""
    source_lower = source.lower()
    if "youtube" in source_lower:
        return 1  # Highest priority
    elif "twitter" in source_lower or "x.com" in source_lower:
        return 1  # Highest priority
    elif "techcrunch" in source_lower:
        return 2  # Second priority
    elif "reddit" in source_lower or source_lower.startswith("r/"):
        return 3  # Third priority
    elif "hacker news" in source_lower or "hn" in source_lower:
        return 4  # Lower priority
    return 5  # Unknown sources


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
    
    prompt = f"""Based on these top AI stories from Hacker News, Reddit, TechCrunch, Twitter/X, and YouTube, provide a concise 2-3 sentence summary of the key AI trends and developments:

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


def generate_pointillism_image(stories: List[Dict], summary: str, api_key: str, date: str) -> Optional[str]:
    """Generate a digital pointillism image with motion design inspired by AI news."""
    if not stories:
        return None
    
    # Create a rich prompt based on news themes
    stories_text = "\n".join([story.get('title', '') for story in stories[:5]])
    
    # Generate an image prompt that captures the essence of the news
    prompt_generation = f"""Based on these AI news headlines and summary, create a detailed visual description for a digital pointillism artwork blended with generative motion design:

Headlines:
{stories_text}

Summary: {summary}

Create a description of a stunning digital pointillism artwork that:
- Uses thousands of small colored dots/pixels to form an abstract composition
- Incorporates motion design elements (flowing lines, dynamic patterns, energy waves)
- Reflects themes from the AI news (innovation, technology, neural networks, data streams)
- Has a futuristic, tech-forward aesthetic
- Uses vibrant colors that suggest innovation and progress
- Blends pointillism technique with modern generative art aesthetics

Return ONLY the visual description (no explanation, no markdown, just the description)."""
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Generate the image description
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a visual artist specializing in digital art and creative descriptions."},
                {"role": "user", "content": prompt_generation}
            ],
            max_tokens=300,
            temperature=0.8,
        )
        
        image_description = response.choices[0].message.content.strip()
        
        # Add pointillism and motion design specifics to the prompt
        image_prompt = f"Digital pointillism artwork, {image_description}, blended with generative motion design, dynamic flowing patterns, vibrant colors, abstract composition, thousands of small dots forming intricate patterns, futuristic tech aesthetic, inspired by AI and technology news"
        
        # Generate the image using DALL-E
        print("Generating digital pointillism artwork...", file=sys.stderr)
        image_response = client.images.generate(
            model="dall-e-3",
            prompt=image_prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        
        image_url = image_response.data[0].url
        
        # Download and save the image
        os.makedirs("image/ai_news", exist_ok=True)
        image_filename = f"image/ai_news/{date}-pointillism.png"
        
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        
        with open(image_filename, "wb") as f:
            f.write(img_response.content)
        
        print(f"Image saved to {image_filename}", file=sys.stderr)
        return image_filename
        
    except Exception as e:
        print(f"Error generating pointillism image: {e}", file=sys.stderr)
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
        return None


def format_ai_markdown(stories: List[Dict], summary: str, date: str, image_path: Optional[str] = None) -> str:
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
    
    # Add the pointillism image at the end
    if image_path:
        lines.extend([
            "### 🎨 Digital Art: Pointillism & Motion Design",
            "",
            f"*Inspired by today's AI news trends*",
            "",
            f"![Digital Pointillism Artwork]({image_path})",
            "",
        ])
    
    return "\n".join(lines)


def main():
    """Main execution function."""
    try:
        openai_key = get_openai_key()
        
        all_stories = []
        
        # Fetch from YouTube (high priority)
        print("Fetching AI stories from YouTube...", file=sys.stderr)
        youtube_stories = fetch_youtube_ai_stories(limit=5)
        all_stories.extend(youtube_stories)
        print(f"Found {len(youtube_stories)} stories from YouTube", file=sys.stderr)
        
        # Fetch from Twitter/X (high priority, if API available)
        print("Fetching AI stories from Twitter/X...", file=sys.stderr)
        twitter_stories = fetch_twitter_ai_stories(limit=5)
        all_stories.extend(twitter_stories)
        print(f"Found {len(twitter_stories)} stories from Twitter/X", file=sys.stderr)
        
        # Fetch from Reddit
        print("Fetching AI stories from Reddit...", file=sys.stderr)
        reddit_stories = fetch_reddit_ai_stories(limit=5)
        all_stories.extend(reddit_stories)
        print(f"Found {len(reddit_stories)} stories from Reddit", file=sys.stderr)
        
        # Fetch from TechCrunch
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
        
        # Generate pointillism image inspired by the news
        image_path = None
        if top_stories:
            print("Generating digital pointillism artwork...", file=sys.stderr)
            image_path = generate_pointillism_image(top_stories, summary, openai_key, date_str)
        
        markdown = format_ai_markdown(top_stories, summary, date_str, image_path)
        
        # Output JSON for other scripts to consume (to stdout only)
        output = {
            "date": date_str,
            "markdown": markdown,
            "stories": top_stories,
            "summary": summary,
            "image_path": image_path,
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
            "summary": "",
            "image_path": None
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
            "summary": "",
            "image_path": None
        }
        print(json.dumps(fallback))
        sys.exit(1)


if __name__ == "__main__":
    main()

