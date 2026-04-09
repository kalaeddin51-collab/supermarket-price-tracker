"""Alert evaluation engine.

Runs after each scrape cycle.  Compares the two most-recent price records for
every watchlist entry and generates AlertEvent rows for:
  - price_drop        — price fell by at least the configured threshold
  - below_threshold   — price crossed below a fixed target price
  - back_in_stock     — item was out-of-stock and is now available
  - on_special        — item just went on special

Alerts are only sent on the user's configured notification days (notify_days).
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app import models
from app.notifiers.email import send_digest, build_digest_html
from app.notifiers.push  import send_push


# ─────────────────────────────────────────────────────────────────────────────

def should_notify_today(settings: models.NotificationSettings) -> bool:
    """Return True if today is one of the user's configured notification days."""
    today = datetime.now().weekday()  # 0=Mon … 6=Sun
    try:
        days = [int(d) for d in settings.notify_days.split(",") if d.strip()]
    except Exception:
        days = list(range(7))
    return today in days


def within_quiet_hours(settings: models.NotificationSettings) -> bool:
    """Return True if the current hour falls inside the quiet-hours window."""
    if settings.quiet_hours_start is None or settings.quiet_hours_end is None:
        return False
    hour = datetime.now().hour
    s, e = settings.quiet_hours_start, settings.quiet_hours_end
    if s <= e:
        return s <= hour < e
    # Overnight window, e.g. 22 → 07
    return hour >= s or hour < e


def evaluate_alerts(db: Session) -> list[models.AlertEvent]:
    """
    Evaluate all watchlist entries and persist new AlertEvent rows.
    Returns the list of new events created.
    """
    settings = db.query(models.NotificationSettings).first()
    if not settings:
        return []

    if not should_notify_today(settings):
        print("[alerts] Not a notification day — skipping evaluation")
        return []

    if within_quiet_hours(settings):
        print("[alerts] Within quiet hours — skipping evaluation")
        return []

    new_events: list[models.AlertEvent] = []

    for entry in db.query(models.WatchlistEntry).all():
        history = (
            db.query(models.PriceRecord)
            .filter(models.PriceRecord.product_id == entry.product_id)
            .order_by(models.PriceRecord.scraped_at.desc())
            .limit(2)
            .all()
        )
        if len(history) < 2:
            continue

        current, previous = history[0], history[1]

        # ── Price drop ────────────────────────────────────────────────────
        if current.price and previous.price and current.price < previous.price:
            drop_pct = (previous.price - current.price) / previous.price * 100
            threshold = entry.alert_drop_pct or settings.global_min_drop_pct
            if drop_pct >= threshold:
                new_events.append(models.AlertEvent(
                    watchlist_entry_id=entry.id,
                    trigger_type="price_drop",
                    old_price=previous.price,
                    new_price=current.price,
                ))

        # ── Below fixed threshold ────────────────────────────────────────
        if (entry.alert_price_below
                and current.price
                and current.price <= entry.alert_price_below
                and (not previous.price or previous.price > entry.alert_price_below)):
            new_events.append(models.AlertEvent(
                watchlist_entry_id=entry.id,
                trigger_type="below_threshold",
                old_price=previous.price,
                new_price=current.price,
            ))

        # ── Back in stock ────────────────────────────────────────────────
        if settings.notify_back_in_stock and current.in_stock and not previous.in_stock:
            new_events.append(models.AlertEvent(
                watchlist_entry_id=entry.id,
                trigger_type="back_in_stock",
                old_price=previous.price,
                new_price=current.price,
            ))

        # ── Went on special ──────────────────────────────────────────────
        if settings.notify_on_special and current.on_special and not previous.on_special:
            new_events.append(models.AlertEvent(
                watchlist_entry_id=entry.id,
                trigger_type="on_special",
                old_price=previous.price,
                new_price=current.price,
            ))

    if new_events:
        for ev in new_events:
            db.add(ev)
        db.commit()
        print(f"[alerts] {len(new_events)} new alert event(s) saved")
        _dispatch_notifications(new_events, settings, db)

    return new_events


def _dispatch_notifications(
    events: list[models.AlertEvent],
    settings: models.NotificationSettings,
    db: Session,
):
    """Send email digest and/or push notifications for a batch of alert events."""
    # Build rich items list
    items = []
    for ev in events:
        entry   = db.query(models.WatchlistEntry).get(ev.watchlist_entry_id)
        if not entry:
            continue
        product = entry.product
        if ev.trigger_type == "price_drop" and not entry.notify_email:
            continue
        items.append({"product": product, "event": ev})

    if not items:
        return

    now = datetime.utcnow()

    # ── Email ─────────────────────────────────────────────────────────────
    if settings.email_enabled and settings.email_address:
        recipients = [a for a in [
            settings.email_address,
            getattr(settings, "email_address_2", None),
            getattr(settings, "email_address_3", None),
        ] if a]
        subject  = f"Price Tracker — {len(items)} alert{'s' if len(items) > 1 else ''}"
        html     = build_digest_html(items)
        if send_digest(subject, html, recipients):
            for ev in events:
                ev.notified_at = now

    # ── Push ──────────────────────────────────────────────────────────────
    if settings.ntfy_enabled and settings.ntfy_topic:
        lines = []
        for item in items:
            p  = item["product"]
            ev = item["event"]
            if ev.new_price:
                lines.append(f"{p.name}: ${ev.new_price:.2f}")
        if lines:
            send_push(
                topic   = settings.ntfy_topic,
                title   = f"{len(items)} price alert{'s' if len(items) > 1 else ''}",
                message = "\n".join(lines),
                server  = settings.ntfy_server or "https://ntfy.sh",
                tags    = ["chart_decreasing"],
            )

    db.commit()
