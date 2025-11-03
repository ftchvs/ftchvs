#!/usr/bin/env python3
"""
Send email or SMS notifications via SendGrid (email) or Twilio (SMS).
"""

import os
import sys
import json
from typing import Optional


def send_email_sendgrid(
    api_key: str,
    to_email: str,
    subject: str,
    content: str,
    from_email: Optional[str] = None
) -> bool:
    """Send email via SendGrid Python SDK."""
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        
        from_email = from_email or "noreply@ftchvs.github.io"
        
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=content
        )
        
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        
        if response.status_code in [200, 201, 202]:
            print(f"Email sent successfully. Status: {response.status_code}", file=sys.stderr)
            return True
        else:
            print(f"Email send returned status {response.status_code}", file=sys.stderr)
            return False
        
    except Exception as e:
        print(f"Error sending email via SendGrid: {e}", file=sys.stderr)
        return False


def send_sms_twilio(
    account_sid: str,
    auth_token: str,
    to_phone: str,
    from_phone: str,
    message: str
) -> bool:
    """Send SMS via Twilio API."""
    try:
        from twilio.rest import Client
        
        client = Client(account_sid, auth_token)
        
        message_obj = client.messages.create(
            body=message,
            from_=from_phone,
            to=to_phone
        )
        
        print(f"SMS sent successfully. SID: {message_obj.sid}", file=sys.stderr)
        return True
        
    except Exception as e:
        print(f"Error sending SMS via Twilio: {e}", file=sys.stderr)
        return False


def format_digest_notification(ai_json_path: str, stats_json_path: str) -> tuple[str, str, str]:
    """Format notification content from JSON files."""
    try:
        # Read content summary (now includes multiple sections)
        content_data = {}
        if ai_json_path and os.path.exists(ai_json_path):
            with open(ai_json_path, "r", encoding="utf-8") as f:
                content_data = json.loads(f.read())
        
        # Read stats
        stats_data = {}
        if stats_json_path and os.path.exists(stats_json_path):
            with open(stats_json_path, "r", encoding="utf-8") as f:
                stats_data = json.loads(f.read())
        
        # Format subject
        date_str = content_data.get("date", stats_data.get("date", ""))
        subject = f"📊 Daily Digest - {date_str}"
        
        # Format content
        content_lines = [
            f"<h2>Daily Digest - {date_str}</h2>",
            "<hr>",
        ]
        
        # Add AI News section
        ai_news = content_data.get("ai_news", {})
        if ai_news.get("summary") or ai_news.get("stories"):
            content_lines.append("<h3>🤖 AI Industry Snapshot</h3>")
            if ai_news.get("summary"):
                content_lines.append(f"<p><strong>Summary:</strong> {ai_news.get('summary', '')}</p>")
            
            stories = ai_news.get("stories", [])
            if stories:
                content_lines.append("<h4>Top AI Stories</h4>")
                content_lines.append("<ul>")
                for story in stories[:5]:
                    title = story.get("title", "")
                    url = story.get("hn_url") or story.get("url", "#")
                    content_lines.append(f'<li><a href="{url}">{title}</a></li>')
                content_lines.append("</ul>")
            content_lines.append("<hr>")
        
        # Add Business News section
        business_news = content_data.get("business_news", {})
        if business_news.get("summary") or business_news.get("stories"):
            content_lines.append("<h3>💼 Business News</h3>")
            if business_news.get("summary"):
                content_lines.append(f"<p>{business_news.get('summary', '')}</p>")
            
            stories = business_news.get("stories", [])
            if stories:
                content_lines.append("<ul>")
                for story in stories[:5]:
                    title = story.get("title", "")
                    url = story.get("url", "#")
                    content_lines.append(f'<li><a href="{url}">{title}</a></li>')
                content_lines.append("</ul>")
            content_lines.append("<hr>")
        
        # Add Tech News section
        tech_news = content_data.get("tech_news", {})
        if tech_news.get("summary") or tech_news.get("stories"):
            content_lines.append("<h3>💻 Tech News</h3>")
            if tech_news.get("summary"):
                content_lines.append(f"<p>{tech_news.get('summary', '')}</p>")
            
            stories = tech_news.get("stories", [])
            if stories:
                content_lines.append("<ul>")
                for story in stories[:5]:
                    title = story.get("title", "")
                    url = story.get("url", "#")
                    content_lines.append(f'<li><a href="{url}">{title}</a></li>')
                content_lines.append("</ul>")
            content_lines.append("<hr>")
        
        # Add Motivation Quotes section
        motivation_quotes = content_data.get("motivation_quotes", {})
        if motivation_quotes.get("items"):
            content_lines.append("<h3>💪 Motivation Quotes</h3>")
            items = motivation_quotes.get("items", [])
            content_lines.append("<ul>")
            for item in items[:5]:
                content = item.get("content", item.get("title", ""))
                url = item.get("url", "#")
                source = item.get("source", "")
                content_lines.append(f'<li>"{content[:200]}" <em>(<a href="{url}">{source}</a>)</em></li>')
            content_lines.append("</ul>")
            content_lines.append("<hr>")
        
        # Add Wise Knowledge section
        wise_knowledge = content_data.get("wise_knowledge", {})
        if wise_knowledge.get("items"):
            content_lines.append("<h3>🧠 Wise Knowledge</h3>")
            items = wise_knowledge.get("items", [])
            content_lines.append("<ul>")
            for item in items[:5]:
                content = item.get("content", item.get("title", ""))
                url = item.get("url", "#")
                source = item.get("source", "")
                content_lines.append(f'<li>"{content[:200]}" <em>(<a href="{url}">{source}</a>)</em></li>')
            content_lines.append("</ul>")
        
        # Add footer
        content_lines.append("<hr>")
        content_lines.append("<p><small>Generated automatically via GitHub Actions</small></p>")
        
        content = "\n".join(content_lines)
        
        # Ensure we have some content - if nothing was added, provide a fallback
        if len(content_lines) <= 3:  # Only header, hr, and footer
            content_lines.insert(1, "<p>Content is being processed. Check back later for updates.</p>")
            content = "\n".join(content_lines)
        
        # Debug: log what we're sending
        print(f"Email content length: {len(content)} characters", file=sys.stderr)
        print(f"Content preview: {content[:200]}...", file=sys.stderr)
        
        # Plain text version for SMS (shorter)
        sms_lines = [f"Daily Digest - {date_str}"]
        
        if ai_news.get("summary"):
            sms_lines.append(f"\n🤖 AI: {ai_news.get('summary', '')[:150]}")
        
        if business_news.get("summary"):
            sms_lines.append(f"\n💼 Business: {business_news.get('summary', '')[:150]}")
        
        motivation_items = motivation_quotes.get("items", [])
        if motivation_items:
            sms_lines.append(f"\n💪 Quote: {motivation_items[0].get('content', '')[:150]}")
        
        sms_content = "\n".join(sms_lines)
        
        return subject, content, sms_content
        
    except Exception as e:
        print(f"Error formatting notification: {e}", file=sys.stderr)
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
        return "Daily Digest", "<p>Error formatting digest content.</p>", "Daily Digest - Error formatting content."


