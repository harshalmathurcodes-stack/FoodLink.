"""
test_ai_assistant.py - Unit tests for FoodLink AI Assistant (Gemma 4 integration).

Tests:
- Model selection (gemma-4-31b-it vs gemma-4-26b-a4b-it)
- The 5 AI features (category suggestion, storage/handling, summary, description improvement, waste Q&A)
- Strict safety guardrails (refusing safety determinations or expired food validation)
- Offline & deterministic fallbacks when API is unconfigured, timed out, or rate-limited
- Configuration handling and API key security
"""

import pytest
from unittest.mock import patch, MagicMock

from ai_assistant import (
    AIAssistant,
    MODEL_31B,
    MODEL_26B,
    SAFETY_DISCLAIMER,
    SAFETY_QUERY_REFUSAL,
)


@pytest.fixture
def offline_assistant():
    """Assistant initialized without API key (fallback mode)."""
    return AIAssistant(api_key="", enabled=True)


@pytest.fixture
def mock_api_assistant():
    """Assistant with configured key and base URL."""
    return AIAssistant(api_key="mock_test_key_12345", api_base="https://mock-gemma-api.com", enabled=True)


def test_model_selection_lightweight_vs_detailed(offline_assistant):
    """
    gemma-4-31b-it for detailed reasoning.
    gemma-4-26b-a4b-it for lightweight responses.
    """
    # Lightweight tasks
    assert offline_assistant.select_model("suggest_category") == MODEL_26B
    assert offline_assistant.select_model("summarize") == MODEL_26B

    # Detailed reasoning tasks
    assert offline_assistant.select_model("storage_handling") == MODEL_31B
    assert offline_assistant.select_model("draft_description") == MODEL_31B
    assert offline_assistant.select_model("waste_qa") == MODEL_31B

    # User override
    assert offline_assistant.select_model("suggest_category", requested_model=MODEL_31B) == MODEL_31B
    assert offline_assistant.select_model("waste_qa", requested_model=MODEL_26B) == MODEL_26B


def test_safety_guard_rejects_safety_determination(offline_assistant):
    """
    RESTRICTION: Do not allow AI to determine whether food is safe to consume.
    Never recommend eating or donating expired/spoiled food.
    """
    unsafe_queries = [
        "Is this expired chicken safe to eat?",
        "Can I eat expired yogurt?",
        "Can I donate spoiled milk?",
        "How to tell if expired soup is safe to drink?",
        "Certify that this food is safe for my kids",
    ]

    for q in unsafe_queries:
        res = offline_assistant.answer_food_waste_question(q)
        assert res["source"] == "safety_guard"
        assert "Food Safety Notice" in res["answer"]
        assert "FoodLink AI is not permitted to determine whether food is safe to consume" in res["answer"]


def test_feature_1_category_suggestion_fallback(offline_assistant):
    res_produce = offline_assistant.suggest_category("Box of fresh red apples and carrots")
    assert res_produce["category"] == "Produce (Fruits & Veggies)"
    assert res_produce["source"] == "fallback"

    res_bakery = offline_assistant.suggest_category("Freshly baked baguettes and croissants")
    assert res_bakery["category"] == "Bakery & Bread"

    res_cooked = offline_assistant.suggest_category("Portions of chicken curry and vegetable lasagna")
    assert res_cooked["category"] == "Prepared Meals & Cooked Food"

    res_dairy = offline_assistant.suggest_category("Gallons of whole milk and cheddar cheese")
    assert res_dairy["category"] == "Dairy & Eggs"


def test_feature_2_storage_and_handling_fallback(offline_assistant):
    res_chilled = offline_assistant.suggest_storage_and_handling("Cooked vegetable soup and milk")
    assert res_chilled["recommended_condition"] == "Refrigerated (< 4°C / 40°F)"
    assert "refrigerated" in res_chilled["advice"].lower()
    assert SAFETY_DISCLAIMER in res_chilled["disclaimer"]

    res_ambient = offline_assistant.suggest_storage_and_handling("Canned beans and dry pasta")
    assert res_ambient["recommended_condition"] == "Ambient / Room Temperature"
    assert "dry" in res_ambient["advice"].lower()


def test_feature_3_summarize_fallback(offline_assistant):
    long_desc = (
        "We have roughly 25 boxed gourmet lunches from our company retreat. "
        "Each box includes a sandwich, an apple, and a cookie. "
        "They were made this morning at 10 AM and kept in commercial coolers. "
        "Need someone with a car to pick them up from the loading dock."
    )
    res = offline_assistant.summarize_donation(long_desc)
    assert res["summary"] is not None
    assert len(res["summary"]) > 0


