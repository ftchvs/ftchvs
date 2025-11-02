#!/usr/bin/env python3
"""
Fetch top AI stories from Hacker News and generate AI summary via OpenAI.
"""

import os
import sys
import json
from typing import List, Dict, Optional
import requests
from openai import OpenAI


def get_openai_key() -> str:
    """Get OpenAI API key from environment."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    return key


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
                ai_stories.append({
                    "title": hit.get("title", ""),
                    "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    "points": hit.get("points", 0),
                    "comments": hit.get("num_comments", 0),
                    "author": hit.get("author", ""),
                    "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                })
                
                if len(ai_stories) >= limit:
                    break
        
        return ai_stories[:limit]
        
    except Exception as e:
        print(f"Error fetching Hacker News stories: {e}", file=sys.stderr)
        return []


def generate_ai_summary(stories: List[Dict], api_key: str) -> str:
    """Generate AI summary of the top AI stories using OpenAI."""
    if not stories:
        return "No AI stories found today."
    
    # Format stories for the prompt
    stories_text = "\n\n".join([
        f"{i+1}. {story['title']} ({story['points']} points, {story['comments']} comments)"
        for i, story in enumerate(stories)
    ])
    
    prompt = f"""Based on these top AI stories from Hacker News, provide a concise 2-3 sentence summary of the key AI trends and developments:

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
        return f"Today's top AI stories cover {len(stories)} trending topics with {sum(s.get('points', 0) for s in stories)} combined points on Hacker News."


def format_ai_markdown(stories: List[Dict], summary: str, date: str) -> str:
    """Format AI news section as markdown."""
    lines = [
        f"## 🤖 AI Industry Snapshot - {date}",
        "",
        "### Top AI Stories",
        "",
    ]
    
    for i, story in enumerate(stories, 1):
        # Use Hacker News URL instead of external URL
        lines.append(f"{i}. [{story['title']}]({story['hn_url']})")
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
        
        print("Fetching top AI stories from Hacker News...", file=sys.stderr)
        stories = fetch_hacker_news_ai_stories(limit=5)
        
        if not stories:
            print("Warning: No AI stories found. Generating fallback summary.", file=sys.stderr)
            # Even if no stories, try to generate a summary
            summary = "No AI stories found today. Check back tomorrow for the latest AI developments."
        else:
            print(f"Found {len(stories)} AI stories", file=sys.stderr)
            print("Generating AI summary...", file=sys.stderr)
            summary = generate_ai_summary(stories, openai_key)
        
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        markdown = format_ai_markdown(stories, summary, date_str)
        
        # Output JSON for other scripts to consume (to stdout only)
        output = {
            "date": date_str,
            "markdown": markdown,
            "stories": stories,
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

