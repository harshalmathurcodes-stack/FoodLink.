"""
models.py - Deterministic Database Models & Workflow for FoodLink.

Enforces deterministic business rules for:
- Donate: Strict validation ensuring expiry date is in the future.
- View: Automatic expiration check based on system clock; search & category filter.
- Claim: Strict transition from AVAILABLE -> CLAIMED; rejected if expired or unavailable.
- Collect: Strict transition from CLAIMED -> COLLECTED.

AI systems have NO authority or ability to alter food availability or bypass expiry dates.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

STATUS_AVAILABLE = "AVAILABLE"
STATUS_CLAIMED = "CLAIMED"
STATUS_COLLECTED = "COLLECTED"
STATUS_EXPIRED = "EXPIRED"

VALID_STATUSES = {
    STATUS_AVAILABLE,
    STATUS_CLAIMED,
    STATUS_COLLECTED,
    STATUS_EXPIRED,
}

CATEGORIES = [
    "Produce (Fruits & Veggies)",
    "Bakery & Bread",
    "Prepared Meals & Cooked Food",
    "Dairy & Eggs",
    "Pantry & Canned Goods",
    "Beverages",
    "Meat & Poultry",
    "Other",
]

STORAGE_CONDITIONS = [
    "Ambient / Room Temperature",
    "Refrigerated (< 4°C / 40°F)",
    "Frozen (< -18°C / 0°F)",
]


class Database:
    """Manages SQLite database connections and deterministic operations."""

    def __init__(self, db_path: str = "foodlink.db"):
        self.db_path = db_path
        self.init_db()

    from contextlib import contextmanager

    @contextmanager
    def connection_scope(self):
        """Context manager that commits on success, rollbacks on error, and always closes."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initializes tables for donations."""
        with self.connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS donations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    expiry_date TEXT NOT NULL,
                    storage_requirement TEXT NOT NULL,
                    pickup_address TEXT NOT NULL,
                    donor_name TEXT NOT NULL,
                    donor_contact TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'AVAILABLE',
                    claimed_by TEXT,
                    claimed_at TEXT,
                    collected_at TEXT,
                    ai_review TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Ensure ai_review column exists if table was previously created
            cursor.execute("PRAGMA table_info(donations)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "ai_review" not in columns:
                cursor.execute("ALTER TABLE donations ADD COLUMN ai_review TEXT")
            conn.commit()

    @staticmethod
    def now_iso() -> str:
        """Returns current local/system time in ISO 8601 format."""
        return datetime.now().isoformat()

    @staticmethod
    def parse_datetime(dt_str: str) -> datetime:
        """Safely parses ISO datetime string into a naive or aware datetime."""
        if not dt_str:
            raise ValueError("Empty datetime string provided")
        # Support both '2026-10-30T14:30' and '2026-10-30 14:30:00'
        dt_str = dt_str.replace("Z", "").strip()
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return datetime.strptime(dt_str, fmt)
                except ValueError:
                    continue
            raise ValueError(f"Unable to parse datetime: {dt_str}")

    def update_expired_donations(self) -> int:
        """
        DETERMINISTIC BACKEND RULE:
        Any donation currently marked 'AVAILABLE' whose expiry_date has passed
        is automatically and deterministically converted to 'EXPIRED'.
        Returns count of items transitioned.
        """
        now = datetime.now()
        with self.connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, expiry_date FROM donations WHERE status = ?",
                (STATUS_AVAILABLE,),
            )
            rows = cursor.fetchall()
            expired_ids = []
            for row in rows:
                try:
                    exp_dt = self.parse_datetime(row["expiry_date"])
                    if exp_dt <= now:
                        expired_ids.append(row["id"])
                except Exception:
                    # If date is invalid or corrupt, treat as expired for safety
                    expired_ids.append(row["id"])

            if expired_ids:
                cursor.executemany(
                    "UPDATE donations SET status = ? WHERE id = ?",
                    [(STATUS_EXPIRED, d_id) for d_id in expired_ids],
                )
                conn.commit()
            return len(expired_ids)

    def create_donation(
        self,
        title: str,
        description: str,
        category: str,
        quantity: str,
        expiry_date_str: str,
        storage_requirement: str,
        pickup_address: str,
        donor_name: str,
        donor_contact: str,
        ai_review: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a new donation.
        DETERMINISTIC BACKEND RULE:
        - Expiration date must be strictly in the future.
        - Expired donations are strictly rejected.
        - AI cannot override this validation.
        """
        if not title or not title.strip():
            raise ValueError("Title is required.")
        if not description or not description.strip():
            raise ValueError("Description is required.")
        if not quantity or not quantity.strip():
            raise ValueError("Quantity is required.")
        if not pickup_address or not pickup_address.strip():
            raise ValueError("Pickup address is required.")
        if not donor_name or not donor_name.strip():
            raise ValueError("Donor name is required.")
        if not donor_contact or not donor_contact.strip():
            raise ValueError("Donor contact is required.")

        # Validate category
        if category not in CATEGORIES:
            category = "Other"

        # Validate storage condition
        if storage_requirement not in STORAGE_CONDITIONS:
            storage_requirement = STORAGE_CONDITIONS[0]

        # DETERMINISTIC EXPIRY VALIDATION
        exp_dt = self.parse_datetime(expiry_date_str)
        now = datetime.now()
        if exp_dt <= now:
            raise ValueError(
                "Expiration date must be in the future. "
                "FoodLink strictly rejects expired food donations for safety."
            )

        created_at = self.now_iso()
        formatted_expiry = exp_dt.isoformat()

        with self.connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO donations (
                    title, description, category, quantity, expiry_date,
                    storage_requirement, pickup_address, donor_name, donor_contact,
                    status, ai_review, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    description.strip(),
                    category,
                    quantity.strip(),
                    formatted_expiry,
                    storage_requirement,
                    pickup_address.strip(),
                    donor_name.strip(),
                    donor_contact.strip(),
                    STATUS_AVAILABLE,
                    ai_review,
                    created_at,
                ),
            )
            donation_id = cursor.lastrowid
            conn.commit()

        return self.get_donation(donation_id)  # type: ignore

    def get_donation(self, donation_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a donation by ID. Deterministically evaluates expiry if still AVAILABLE.
        Parses ai_review JSON if present.
        """
        self.update_expired_donations()

        with self.connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM donations WHERE id = ?", (donation_id,))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("ai_review"):
                import json
                try:
                    data["ai_review_data"] = json.loads(data["ai_review"])
                except Exception:
                    data["ai_review_data"] = None
            else:
                data["ai_review_data"] = None
            return data

    def update_donation_ai_review(self, donation_id: int, ai_review: str) -> None:
        """Updates AI inspection report for a donation."""
        with self.connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE donations SET ai_review = ? WHERE id = ?",
                (ai_review, donation_id),
            )
            conn.commit()

    def list_donations(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Lists donations with deterministic expiry evaluation, filtering and search.
        """
        self.update_expired_donations()

        query = "SELECT * FROM donations WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        elif not include_expired:
            # Default view only shows active available donations
            query += " AND status != ?"
            params.append(STATUS_EXPIRED)

        if category and category.strip():
            query += " AND category = ?"
            params.append(category.strip())

        if search and search.strip():
            query += " AND (title LIKE ? OR description LIKE ? OR pickup_address LIKE ?)"
            term = f"%{search.strip()}%"
            params.extend([term, term, term])

        query += " ORDER BY id DESC"

        with self.connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def claim_donation(self, donation_id: int, claimed_by: str) -> Dict[str, Any]:
        """
        DETERMINISTIC BACKEND RULE:
        Only donations with status == 'AVAILABLE' and expiry_date > now can be claimed.
        Transitions state to 'CLAIMED'.
        """
        if not claimed_by or not claimed_by.strip():
            raise ValueError("Claimant name or organization is required.")

        # First, ensure expired items are up to date
        self.update_expired_donations()

        with self.connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM donations WHERE id = ?", (donation_id,))
            row = cursor.fetchone()

            if not row:
                raise ValueError(f"Donation with ID {donation_id} not found.")

            current_status = row["status"]
            if current_status == STATUS_EXPIRED:
                raise ValueError("This donation has expired and cannot be claimed.")
            if current_status == STATUS_CLAIMED:
                raise ValueError("This donation has already been claimed by another recipient.")
            if current_status == STATUS_COLLECTED:
                raise ValueError("This donation has already been collected.")
            if current_status != STATUS_AVAILABLE:
                raise ValueError(f"Cannot claim donation in status: {current_status}")

            claimed_at = self.now_iso()
            cursor.execute(
                """
                UPDATE donations
                SET status = ?, claimed_by = ?, claimed_at = ?
                WHERE id = ? AND status = ?
                """,
                (STATUS_CLAIMED, claimed_by.strip(), claimed_at, donation_id, STATUS_AVAILABLE),
            )
            if cursor.rowcount == 0:
                raise ValueError("Concurrent update conflict: donation is no longer available.")
            conn.commit()

        return self.get_donation(donation_id)  # type: ignore

    def collect_donation(self, donation_id: int) -> Dict[str, Any]:
        """
        DETERMINISTIC BACKEND RULE:
        Only donations with status == 'CLAIMED' can be marked as 'COLLECTED'.
        Transitions state to 'COLLECTED'.
        """
        with self.connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM donations WHERE id = ?", (donation_id,))
            row = cursor.fetchone()

            if not row:
                raise ValueError(f"Donation with ID {donation_id} not found.")

            current_status = row["status"]
            if current_status == STATUS_COLLECTED:
                raise ValueError("Donation is already marked as collected.")
            if current_status != STATUS_CLAIMED:
                raise ValueError(
                    f"Donation must be claimed before it can be collected. Current status: {current_status}"
                )

            collected_at = self.now_iso()
            cursor.execute(
                """
                UPDATE donations
                SET status = ?, collected_at = ?
                WHERE id = ? AND status = ?
                """,
                (STATUS_COLLECTED, collected_at, donation_id, STATUS_CLAIMED),
            )
            if cursor.rowcount == 0:
                raise ValueError("Failed to collect donation: status changed concurrently.")
            conn.commit()

        return self.get_donation(donation_id)  # type: ignore

    def get_stats(self) -> Dict[str, int]:
        """Returns deterministic counts of donations across all statuses."""
        self.update_expired_donations()
        with self.connection_scope() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) as cnt FROM donations GROUP BY status")
            counts = {row["status"]: row["cnt"] for row in cursor.fetchall()}
            return {
                "available": counts.get(STATUS_AVAILABLE, 0),
                "claimed": counts.get(STATUS_CLAIMED, 0),
                "collected": counts.get(STATUS_COLLECTED, 0),
                "expired": counts.get(STATUS_EXPIRED, 0),
                "total": sum(counts.values()),
            }