def main():
    """Main execution function."""
    # Get notification type
    notify_type = os.getenv("NOTIFY_TYPE", "").lower()  # "email" or "sms"
    
    if not notify_type:
        print("No notification type specified. Set NOTIFY_TYPE=email or NOTIFY_TYPE=sms", file=sys.stderr)
        sys.exit(0)
    
    # Get file paths
    ai_json = os.getenv("AI_JSON", "/tmp/ai_summary.json")
    stats_json = os.getenv("STATS_JSON", "/tmp/github_stats.json")
    
    # Format notification
    subject, email_content, sms_content = format_digest_notification(ai_json, stats_json)
    
    success = False
    
    if notify_type == "email":
        # Send email via SendGrid
        api_key = os.getenv("SENDGRID_API_KEY")
        to_email = os.getenv("NOTIFY_EMAIL")
        
        if not api_key or not to_email:
            print("Error: SENDGRID_API_KEY and NOTIFY_EMAIL required for email", file=sys.stderr)
            sys.exit(1)
        
        # Get from_email from environment or use default
        from_email = os.getenv("SENDGRID_FROM_EMAIL")
        
        success = send_email_sendgrid(
            api_key=api_key,
            to_email=to_email,
            subject=subject,
            content=email_content,
            from_email=from_email
        )
        
    elif notify_type == "sms":
        # Send SMS via Twilio
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        to_phone = os.getenv("NOTIFY_PHONE")
        from_phone = os.getenv("TWILIO_PHONE_NUMBER")
        
        if not all([account_sid, auth_token, to_phone, from_phone]):
            print("Error: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, NOTIFY_PHONE, and TWILIO_PHONE_NUMBER required", file=sys.stderr)
            sys.exit(1)
        
        success = send_sms_twilio(
            account_sid=account_sid,
            auth_token=auth_token,
            to_phone=to_phone,
            from_phone=from_phone,
            message=sms_content
        )
    
    if success:
        print(f"Notification sent successfully via {notify_type}", file=sys.stderr)
        sys.exit(0)
    else:
        print(f"Failed to send notification via {notify_type}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
