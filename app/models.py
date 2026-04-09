from datetime import datetime
from sqlalchemy import (
    Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    preference: Mapped["UserPreference | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    suburb: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stores: Mapped[str | None] = mapped_column(String(300), nullable=True)  # comma-separated slugs
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="preference")


class Store(enum.Enum):
    woolworths = "woolworths"
    coles = "coles"
    harris_farm = "harris_farm"
    iga_crows_nest = "iga_crows_nest"
    iga_milsons_point = "iga_milsons_point"
    iga_north_sydney = "iga_north_sydney"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    store: Mapped[str] = mapped_column(SAEnum(Store))
    external_id: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    price_history: Mapped[list["PriceRecord"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    watchlist_entries: Mapped[list["WatchlistEntry"]] = relationship(back_populates="product", cascade="all, delete-orphan")

    def latest_price(self) -> "PriceRecord | None":
        if not self.price_history:
            return None
        return max(self.price_history, key=lambda r: r.scraped_at)


class PriceRecord(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    was_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    on_special: Mapped[bool] = mapped_column(Boolean, default=False)
    scrape_error: Mapped[bool] = mapped_column(Boolean, default=False)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["Product"] = relationship(back_populates="price_history")


class WatchlistEntry(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    alert_drop_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_price_below: Mapped[float | None] = mapped_column(Float, nullable=True)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_push: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="watchlist_entries")
    alert_events: Mapped[list["AlertEvent"]] = relationship(back_populates="watchlist_entry", cascade="all, delete-orphan")


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watchlist_entry_id: Mapped[int] = mapped_column(ForeignKey("watchlist.id"))
    trigger_type: Mapped[str] = mapped_column(String(50))
    old_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    watchlist_entry: Mapped["WatchlistEntry"] = relationship(back_populates="alert_events")


class DigestFrequency(enum.Enum):
    daily = "daily"
    weekly = "weekly"


class NotificationSettings(Base):
    """Singleton config table — exactly one row, seeded on init_db."""
    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Email — up to 3 recipients
    email_address: Mapped[str | None] = mapped_column(String(254), nullable=True)
    email_address_2: Mapped[str | None] = mapped_column(String(254), nullable=True)
    email_address_3: Mapped[str | None] = mapped_column(String(254), nullable=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Notification schedule
    digest_frequency: Mapped[str] = mapped_column(
        SAEnum(DigestFrequency), default=DigestFrequency.weekly
    )
    notify_hour: Mapped[int] = mapped_column(Integer, default=8)
    notify_days: Mapped[str] = mapped_column(String(20), default="0,1,2,3,4,5,6")

    # Price polling schedule (separate from notification schedule)
    poll_frequency: Mapped[str] = mapped_column(String(20), default="weekly")   # "daily" | "weekly"
    poll_day: Mapped[int] = mapped_column(Integer, default=0)                   # 0=Mon … 6=Sun

    # SMTP credentials (stored locally — never leave this machine)
    smtp_user: Mapped[str | None] = mapped_column(String(254), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Push via ntfy.sh
    ntfy_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ntfy_topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ntfy_server: Mapped[str] = mapped_column(String(300), default="https://ntfy.sh")

    # Quiet hours
    quiet_hours_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quiet_hours_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Global alert sensitivity
    global_min_drop_pct: Mapped[float] = mapped_column(Float, default=5.0)
    notify_back_in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_special: Mapped[bool] = mapped_column(Boolean, default=True)

    last_digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Search preferences
    default_sort: Mapped[str] = mapped_column(String(10), default="")       # "" | "asc" | "desc"
    default_store: Mapped[str] = mapped_column(String(50), default="all")   # "all" | store slug


class ShoppingList(Base):
    __tablename__ = "shopping_lists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="My Shopping List")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    items: Mapped[list["ShoppingListItem"]] = relationship("ShoppingListItem", back_populates="list", cascade="all, delete-orphan")

class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(Integer, ForeignKey("shopping_lists.id"))
    name: Mapped[str] = mapped_column(String(300))           # search keyword / item name
    qty: Mapped[float] = mapped_column(Float, default=1.0)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    # Best match found per store (stored as JSON string for simplicity)
    matched_results: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    list: Mapped["ShoppingList"] = relationship("ShoppingList", back_populates="items")
