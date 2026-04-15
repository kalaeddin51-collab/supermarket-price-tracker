"""SMTP email sender with auto-configuration for Gmail, Yahoo, Hotmail."""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# Auto-detect SMTP settings by email domain
SMTP_PRESETS = {
    "gmail.com":       ("smtp.gmail.com",          587),
    "googlemail.com":  ("smtp.gmail.com",          587),
    "yahoo.com":       ("smtp.mail.yahoo.com",     587),
    "yahoo.com.au":    ("smtp.mail.yahoo.com",     587),
    "hotmail.com":     ("smtp-mail.outlook.com",   587),
    "outlook.com":     ("smtp-mail.outlook.com",   587),
    "live.com":        ("smtp-mail.outlook.com",   587),
    "live.com.au":     ("smtp-mail.outlook.com",   587),
    "icloud.com":      ("smtp.mail.me.com",        587),
}


def smtp_config_for(email: str) -> tuple[str, int]:
    """Return (host, port) for the given email address, or fall back to env vars."""
    domain = email.split("@")[-1].lower() if "@" in email else ""
    if domain in SMTP_PRESETS:
        return SMTP_PRESETS[domain]
    # Fall back to environment overrides
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    return host, port


def send_digest(subject: str, html_body: str, recipients: list[str]) -> bool:
    """
    Send an HTML email to one or more recipients.
    Credentials come from environment variables:
      SMTP_USER     — the sending email address (defaults to first recipient)
      SMTP_PASSWORD — app password / OAuth token
    Returns True on success, False on failure.
    """
    smtp_user = os.getenv("SMTP_USER") or (recipients[0] if recipients else "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_pass:
        print("[email] SMTP_USER or SMTP_PASSWORD not set — skipping send")
        return False

    host, port = smtp_config_for(smtp_user)

    from email.header import Header
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = f"Price Tracker <{smtp_user}>"
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    server = None
    sent = False
    try:
        server = smtplib.SMTP(host, port, timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        # send_message handles UTF-8 / emoji encoding correctly on all platforms
        server.send_message(msg)
        print(f"[email] Sent '{subject}' to {recipients}")
        sent = True
    except Exception as exc:
        print(f"[email] Send failed: {exc}")
        sent = False
    finally:
        # Yahoo (and some others) drop the connection after QUIT — ignore close errors
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass
    return sent


def build_digest_html(items: list[dict]) -> str:
    """Build a simple HTML email body from a list of alert dicts."""
    rows = ""
    for item in items:
        product  = item["product"]
        event    = item["event"]
        old_p    = f"${event.old_price:.2f}" if event.old_price else "—"
        new_p    = f"${event.new_price:.2f}" if event.new_price else "—"
        trigger  = event.trigger_type.replace("_", " ").title()
        rows += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0">
            <strong>{product.name}</strong><br>
            <small style="color:#666">{product.store}</small>
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;color:#059669;font-weight:600">{trigger}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;text-decoration:line-through;color:#999">{old_p}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;font-weight:700;color:#111">{new_p}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333">
  <div style="background:#059669;color:white;padding:16px 20px;border-radius:8px 8px 0 0">
    <h2 style="margin:0;font-size:18px">🛒 Price Tracker — Digest</h2>
    <p style="margin:4px 0 0;font-size:12px;opacity:.8">{datetime.now().strftime('%A, %d %B %Y')}</p>
  </div>
  <table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-top:none">
    <thead>
      <tr style="background:#f9fafb">
        <th style="padding:8px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase">Product</th>
        <th style="padding:8px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase">Alert</th>
        <th style="padding:8px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase">Was</th>
        <th style="padding:8px 12px;text-align:left;font-size:11px;color:#6b7280;text-transform:uppercase">Now</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="font-size:11px;color:#9ca3af;margin-top:16px;text-align:center">
    Price Tracker · North Sydney · Manage alerts at http://localhost:8000/settings
  </p>
</body>
</html>"""
