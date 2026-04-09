"""Push notifications via ntfy.sh."""
import urllib.request
import urllib.error
import json


def send_push(topic: str, title: str, message: str, server: str = "https://ntfy.sh",
              priority: str = "default", tags: list[str] | None = None) -> bool:
    """
    Send a push notification to an ntfy topic.
    Returns True on success, False on failure.
    """
    if not topic:
        print("[push] No ntfy topic configured — skipping")
        return False

    url = f"{server.rstrip('/')}/{topic}"
    payload = json.dumps({
        "topic":    topic,
        "title":    title,
        "message":  message,
        "priority": priority,
        "tags":     tags or ["shopping_cart"],
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status < 300
            if ok:
                print(f"[push] Sent '{title}' to ntfy:{topic}")
            return ok
    except Exception as exc:
        print(f"[push] Send failed: {exc}")
        return False
