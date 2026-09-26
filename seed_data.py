"""
Seeds the database with a starter, fixed-but-extensible list of medicinal
use categories. Run once after creating the DB:

  

Edit STARTER_CATEGORIES below to match your fieldwork/grant proposal list.
New categories can also be added later straight through the DB (or a small
admin route) without touching this file again.
"""

import sqlite3

DB_PATH = "database.db"

STARTER_CATEGORIES = [
    "Wound healing",
    "Fever",
    "Malaria",
    "Digestive issues",
    "Skin infection",
    "Pain relief",
    "Cough / Respiratory",
    "Diabetes management",
    "Hypertension",
    "Antimicrobial / Antiseptic",
]


def seed():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for name in STARTER_CATEGORIES:
        cur.execute(
            "INSERT OR IGNORE INTO use_categories (name) VALUES (?)", (name,)
        )
    conn.commit()
    print(f"Seeded {len(STARTER_CATEGORIES)} use categories (duplicates skipped).")
    conn.close()


if __name__ == "__main__":
    seed()
