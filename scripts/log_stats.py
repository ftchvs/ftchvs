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
    """Get GitHub token from environment variable or stored PAT file."""
    # Try environment variables first
    token = os.getenv("GITHUB_TOKEN") or os.getenv("PAT_PRIVATE")
    if token:
        return token
    
    # Try to load from encrypted storage
    try:
        from pathlib import Path
        from cryptography.fernet import Fernet
        import json
        import base64
        
        pat_storage_dir = Path("~/.ftchvs").expanduser()
        pat_file = pat_storage_dir / "pat_token.enc"
        key_file = pat_storage_dir / "pat_key.key"
        
        if pat_file.exists() and key_file.exists():
            with open(key_file, "rb") as f:
                key = f.read()
            fernet = Fernet(key)
            
            with open(pat_file, "r") as f:
                data = json.load(f)
                encrypted_token = data.get("token")
                if encrypted_token:
                    encrypted_bytes = base64.b64decode(encrypted_token.encode())
                    return fernet.decrypt(encrypted_bytes).decode()
    except Exception as e:
        print(f"Warning: Could not load PAT from storage: {e}", file=sys.stderr)
    
    # No token found
    raise ValueError("GITHUB_TOKEN, PAT_PRIVATE environment variable, or stored PAT file required")


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
    """Query comprehensive PR stats: created, contributed, reviewed, and managed."""
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
    
    # Search for PRs where user contributed (as committer, not just author)
    contributed_prs = []
    page = 1
    while True:
        url = f"https://api.github.com/search/issues?q=committer:{username}+type:pr+created:>={since}&per_page=100&page={page}"
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            if not items:
                break
            contributed_prs.extend(items)
            if len(items) < 100:
                break
            page += 1
    
    # Search for PRs reviewed by user
    reviewed_prs = []
    page = 1
    while True:
        url = f"https://api.github.com/search/issues?q=reviewed-by:{username}+type:pr+created:>={since}&per_page=100&page={page}"
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            if not items:
                break
            reviewed_prs.extend(items)
            if len(items) < 100:
                break
            page += 1
    
    # Count created PRs by state
    created_open = len([pr for pr in created_prs if pr.get("state") == "open"])
    created_merged = len([pr for pr in created_prs if pr.get("state") == "closed" and pr.get("pull_request", {}).get("merged_at")])
    created_closed = len([pr for pr in created_prs if pr.get("state") == "closed"]) - created_merged
    
    # Get unique contributed PRs (excluding those already in created)
    created_pr_ids = {pr.get("number") for pr in created_prs}
    unique_contributed = [pr for pr in contributed_prs if pr.get("number") not in created_pr_ids]
    contributed_merged = len([pr for pr in unique_contributed if pr.get("state") == "closed" and pr.get("pull_request", {}).get("merged_at")])
    
    # Count reviewed PRs
    reviewed_merged = len([pr for pr in reviewed_prs if pr.get("state") == "closed" and pr.get("pull_request", {}).get("merged_at")])
    
    return {
        "created": len(created_prs),
        "created_open": created_open,
        "created_merged": created_merged,
        "created_closed": created_closed,
        "contributed": len(unique_contributed),
        "contributed_merged": contributed_merged,
        "reviewed": len(reviewed_prs),
        "reviewed_merged": reviewed_merged,
        "total": len(created_prs) + len(unique_contributed) + len(reviewed_prs),
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
    prs = stats['prs']
    lines = [
        f"## 📊 Year-To-Date (YTD) Dev Activity - {current_year}",
        "",
        "### Commits & Contributions",
        f"- **Total Commits**: {stats['commits']['total']}",
        "",
        "### Pull Requests",
        f"- **Created**: {prs['created']} ({prs['created_open']} open, {prs['created_merged']} merged, {prs['created_closed']} closed)",
        f"- **Contributed To**: {prs['contributed']} ({prs['contributed_merged']} merged)",
        f"- **Reviewed**: {prs['reviewed']} ({prs['reviewed_merged']} merged)",
        f"- **Total PR Activity**: {prs['total']}",
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

