#!/usr/bin/env python3
"""
Update README.md by injecting content between comment markers.
Replaces everything between <!--START_SECTION:daily--> and <!--END_SECTION:daily-->.
"""

import os
import sys
import json
from typing import Optional


def read_file(filepath: str) -> str:
    """Read file content."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def write_file(filepath: str, content: str):
    """Write content to file."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def extract_stats_markdown(stats_json: str) -> str:
    """Extract markdown from stats JSON output."""
    try:
        data = json.loads(stats_json)
        return data.get("markdown", "")
    except (json.JSONDecodeError, TypeError):
        # If not JSON, assume it's already markdown
        return stats_json


def extract_ai_markdown(ai_json: str) -> str:
    """Extract markdown from AI summary JSON output."""
    try:
        data = json.loads(ai_json)
        return data.get("markdown", "")
    except (json.JSONDecodeError, TypeError):
        # If not JSON, assume it's already markdown
        return ai_json


def update_readme_section(
    readme_path: str,
    stats_markdown: str,
    ai_markdown: str,
    start_marker: str = "<!--START_SECTION:daily-->",
    end_marker: str = "<!--END_SECTION:daily-->",
) -> bool:
    """
    Update README.md by replacing ALL content between markers.
    Returns True if file was modified, False otherwise.
    """
    if not os.path.exists(readme_path):
        print(f"Error: README file not found at {readme_path}", file=sys.stderr)
        return False
    
    content = read_file(readme_path)
    
    # Check if markers exist
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    
    if start_idx == -1:
        print(f"Warning: Start marker '{start_marker}' not found in README", file=sys.stderr)
        print("Adding markers after header section...", file=sys.stderr)
        # Add markers after the table section if they don't exist
        # Look for end of table or profile section
        insert_point = content.find("</table>")
        if insert_point == -1:
            insert_point = content.find("## Strengths")
        if insert_point == -1:
            insert_point = len(content)
        
        # Insert markers
        new_section = f"\n\n{start_marker}\n\n{end_marker}\n\n"
        content = content[:insert_point] + new_section + content[insert_point:]
        # Re-find indices after insertion
        start_idx = content.find(start_marker)
        end_idx = content.find(end_marker)
    
    if end_idx == -1:
        print(f"Error: End marker '{end_marker}' not found in README", file=sys.stderr)
        return False
    
    # Build new content section - clean replacement
    new_content = f"{start_marker}\n\n"
    new_content += stats_markdown.strip()
    new_content += "\n\n---\n\n"
    new_content += ai_markdown.strip()
    new_content += f"\n\n{end_marker}"
    
    # Preserve content before and after markers
    before = content[:start_idx]
    after = content[end_idx + len(end_marker):]
    
    # Reconstruct with new section (completely replacing everything between markers)
    updated_content = before + new_content + after
    
    # Check if content actually changed
    if updated_content == content:
        print("No changes detected, skipping update", file=sys.stderr)
        return False
    
    write_file(readme_path, updated_content)
    print(f"README section updated successfully at {readme_path}", file=sys.stderr)
    return True


def main():
    """Main execution function."""
    # Get file paths from environment or use defaults
    readme_path = os.getenv("README_PATH", "README.md")
    
    # Expect JSON input files from previous scripts
    stats_json_path = os.getenv("STATS_JSON", "")
    ai_json_path = os.getenv("AI_JSON", "")
    
    stats_markdown = ""
    ai_markdown = ""
    
    # Read stats JSON
    if stats_json_path and os.path.exists(stats_json_path):
        with open(stats_json_path, "r", encoding="utf-8") as f:
            stats_data = f.read()
            stats_markdown = extract_stats_markdown(stats_data)
    
    # Read AI JSON
    if ai_json_path and os.path.exists(ai_json_path):
        with open(ai_json_path, "r", encoding="utf-8") as f:
            ai_data = f.read()
            ai_markdown = extract_ai_markdown(ai_data)
    
    # Fallback: create placeholder if no data
    if not stats_markdown:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        stats_markdown = f"## 📊 Daily Dev Activity - {date_str}\n\n*No activity data available for today.*\n"
    
    if not ai_markdown:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        ai_markdown = f"## 🤖 AI Industry Snapshot - {date_str}\n\n*No AI news available for today.*\n"
    
    # Update README
    updated = update_readme_section(readme_path, stats_markdown, ai_markdown)
    
    if updated:
        print("README section updated successfully")
        sys.exit(0)
    else:
        print("README section unchanged")
        sys.exit(0)  # Exit 0 even if no changes


if __name__ == "__main__":
    main()

