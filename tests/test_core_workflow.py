"""
test_core_workflow.py - Comprehensive Unit Tests for the FoodLink Core Workflow.

Verifies:
- Donate (Future expiry accepted, past/expired strictly rejected)
- View (List, search, filter, deterministic expiry transitions)
- Claim (Available -> Claimed, rejects claiming expired or already claimed items)
- Collect (Claimed -> Collected, rejects collecting un-claimed items)
- Deterministic behavior without any AI dependencies
"""

import os
import tempfile
import pytest
from datetime import datetime, timedelta

from models import (
    Database,
    STATUS_AVAILABLE,
    STATUS_CLAIMED,
    STATUS_COLLECTED,
    STATUS_EXPIRED,
)


@pytest.fixture
def test_db():
    """Creates a fresh temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(db_path=path)
    yield db
    if os.path.exists(path):
        os.remove(path)


def test_donate_valid_item(test_db):
    future_time = (datetime.now() + timedelta(hours=24)).isoformat()
    donation = test_db.create_donation(
        title="Artisan Sourdough Loaves",
        description="5 freshly baked whole wheat sourdough loaves from morning batch.",
        category="Bakery & Bread",
        quantity="5 loaves",
        expiry_date_str=future_time,
        storage_requirement="Ambient / Room Temperature",
        pickup_address="124 Baker Street, Central",
        donor_name="Corner Bakery",
        donor_contact="baker@example.com",
    )

    assert donation["id"] is not None
    assert donation["title"] == "Artisan Sourdough Loaves"
    assert donation["status"] == STATUS_AVAILABLE
    assert donation["claimed_by"] is None


def test_reject_expired_donation(test_db):
    """
    CRITICAL RULE: Never allow donating expired food.
    Backend must deterministically reject past expiry dates.
    """
    past_time = (datetime.now() - timedelta(hours=2)).isoformat()

    with pytest.raises(ValueError) as excinfo:
        test_db.create_donation(
            title="Expired Milk",
            description="Leftover milk carton",
            category="Dairy & Eggs",
            quantity="1 carton",
            expiry_date_str=past_time,
            storage_requirement="Refrigerated (< 4°C / 40°F)",
            pickup_address="Main St",
            donor_name="Local Cafe",
            donor_contact="555-0100",
        )
    assert "Expiration date must be in the future" in str(excinfo.value)


def test_view_and_filter_donations(test_db):
    future_time1 = (datetime.now() + timedelta(hours=12)).isoformat()
    future_time2 = (datetime.now() + timedelta(hours=48)).isoformat()

    test_db.create_donation(
        title="Apples & Oranges",
        description="Box of fresh gala apples and navel oranges",
        category="Produce (Fruits & Veggies)",
        quantity="10 kg",
        expiry_date_str=future_time1,
        storage_requirement="Ambient / Room Temperature",
        pickup_address="Green Grocer, North St",
        donor_name="Green Grocer",
        donor_contact="green@example.com",
    )

    test_db.create_donation(
        title="Vegetable Lasagna",
        description="Freshly cooked vegetarian lasagna portions in foil trays",
        category="Prepared Meals & Cooked Food",
        quantity="12 portions",
        expiry_date_str=future_time2,
        storage_requirement="Refrigerated (< 4°C / 40°F)",
        pickup_address="Community Center, West St",
        donor_name="Community Kitchen",
        donor_contact="kitchen@example.com",
    )

    # Test list all available
    all_donations = test_db.list_donations()
    assert len(all_donations) == 2

    # Test category filter
    produce_list = test_db.list_donations(category="Produce (Fruits & Veggies)")
    assert len(produce_list) == 1
    assert produce_list[0]["title"] == "Apples & Oranges"

    # Test keyword search
    search_list = test_db.list_donations(search="Lasagna")
    assert len(search_list) == 1
    assert search_list[0]["title"] == "Vegetable Lasagna"


def test_claim_workflow(test_db):
    """
    Tests transitioning from AVAILABLE -> CLAIMED.
    """
    future_time = (datetime.now() + timedelta(hours=24)).isoformat()
    donation = test_db.create_donation(
        title="Canned Soups",
        description="Case of vegetable soup cans",
        category="Pantry & Canned Goods",
        quantity="24 cans",
        expiry_date_str=future_time,
        storage_requirement="Ambient / Room Temperature",
        pickup_address="Warehouse 4",
        donor_name="Food Distributor",
        donor_contact="dist@example.com",
    )
    d_id = donation["id"]

    claimed = test_db.claim_donation(d_id, claimed_by="Hope Shelter NGO")
    assert claimed["status"] == STATUS_CLAIMED
    assert claimed["claimed_by"] == "Hope Shelter NGO"
    assert claimed["claimed_at"] is not None

    # Cannot claim an already claimed item
    with pytest.raises(ValueError) as exc:
        test_db.claim_donation(d_id, claimed_by="Another Charity")
    assert "already been claimed" in str(exc.value)


def test_collect_workflow(test_db):
    """
    Tests transitioning from CLAIMED -> COLLECTED.
    """
    future_time = (datetime.now() + timedelta(hours=24)).isoformat()
    donation = test_db.create_donation(
        title="Sandwich Platters",
        description="Assorted cheese and tomato sandwiches",
        category="Prepared Meals & Cooked Food",
        quantity="30 sandwiches",
        expiry_date_str=future_time,
        storage_requirement="Refrigerated (< 4°C / 40°F)",
        pickup_address="Conference Hall B",
        donor_name="Event Caterers",
        donor_contact="events@example.com",
    )
    d_id = donation["id"]

    # Cannot collect before claiming
    with pytest.raises(ValueError) as exc:
        test_db.collect_donation(d_id)
    assert "must be claimed before it can be collected" in str(exc.value)

    # Claim first
    test_db.claim_donation(d_id, claimed_by="City Mission Volunteer")

    # Now collect
    collected = test_db.collect_donation(d_id)
    assert collected["status"] == STATUS_COLLECTED
    assert collected["collected_at"] is not None

    # Cannot collect again
    with pytest.raises(ValueError) as exc:
        test_db.collect_donation(d_id)
    assert "already marked as collected" in str(exc.value)


def test_deterministic_expiration_transition(test_db):
    """
    Tests that items that pass their expiry date automatically transition to EXPIRED
    and cannot be claimed.
    """
    # Create item expiring 1 second from now
    almost_expired = (datetime.now() + timedelta(seconds=1)).isoformat()
    donation = test_db.create_donation(
        title="Perishable Salad",
        description="Fresh green salad",
        category="Produce (Fruits & Veggies)",
        quantity="3 bowls",
        expiry_date_str=almost_expired,
        storage_requirement="Refrigerated (< 4°C / 40°F)",
        pickup_address="Salad Bar",
        donor_name="Salad Bar",
        donor_contact="555-0199",
    )
    d_id = donation["id"]

    # Sleep slightly or manually simulate time passage by updating expiry date in db
    with test_db.connection_scope() as conn:
        past_time = (datetime.now() - timedelta(minutes=5)).isoformat()
        conn.execute("UPDATE donations SET expiry_date = ? WHERE id = ?", (past_time, d_id))

    # When querying get_donation or list_donations, status is updated to EXPIRED
    item = test_db.get_donation(d_id)
    assert item["status"] == STATUS_EXPIRED

    # Cannot claim expired donation
    with pytest.raises(ValueError) as exc:
        test_db.claim_donation(d_id, claimed_by="Shelter")
    assert "expired" in str(exc.value).lower()
