#!/usr/bin/env python3
"""
Update README.md by injecting content between comment markers.
Supports multiple sections:
- AI News
- Business News
- Tech News
- Motivation Quotes
- Wise Knowledge
"""

import os
import sys
import json
from typing import Optional
from datetime import datetime
import pytz


def read_file(filepath: str) -> str:
    """Read file content."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def write_file(filepath: str, content: str):
    """Write content to file."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def extract_content_markdown(content_json: str, section_key: str) -> str:
    """Extract markdown from content JSON output for a specific section."""
    try:
        data = json.loads(content_json)
        section_data = data.get(section_key, {})
        return section_data.get("markdown", "")
    except (json.JSONDecodeError, TypeError):
        return ""


def remove_duplicate_sections(content: str, start_marker: str, end_marker: str) -> str:
    """Remove duplicate sections, keeping only the last occurrence."""
    # Find all occurrences
    start_indices = []
    end_indices = []
    
    start_idx = 0
    while True:
        idx = content.find(start_marker, start_idx)
        if idx == -1:
            break
        start_indices.append(idx)
        start_idx = idx + 1
    
    start_idx = 0
    while True:
        idx = content.find(end_marker, start_idx)
        if idx == -1:
            break
        end_indices.append(idx)
        start_idx = idx + 1
    
    # If we have duplicates, keep only the last one
    if len(start_indices) > 1:
        print(f"Found {len(start_indices)} duplicate sections for {start_marker}, removing all but the last", file=sys.stderr)
        # Remove all but the last occurrence
        for i in range(len(start_indices) - 1):
            start_pos = start_indices[i]
            end_pos = end_indices[i] + len(end_marker)
            # Remove this section
            content = content[:start_pos] + content[end_pos:]
            # Adjust subsequent indices
            removed_len = end_pos - start_pos
            for j in range(i + 1, len(start_indices)):
                start_indices[j] -= removed_len
                end_indices[j] -= removed_len
    
    return content


def update_readme_section(
    readme_path: str,
    markdown_content: str,
    start_marker: str,
    end_marker: str,
) -> bool:
    """
    Update a specific section in README.md by replacing content between markers.
    Removes duplicates and keeps only one section.
    Returns True if file was modified, False otherwise.
    """
    if not os.path.exists(readme_path):
        print(f"Error: README file not found at {readme_path}", file=sys.stderr)
        return False
    
    content = read_file(readme_path)
    
    # Remove duplicate sections first
    content = remove_duplicate_sections(content, start_marker, end_marker)
    
    # Find the (now single) occurrence
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    
    if start_idx == -1:
        print(f"Warning: Start marker '{start_marker}' not found in README", file=sys.stderr)
        return False
    
    if end_idx == -1:
        print(f"Error: End marker '{end_marker}' not found in README", file=sys.stderr)
        return False
    
    # Ensure end marker comes after start marker
    if end_idx < start_idx:
        print(f"Error: End marker appears before start marker for {start_marker}", file=sys.stderr)
        return False
    
    # Build new content section
    new_content = f"{start_marker}\n\n"
    if markdown_content.strip():
        new_content += markdown_content.strip()
    else:
        new_content += "*Content will be updated daily via GitHub Actions*\n"
    new_content += f"\n\n{end_marker}"
    
    # Preserve content before and after markers
    before = content[:start_idx]
    after = content[end_idx + len(end_marker):]
    
    # Reconstruct with new section
    updated_content = before + new_content + after
    
    # Check if content actually changed
    if updated_content == content:
        return False
    
    write_file(readme_path, updated_content)
    print(f"README section {start_marker} updated successfully", file=sys.stderr)
    return True


def update_disclaimer_section(
    readme_path: str,
    start_marker: str = "<!--START_SECTION:disclaimer-->",
    end_marker: str = "<!--END_SECTION:disclaimer-->",
) -> bool:
    """
    Update disclaimer section with current timestamp and all sources.
    Returns True if file was modified, False otherwise.
    """
    if not os.path.exists(readme_path):
        return False
    
    # Get current UTC time
    utc_now = datetime.now(pytz.UTC)
    timestamp = utc_now.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    content = read_file(readme_path)
    
    # Check if markers exist
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    
    if start_idx == -1 or end_idx == -1:
        # Markers don't exist, skip
        return False
    
    # Build new disclaimer content
    disclaimer_content = f"""**Last Updated:** {timestamp}

*Disclaimer: All sections are automatically generated by AI and updated daily via GitHub Actions. Content is aggregated from multiple sources:*

- **AI News**: YouTube, Twitter/X, Reddit (r/MachineLearning, r/artificial), TechCrunch, Hacker News
- **Business News**: CNN Business, Fox Business, NBC News, WSJ, NYTimes
- **Tech News**: TechCrunch, Hacker News, Reddit (r/technology, r/programming)
- **Podcasts**: All In, Pivot, Lenny Podcast, Joe Rogan Experience (YouTube)
- **Motivation Quotes**: Reddit (r/getmotivated, r/motivation, r/quotes)
- **Wise Knowledge**: Reddit (r/stoicism, r/philosophy, r/ZenHabits, r/Meditation)

*All content is summarized using AI. Stories, quotes, and knowledge snippets are compiled without human review.*"""
    
    new_content = f"{start_marker}\n{disclaimer_content}\n{end_marker}"
    
    # Preserve content before and after markers
    before = content[:start_idx]
    after = content[end_idx + len(end_marker):]
    
    # Reconstruct with new disclaimer section
    updated_content = before + new_content + after
    
    # Check if content actually changed
    if updated_content == content:
        return False
    
    write_file(readme_path, updated_content)
    print(f"Disclaimer section updated with timestamp: {timestamp}", file=sys.stderr)
    return True


def main():
    """Main execution function."""
    # Get file paths from environment or use defaults
    readme_path = os.getenv("README_PATH", "README.md")
    
    # Expect JSON input file from summarize_content.py
    content_json_path = os.getenv("CONTENT_JSON", "")
    
    if not content_json_path or not os.path.exists(content_json_path):
        print(f"Warning: Content JSON file not found at {content_json_path}", file=sys.stderr)
        # Try default path
        content_json_path = "/tmp/content_summary.json"
        if not os.path.exists(content_json_path):
            print("Error: No content JSON file available", file=sys.stderr)
            sys.exit(1)
    
    # Read content JSON
    with open(content_json_path, "r", encoding="utf-8") as f:
        content_data = f.read()
    
    # Update each section
    sections = [
        ("ai_news", "<!--START_SECTION:ai_news-->", "<!--END_SECTION:ai_news-->"),
        ("business_news", "<!--START_SECTION:business_news-->", "<!--END_SECTION:business_news-->"),
        ("tech_news", "<!--START_SECTION:tech_news-->", "<!--END_SECTION:tech_news-->"),
        ("podcasts", "<!--START_SECTION:podcasts-->", "<!--END_SECTION:podcasts-->"),
    ]
    
    updated = False
    for section_key, start_marker, end_marker in sections:
        markdown = extract_content_markdown(content_data, section_key)
        # Always try to update, even if markdown is empty (to clear old content)
        section_updated = update_readme_section(readme_path, markdown or "", start_marker, end_marker)
        if section_updated:
            updated = True
    
    # Update disclaimer section
    disclaimer_updated = update_disclaimer_section(readme_path)
    
    if updated or disclaimer_updated:
        print("README updated successfully", file=sys.stderr)
        sys.exit(0)
    else:
        print("README unchanged", file=sys.stderr)
        sys.exit(0)  # Exit 0 even if no changes


if __name__ == "__main__":
    main()
