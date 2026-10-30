"""
test_flask_app.py - Integration and Web Route Tests for FoodLink Flask Application.

Verifies:
- All core web routes (Home, Listings, Donate, Detail, Claim, Collect)
- Deterministic expiry date handling in Flask form submissions
- AI API AJAX endpoints (/api/ai/*)
- Safety guardrails and disclaimer presence
- Decoupled operation without requiring live external API
"""

import os
import tempfile
import pytest
from datetime import datetime, timedelta

from app import app, db
from models import Database, STATUS_AVAILABLE, STATUS_CLAIMED, STATUS_COLLECTED


@pytest.fixture
def client():
    """Configures test client with an isolated temporary SQLite database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    app.config["TESTING"] = True
    app.config["DATABASE_PATH"] = path
    app.config["WTF_CSRF_ENABLED"] = False

    # Point db instance to the temporary test database
    db.db_path = path
    db.init_db()

    with app.test_client() as test_client:
        yield test_client

    if os.path.exists(path):
        os.remove(path)


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Rescue Good Food" in response.data
    assert b"Available Items" in response.data


def test_listings_empty_and_populated(client):
    # Initially empty
    resp = client.get("/listings")
    assert resp.status_code == 200
    assert b"No Food Donations Matched Your Filters" in resp.data

    # Add an item
    future_time = (datetime.now() + timedelta(days=2)).isoformat()
    db.create_donation(
        title="Apples & Oranges",
        description="Fresh citrus fruits and apples",
        category="Produce (Fruits & Veggies)",
        quantity="10 kg",
        expiry_date_str=future_time,
        storage_requirement="Ambient / Room Temperature",
        pickup_address="Market St",
        donor_name="Fruit Stand",
        donor_contact="555-0101",
    )

    resp_after = client.get("/listings")
    assert resp_after.status_code == 200
    assert b"Apples &amp; Oranges" in resp_after.data or b"Apples & Oranges" in resp_after.data


def test_donate_valid_food_flow(client):
    future_time = (datetime.now() + timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M")
    payload = {
        "title": "Fresh Brioche Buns",
        "description": "24 fresh brioche hamburger buns, packed in sealed plastic bags.",
        "category": "Bakery & Bread",
        "quantity": "24 buns",
        "expiry_date": future_time,
        "storage_requirement": "Ambient / Room Temperature",
        "pickup_address": "Bakery Lane #5",
        "donor_name": "Baker Joe",
        "donor_contact": "joe@example.com",
    }

    resp = client.post("/donate", data=payload, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Food donation posted successfully!" in resp.data
    assert b"AI Quality Check" in resp.data
    assert b"Fresh Brioche Buns" in resp.data


def test_donate_expired_food_strictly_rejected(client):
    """
    CRITICAL RESTRICTION: Expiry dates must be in the future.
    Expired food donation attempts must be rejected with clear error.
    """
    past_time = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M")
    payload = {
        "title": "Old Salad Greens",
        "description": "Wilted greens from earlier this week",
        "category": "Produce (Fruits & Veggies)",
        "quantity": "2 bowls",
        "expiry_date": past_time,
        "storage_requirement": "Refrigerated (< 4°C / 40°F)",
        "pickup_address": "Salad Spot",
        "donor_name": "Salad Spot",
        "donor_contact": "spot@example.com",
    }

    resp = client.post("/donate", data=payload, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Expiration date must be in the future" in resp.data


def test_claim_and_collect_workflow_via_web(client):
    future_time = (datetime.now() + timedelta(days=1)).isoformat()
    donation = db.create_donation(
        title="Prepared Vegetable Stew",
        description="Freshly cooked stew in large container",
        category="Prepared Meals & Cooked Food",
        quantity="8 portions",
        expiry_date_str=future_time,
        storage_requirement="Refrigerated (< 4°C / 40°F)",
        pickup_address="Main Kitchen",
        donor_name="Chef Maria",
        donor_contact="maria@example.com",
    )
    d_id = donation["id"]

    # Claim the donation
    claim_resp = client.post(
        f"/donation/{d_id}/claim",
        data={"claimed_by": "Community Food Bank"},
        follow_redirects=True,
    )
    assert claim_resp.status_code == 200
    assert b"You have claimed this food donation" in claim_resp.data
    assert b"CLAIMED" in claim_resp.data

    # Collect the donation
    collect_resp = client.post(
        f"/donation/{d_id}/collect",
        follow_redirects=True,
    )
    assert collect_resp.status_code == 200
    assert b"marked as collected" in collect_resp.data
    assert b"COLLECTED" in collect_resp.data


def test_ai_assistant_page_renders(client):
    resp = client.get("/ai-assistant")
    assert resp.status_code == 200
    assert b"FoodLink AI Assistant" in resp.data
    assert b"gemma-4-31b-it" in resp.data
    assert b"gemma-4-26b-a4b-it" in resp.data
    assert b"Important AI Safety Notice" in resp.data


def test_ai_api_endpoints(client):
    # 1. Category suggestion
    resp1 = client.post(
        "/api/ai/suggest-category",
        json={"description": "5 loaves of freshly baked sourdough bread", "model": "gemma-4-26b-a4b-it"},
    )
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert data1["category"] == "Bakery & Bread"

    # 2. Storage advice
    resp2 = client.post(
        "/api/ai/suggest-storage",
        json={"food_item": "Chicken Caesar Salad", "model": "gemma-4-31b-it"},
    )
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2["recommended_condition"] == "Refrigerated (< 4°C / 40°F)"
    assert "Disclaimer" in data2["disclaimer"]

    # 3. Summarize
    resp3 = client.post(
        "/api/ai/summarize",
        json={"description": "We have 10 boxes of fresh organic strawberries picked this morning. Refrigerated and ripe."},
    )
    assert resp3.status_code == 200
    data3 = resp3.get_json()
    assert len(data3["summary"]) > 0

    # 4. Improve description
    resp4 = client.post(
        "/api/ai/improve-description",
        json={"text": "leftover buffet pastries"},
    )
    assert resp4.status_code == 200
    data4 = resp4.get_json()
    assert "improved_text" in data4

    # 5. Food waste Q&A
    resp5 = client.post(
        "/api/ai/qa",
        json={"question": "What is the FIFO rule for pantry goods?"},
    )
    assert resp5.status_code == 200
    data5 = resp5.get_json()
    assert "First-In, First-Out" in data5["answer"]

    # 6. Safety check intercept in Q&A
    resp6 = client.post(
        "/api/ai/qa",
        json={"question": "Can I eat expired moldy chicken?"},
    )
    assert resp6.status_code == 200
    data6 = resp6.get_json()
    assert data6["source"] == "safety_guard"
    assert "Food Safety Notice" in data6["answer"]

    # 7. Custom Prompt Execution endpoint
    resp_prompt = client.post(
        "/api/ai/custom-prompt",
        json={"prompt": "How do I store fresh strawberries to maximize shelf life?", "model": "gemma-4-31b-it"},
    )
    assert resp_prompt.status_code == 200
    data_prompt = resp_prompt.get_json()
    assert "response" in data_prompt

    # 8. AI Donation Inspection endpoint
    resp_check = client.post(
        "/api/ai/check-donation",
        json={
            "title": "Fresh Brioche Rolls",
            "description": "12 rolls in bakery paper bag. Contains gluten.",
            "category": "Bakery & Bread",
            "quantity": "12 rolls",
            "storage_requirement": "Ambient / Room Temperature",
        },
    )
    assert resp_check.status_code == 200
    data_check = resp_check.get_json()
    assert data_check["status"] == "APPROVED"
    assert "clarity_score" in data_check

    # 9. Status endpoint (no secrets leaked)
    resp7 = client.get("/api/ai/status")
    assert resp7.status_code == 200
    data7 = resp7.get_json()
    assert "enabled" in data7
    assert "default_model" in data7
    assert "api_key" not in data7
    assert "GEMMA_API_KEY" not in data7
