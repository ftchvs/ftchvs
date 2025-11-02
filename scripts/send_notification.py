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
    """Send email via SendGrid API."""
    try:
        import requests
        
        from_email = from_email or "noreply@ftchvs.github.io"
        
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "personalizations": [{
                "to": [{"email": to_email}]
            }],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{
                "type": "text/html",
                "value": content.replace("\n", "<br>")
            }]
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return True
        
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


def format_digest_notification(ai_json_path: str, stats_json_path: str) -> tuple[str, str]:
    """Format notification content from JSON files."""
    try:
        # Read AI summary
        ai_data = {}
        if ai_json_path and os.path.exists(ai_json_path):
            with open(ai_json_path, "r", encoding="utf-8") as f:
                ai_data = json.loads(f.read())
        
        # Read stats
        stats_data = {}
        if stats_json_path and os.path.exists(stats_json_path):
            with open(stats_json_path, "r", encoding="utf-8") as f:
                stats_data = json.loads(f.read())
        
        # Format subject
        date_str = ai_data.get("date", stats_data.get("date", ""))
        subject = f"🤖 Daily AI Digest - {date_str}"
        
        # Format content
        content_lines = [
            f"<h2>Daily AI Digest - {date_str}</h2>",
            "<hr>",
        ]
        
        # Add AI summary
        if ai_data.get("summary"):
            content_lines.append("<h3>AI Trends Summary</h3>")
            content_lines.append(f"<p>{ai_data.get('summary', '')}</p>")
        
        # Add top stories
        stories = ai_data.get("stories", [])
        if stories:
            content_lines.append("<h3>Top AI Stories</h3>")
            content_lines.append("<ul>")
            for story in stories[:5]:
                title = story.get("title", "")
                url = story.get("hn_url") or story.get("url", "#")
                content_lines.append(f'<li><a href="{url}">{title}</a></li>')
            content_lines.append("</ul>")
        
        content = "\n".join(content_lines)
        
        # Plain text version for SMS
        sms_lines = [f"Daily AI Digest - {date_str}"]
        if ai_data.get("summary"):
            sms_lines.append(f"\n{ai_data.get('summary', '')}")
        if stories:
            sms_lines.append("\nTop Stories:")
            for story in stories[:3]:  # Limit to 3 for SMS
                sms_lines.append(f"- {story.get('title', '')}")
        
        sms_content = "\n".join(sms_lines)
        
        return subject, content, sms_content
        
    except Exception as e:
        print(f"Error formatting notification: {e}", file=sys.stderr)
        return "Daily AI Digest", "Error formatting digest content.", "Daily AI Digest - Error formatting content."


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
        
        success = send_email_sendgrid(
            api_key=api_key,
            to_email=to_email,
            subject=subject,
            content=email_content
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
