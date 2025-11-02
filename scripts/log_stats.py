#!/usr/bin/env python3
"""
Fetch GitHub developer activity stats for Year-To-Date (YTD).
Includes commits, PRs, and code deltas via GraphQL API.
"""

import os
import sys
import json
from datetime import datetime, timedelta, timezone
import requests
from typing import Dict, List, Optional


def get_github_token() -> str:
    """Get GitHub token from environment variable."""
    token = os.getenv("GITHUB_TOKEN") or os.getenv("PAT_PRIVATE")
    if not token:
        raise ValueError("GITHUB_TOKEN or PAT_PRIVATE environment variable is required")
    return token


def get_username() -> str:
    """Get GitHub username from environment or default."""
    return os.getenv("GITHUB_USERNAME", "ftchvs")


def query_contributions(token: str, username: str, since: str) -> Dict:
    """Query GitHub GraphQL API for contribution statistics."""
    query = """
    query($username: String!, $since: DateTime!) {
      user(login: $username) {
        contributionsCollection(from: $since) {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          contributionCalendar {
            totalContributions
          }
        }
      }
    }
    """
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    variables = {
        "username": username,
        "since": since,
    }
    
    response = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers=headers,
        timeout=30,
    )
    
    if response.status_code != 200:
        raise Exception(f"GraphQL query failed: {response.status_code} - {response.text}")
    
    data = response.json()
    if "errors" in data:
        raise Exception(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}")
    
    return data.get("data", {})


def query_recent_commits(token: str, username: str, since: str) -> List[Dict]:
    """Query recent commits via REST API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
    commits = []
    page = 1
    per_page = 100
    
    while True:
        url = f"https://api.github.com/search/commits?q=author:{username}+author-date:>={since}&per_page={per_page}&page={page}"
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            break
        
        data = response.json()
        items = data.get("items", [])
        if not items:
            break
        
        commits.extend(items)
        
        if len(items) < per_page:
            break
        page += 1
    
    return commits


def query_recent_prs(token: str, username: str, since: str) -> Dict:
    """Query recent PRs (open and merged) via REST API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
    # Search for PRs created by user
    created_prs = []
    page = 1
    while True:
        url = f"https://api.github.com/search/issues?q=author:{username}+type:pr+created:>={since}&per_page=100&page={page}"
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            if not items:
                break
            created_prs.extend(items)
            if len(items) < 100:
                break
            page += 1
    
    # Count by state
    open_prs = len([pr for pr in created_prs if pr.get("state") == "open"])
    merged_prs = len([pr for pr in created_prs if pr.get("state") == "closed" and pr.get("pull_request", {}).get("merged_at")])
    
    return {
        "total": len(created_prs),
        "open": open_prs,
        "merged": merged_prs,
        "closed": len([pr for pr in created_prs if pr.get("state") == "closed"]) - merged_prs,
    }


def calculate_line_changes(token: str, commits: List[Dict]) -> Dict:
    """Calculate total additions and deletions from commit details."""
    total_additions = 0
    total_deletions = 0
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
    for commit in commits[:50]:  # Limit to first 50 commits to avoid rate limits
        sha = commit.get("sha")
        repo_url = commit.get("repository", {}).get("url", "")
        if not sha or not repo_url:
            continue
        
        # Extract owner/repo from URL
        parts = repo_url.replace("https://api.github.com/repos/", "").split("/")
        if len(parts) < 2:
            continue
        
        owner, repo = parts[0], parts[1]
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                commit_data = response.json()
                stats = commit_data.get("stats", {})
                total_additions += stats.get("additions", 0)
                total_deletions += stats.get("deletions", 0)
        except Exception:
            continue  # Skip on error
    
    return {
        "additions": total_additions,
        "deletions": total_deletions,
        "net": total_additions - total_deletions,
    }


def format_stats_markdown(stats: Dict, date: str) -> str:
    """Format statistics as markdown."""
    current_year = datetime.now().year
    lines = [
        f"## 📊 Year-To-Date (YTD) Dev Activity - {current_year}",
        "",
        "### Commits & Contributions",
        f"- **Total Commits**: {stats['commits']['total']}",
        f"- **Pull Requests**: {stats['prs']['total']} ({stats['prs']['open']} open, {stats['prs']['merged']} merged)",
        "",
        "### Code Changes",
        f"- **Lines Added**: +{stats['lines']['additions']:,}",
        f"- **Lines Deleted**: -{stats['lines']['deletions']:,}",
        f"- **Net Change**: {stats['lines']['net']:+,}",
        "",
    ]
    return "\n".join(lines)


def save_log(log_content: str, date: str, logs_dir: str = "logs") -> str:
    """Save daily log to file."""
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, f"{date}.md")
    
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(log_content)
    
    return log_file


def main():
    """Main execution function."""
    try:
        token = get_github_token()
        username = get_username()
        
        # Calculate timestamp for Year-To-Date (January 1st of current year)
        now = datetime.now(timezone.utc)
        current_year = now.year
        ytd_start = datetime(current_year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        since_iso = ytd_start.isoformat()
        
        date_str = now.strftime("%Y-%m-%d")
        
        print(f"Fetching GitHub YTD stats for {username} since {since_iso}...", file=sys.stderr)
        
        # Fetch contributions via GraphQL
        contributions_data = query_contributions(token, username, since_iso)
        contributions = contributions_data.get("user", {}).get("contributionsCollection", {})
        
        # Fetch commits via REST (use YYYY-MM-DD format)
        commits = query_recent_commits(token, username, since_iso.split("T")[0])
        
        # Fetch PRs (use YYYY-MM-DD format)
        prs = query_recent_prs(token, username, since_iso.split("T")[0])
        
        # Calculate line changes
        lines = calculate_line_changes(token, commits)
        
        # Compile stats
        stats = {
            "date": date_str,
            "commits": {
                "total": contributions.get("totalCommitContributions", len(commits)),
            },
            "prs": prs,
            "lines": lines,
        }
        
        # Format as markdown
        markdown = format_stats_markdown(stats, date_str)
        
        # Save log
        log_file = save_log(markdown, date_str)
        
        # Output JSON for other scripts to consume (to stdout only)
        output = {
            "date": date_str,
            "markdown": markdown,
            "stats": stats,
        }
        
        # Print status to stderr, JSON to stdout
        print(f"Log saved to {log_file}", file=sys.stderr)
        print(json.dumps(output))
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