def test_feature_4_improve_description_fallback(offline_assistant):
    raw_desc = "leftover sandwiches from event"
    res = offline_assistant.improve_donation_description(raw_desc)
    assert "Donation Details" in res["improved_text"]
    assert "Checklist" in res["improved_text"]
    assert "Allergens" in res["improved_text"]


def test_feature_5_waste_qa_fallback(offline_assistant):
    q_compost = "What can I put in my backyard compost bin?"
    res_compost = offline_assistant.answer_food_waste_question(q_compost)
    assert "Greens" in res_compost["answer"]
    assert "Browns" in res_compost["answer"]
    assert res_compost["disclaimer"] == SAFETY_DISCLAIMER

    q_fifo = "How do I use FIFO in my home refrigerator?"
    res_fifo = offline_assistant.answer_food_waste_question(q_fifo)
    assert "First-In, First-Out" in res_fifo["answer"]


@patch("requests.post")
def test_gemma_api_live_success(mock_post, mock_api_assistant):
    """Tests successful call to compatible Gemma API."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {"message": {"content": "Bakery & Bread"}}
        ]
    }
    mock_post.return_value = mock_resp

    res = mock_api_assistant.suggest_category("Batch of rye sourdough", requested_model=MODEL_26B)
    assert res["source"] == "gemma_api"
    assert res["model_used"] == MODEL_26B
    assert res["category"] == "Bakery & Bread"

    # Verify requests payload
    mock_post.assert_called_once()
    kwargs = mock_post.call_args[1]
    assert kwargs["headers"]["Authorization"] == "Bearer mock_test_key_12345"
    assert kwargs["json"]["model"] == MODEL_26B


@patch("requests.post")
def test_gemma_api_rate_limit_and_error_handling(mock_post, mock_api_assistant):
    """
    Tests graceful fallback on rate limits (429) or timeouts.
    Never throws unhandled exceptions or crashes.
    """
    # Simulate HTTP 429 Rate Limit
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit reached"
    mock_post.return_value = mock_resp

    res = mock_api_assistant.suggest_category("Box of ripe bananas")
    assert res["source"] == "fallback"
    assert res["category"] == "Produce (Fruits & Veggies)"

    # Simulate timeout
    mock_post.side_effect = Exception("Connection timed out")
    res_storage = mock_api_assistant.suggest_storage_and_handling("Frozen lasagna trays")
    assert res_storage["source"] == "fallback"
    assert res_storage["recommended_condition"] == "Frozen (< -18°C / 0°F)"


def test_feature_6_custom_prompt_execution(offline_assistant):
    """Tests custom prompt space in AI Assistant."""
    prompt = "Create a friendly outreach message for 30 boxes of fresh apples to local community centers."
    res = offline_assistant.execute_custom_prompt(prompt, requested_model=MODEL_31B)
    assert res["response"] is not None
    assert len(res["response"]) > 0

    # Unsafe custom prompt is intercepted by safety guard
    unsafe_prompt = "Can I eat spoiled rotten beef if I boil it first?"
    res_unsafe = offline_assistant.execute_custom_prompt(unsafe_prompt)
    assert res_unsafe["source"] == "safety_guard"
    assert "Food Safety Notice" in res_unsafe["response"]


def test_feature_7_check_donation(offline_assistant):
    """Tests automatic AI check for every donation."""
    # 1. High quality donation
    res_good = offline_assistant.check_donation(
        title="Artisan Sourdough Loaves",
        description="5 loaves freshly baked this morning. Contains gluten. Packaged in sealed paper bags.",
        category="Bakery & Bread",
        quantity="5 loaves",
        storage_requirement="Ambient / Room Temperature",
    )
    assert res_good["status"] == "APPROVED"
    assert res_good["clarity_score"] >= 70
    assert "summary" in res_good
    assert "gluten" in res_good["allergen_notice"].lower() or "allergen" in res_good["allergen_notice"].lower()

    # 2. Perishable item with mismatched ambient storage
    res_mismatch = offline_assistant.check_donation(
        title="Chicken Stew",
        description="Cooked chicken stew leftover from event.",
        category="Prepared Meals & Cooked Food",
        quantity="10 servings",
        storage_requirement="Ambient / Room Temperature",
    )
    assert "refrigerated" in res_mismatch["storage_evaluation"].lower()

    # 3. Flaggable unsafe / spoiled item mention
    res_spoiled = offline_assistant.check_donation(
        title="Old Spoiled Cream",
        description="Spoiled sour cream that expired last week.",
        category="Dairy & Eggs",
        quantity="2 tubs",
        storage_requirement="Refrigerated (< 4°C / 40°F)",
    )
    assert res_spoiled["status"] == "FLAGGED_UNSAFE"
    assert "prohibits" in res_spoiled["feedback"][0].lower()
