"""
Email sender — tries Resend HTTP API first, falls back to SMTP.

Resend (https://resend.com) works on Railway and any cloud host because it
uses HTTPS (port 443) instead of SMTP ports (587/465) which are blocked by
most cloud providers to prevent spam.

SMTP fallback is kept for self-hosted / local deployments where port 587
is available.
"""
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
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    return host, port


def _send_via_resend(api_key: str, subject: str, html_body: str,
                     from_addr: str, recipients: list[str]) -> bool:
    """Send via Resend HTTP API — works on Railway (HTTPS only, port 443)."""
    import httpx
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json={
                "from":    from_addr,
                "to":      recipients,
                "subject": subject,
                "html":    html_body,
            },
            timeout=20,
        )
        if resp.status_code in (200, 201):
            print(f"[email/resend] Sent '{subject}' to {recipients}")
            send_digest._last_error = ""  # type: ignore[attr-defined]
            return True
        else:
            err = f"Resend API error {resp.status_code}: {resp.text[:300]}"
            print(f"[email/resend] {err}")
            send_digest._last_error = err  # type: ignore[attr-defined]
            return False
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        print(f"[email/resend] Exception: {err}")
        send_digest._last_error = err  # type: ignore[attr-defined]
        return False


def _send_via_smtp(subject: str, html_body: str, recipients: list[str]) -> bool:
    """Send via SMTP — works on local/self-hosted, blocked on most cloud hosts."""
    smtp_user = os.getenv("SMTP_USER") or (recipients[0] if recipients else "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_pass:
        send_digest._last_error = "SMTP_USER or SMTP_PASSWORD not set"  # type: ignore[attr-defined]
        return False

    host, port = smtp_config_for(smtp_user)

    from email.header import Header
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = f"Price Tracker <{smtp_user}>"
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    server = None
    try:
        server = smtplib.SMTP(host, port, timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        print(f"[email/smtp] Sent '{subject}' to {recipients}")
        send_digest._last_error = ""  # type: ignore[attr-defined]
        return True
    except smtplib.SMTPAuthenticationError as exc:
        err = f"Auth failed ({exc.smtp_code}): {exc.smtp_error.decode(errors='replace') if isinstance(exc.smtp_error, bytes) else exc.smtp_error}"
        print(f"[email/smtp] {err}")
        send_digest._last_error = err  # type: ignore[attr-defined]
        return False
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        print(f"[email/smtp] {err}")
        send_digest._last_error = err  # type: ignore[attr-defined]
        return False
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


def send_digest(subject: str, html_body: str, recipients: list[str],
                resend_api_key: str | None = None,
                resend_from: str = "Price Tracker <onboarding@resend.dev>") -> bool:
    """
    Send an HTML email.  Tries Resend first if an API key is supplied,
    otherwise falls back to SMTP via env vars SMTP_USER / SMTP_PASSWORD.

    Returns True on success, False on failure.
    Sets send_digest._last_error with a human-readable failure reason.
    """
    send_digest._last_error = ""  # type: ignore[attr-defined]

    if resend_api_key:
        return _send_via_resend(resend_api_key, subject, html_body, resend_from, recipients)

    # No Resend key — try SMTP
    return _send_via_smtp(subject, html_body, recipients)


def diagnose_resend(api_key: str, from_addr: str, to_addr: str) -> dict:
    """
    Send a real minimal email via Resend and return a diagnosis dict:
      { "ok": bool, "status": int, "detail": str }

    Useful for the settings diagnostics panel to show the exact Resend response.
    """
    import httpx
    if not api_key:
        return {"ok": False, "status": 0, "detail": "No Resend API key configured."}
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from":    from_addr,
                "to":      [to_addr],
                "subject": "Price Tracker — Email Diagnostics Test",
                "html":    "<p>This is an automated diagnostics test from your Price Tracker app. "
                           "If you received this, email delivery is working correctly ✅</p>",
            },
            timeout=20,
        )
        ok = resp.status_code in (200, 201)
        try:
            body = resp.json()
            detail = body.get("message") or body.get("name") or str(body)
        except Exception:
            detail = resp.text[:300]
        return {"ok": ok, "status": resp.status_code, "detail": detail if not ok else "Email sent successfully ✅"}
    except Exception as exc:
        return {"ok": False, "status": 0, "detail": f"{type(exc).__name__}: {exc}"}


def build_digest_html(items: list[dict]) -> str:
    """Build a simple HTML email body from a list of alert dicts."""
    rows = ""
    for item in items:
        product = item["product"]
        event   = item["event"]
        old_p   = f"${event.old_price:.2f}" if event.old_price else "—"
        new_p   = f"${event.new_price:.2f}" if event.new_price else "—"
        trigger = event.trigger_type.replace("_", " ").title()
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
    Price Tracker · Manage alerts in the app settings
  </p>
</body>
</html>"""
