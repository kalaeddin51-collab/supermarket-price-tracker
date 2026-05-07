"""
Seed script: create test persona "Sarah" — a Neutral Bay housewife with 10 profile items.

Usage:
    python scripts/seed_sarah.py

Safe to re-run: skips creation if sarah@example.com already exists.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import bcrypt
from app.database import SessionLocal, init_db
from app import models

EMAIL = "sarah@example.com"
PASSWORD = "password123"
NAME = "Sarah"
SUBURB = "neutral bay"
# Stores for Neutral Bay: woolworths, coles, aldi, iga_milsons_point, harris_farm_cammeray
STORES = "woolworths,coles,aldi,iga_milsons_point,harris_farm_cammeray"

PROFILE_ITEMS = [
    {"item_name": "full cream milk", "brand_preference": "Dairy Farmers", "notes": "2L carton"},
    {"item_name": "free range eggs", "brand_preference": None, "notes": "12 pack"},
    {"item_name": "chicken breast", "brand_preference": None, "notes": "free range if possible"},
    {"item_name": "greek yoghurt", "brand_preference": "Chobani", "notes": "plain, 500g"},
    {"item_name": "sourdough bread", "brand_preference": None, "notes": "sliced loaf"},
    {"item_name": "butter", "brand_preference": "Mainland", "notes": "salted, 500g block"},
    {"item_name": "cheddar cheese", "brand_preference": "Mainland", "notes": "tasty, 500g block"},
    {"item_name": "olive oil", "brand_preference": None, "notes": "extra virgin, 750ml"},
    {"item_name": "rolled oats", "brand_preference": None, "notes": "1kg bag"},
    {"item_name": "baby spinach", "brand_preference": None, "notes": "120g bag"},
]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def main():
    init_db()
    db = SessionLocal()

    try:
        existing = db.query(models.User).filter(models.User.email == EMAIL).first()
        if existing:
            print(f"User {EMAIL} already exists (id={existing.id}). Skipping creation.")
            user = existing
        else:
            user = models.User(
                name=NAME,
                email=EMAIL,
                password_hash=hash_password(PASSWORD),
            )
            db.add(user)
            db.flush()  # get user.id before inserting related rows

            pref = models.UserPreference(
                user_id=user.id,
                suburb=SUBURB,
                stores=STORES,
            )
            db.add(pref)
            db.commit()
            print(f"Created user: {NAME} <{EMAIL}> (id={user.id})")
            print(f"  suburb={SUBURB}")
            print(f"  stores={STORES}")

        # Remove any existing profile items so re-run is idempotent
        existing_items = (
            db.query(models.ConsumptionItem)
            .filter(models.ConsumptionItem.user_id == user.id)
            .all()
        )
        if existing_items:
            for item in existing_items:
                db.delete(item)
            db.commit()
            print(f"  Cleared {len(existing_items)} existing profile items.")

        for item_data in PROFILE_ITEMS:
            db.add(models.ConsumptionItem(
                user_id=user.id,
                item_name=item_data["item_name"],
                brand_preference=item_data["brand_preference"],
                notes=item_data["notes"],
            ))

        db.commit()
        print(f"  Seeded {len(PROFILE_ITEMS)} consumption profile items:")
        for item in PROFILE_ITEMS:
            brand = f" [{item['brand_preference']}]" if item["brand_preference"] else ""
            notes = f" — {item['notes']}" if item["notes"] else ""
            print(f"    - {item['item_name']}{brand}{notes}")

        print(f"\nDone. Log in as {EMAIL} / {PASSWORD}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
