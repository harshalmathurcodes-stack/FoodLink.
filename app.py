"""
app.py - Main Flask Web Application for FoodLink.

Core Workflow: Donate -> View -> Claim -> Collect.
Deterministic validation controls expiry and availability.
AI Assistant (Gemma 4 models) is strictly optional and decoupled.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
)

from config import Config
from models import (
    Database,
    CATEGORIES,
    STORAGE_CONDITIONS,
    STATUS_AVAILABLE,
    STATUS_CLAIMED,
    STATUS_COLLECTED,
    STATUS_EXPIRED,
)
from ai_assistant import (
    AIAssistant,
    MODEL_31B,
    MODEL_26B,
    SUPPORTED_MODELS,
    SAFETY_DISCLAIMER,
)

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db = Database(db_path=app.config["DATABASE_PATH"])

# Initialize decoupled AI Assistant
ai_assistant = AIAssistant(
    api_key=app.config["GEMMA_API_KEY"],
    api_base=app.config["GEMMA_API_BASE"],
    default_model=app.config["GEMMA_DEFAULT_MODEL"],
    enabled=app.config["AI_ENABLED"],
    timeout=app.config["GEMMA_REQUEST_TIMEOUT"],
)


@app.context_processor
def inject_global_data():
    """Provides common data to all templates."""
    return {
        "categories": CATEGORIES,
        "storage_conditions": STORAGE_CONDITIONS,
        "ai_enabled": ai_assistant.enabled,
        "ai_online": ai_assistant.is_available(),
        "supported_models": [
            {"id": MODEL_31B, "name": "Google Gemma 4 (31B-IT)", "badge": "Detailed Reasoning"},
            {"id": MODEL_26B, "name": "Google Gemma 4 (26B-A4B-IT)", "badge": "Fast & Lightweight"},
        ],
        "default_model": ai_assistant.default_model,
        "now": datetime.now(),
    }


# =============================================================================
# Core Web Pages
# =============================================================================

@app.route("/")
def index():
    """Landing page showcasing FoodLink stats and recent available donations."""
    stats = db.get_stats()
    recent_donations = db.list_donations()[:6]
    return render_template("index.html", stats=stats, donations=recent_donations)


@app.route("/listings")
def listings():
    """
    View all available food donations.
    Supports filtering by category and keyword search.
    """
    category = request.args.get("category", "").strip() or None
    search = request.args.get("q", "").strip() or None

    donations_list = db.list_donations(category=category, search=search)
    return render_template(
        "listings.html",
        donations=donations_list,
        selected_category=category,
        search_query=search or "",
    )


@app.route("/donate", methods=["GET", "POST"])
def donate():
    """
    Food donation submission.
    DETERMINISTIC BACKEND VALIDATION: Expiry date must strictly be in the future.
    """
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        quantity = request.form.get("quantity", "").strip()
        expiry_date = request.form.get("expiry_date", "").strip()
        storage_requirement = request.form.get("storage_requirement", "").strip()
        pickup_address = request.form.get("pickup_address", "").strip()
        donor_name = request.form.get("donor_name", "").strip()
        donor_contact = request.form.get("donor_contact", "").strip()

        try:
            # INTEGRATE AI: Automatic inspection on every donation
            ai_review_dict = ai_assistant.check_donation(
                title=title,
                description=description,
                category=category,
                quantity=quantity,
                storage_requirement=storage_requirement,
            )
            import json
            ai_review_json = json.dumps(ai_review_dict)

            donation = db.create_donation(
                title=title,
                description=description,
                category=category,
                quantity=quantity,
                expiry_date_str=expiry_date,
                storage_requirement=storage_requirement,
                pickup_address=pickup_address,
                donor_name=donor_name,
                donor_contact=donor_contact,
                ai_review=ai_review_json,
            )
            status_msg = f"Food donation posted successfully! AI Quality Check: {ai_review_dict.get('status', 'REVIEWED')} (Score: {ai_review_dict.get('clarity_score', 80)}/100)."
            flash(status_msg, "success")
            return redirect(url_for("donation_detail", donation_id=donation["id"]))
        except ValueError as e:
            flash(str(e), "danger")
            return render_template(
                "donate.html",
                form_data=request.form,
            )

    # Suggest a default expiry date 24 hours from now for user convenience
    suggested_expiry = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    return render_template("donate.html", suggested_expiry=suggested_expiry, form_data={})


@app.route("/donation/<int:donation_id>")
def donation_detail(donation_id: int):
    """View details of a specific donation, with claim and collect capabilities."""
    item = db.get_donation(donation_id)
    if not item:
        abort(404, description="Donation listing not found.")

    return render_template("detail.html", item=item)


@app.route("/donation/<int:donation_id>/claim", methods=["POST"])
def claim_donation(donation_id: int):
    """
    Deterministic claim endpoint.
    Transitions AVAILABLE -> CLAIMED.
    """
    claimed_by = request.form.get("claimed_by", "").strip()
    try:
        db.claim_donation(donation_id, claimed_by=claimed_by)
        flash(f"Success! You have claimed this food donation. Please coordinate pickup with the donor.", "success")
    except ValueError as e:
        flash(f"Claim failed: {str(e)}", "danger")

    return redirect(url_for("donation_detail", donation_id=donation_id))


@app.route("/donation/<int:donation_id>/collect", methods=["POST"])
def collect_donation(donation_id: int):
    """
    Deterministic collect endpoint.
    Transitions CLAIMED -> COLLECTED.
    """
    try:
        db.collect_donation(donation_id)
        flash("Success! This donation has been marked as collected. Thank you for rescuing food!", "success")
    except ValueError as e:
        flash(f"Collection update failed: {str(e)}", "danger")

    return redirect(url_for("donation_detail", donation_id=donation_id))


@app.route("/ai-assistant")
def ai_assistant_page():
    """Dedicated interactive AI Assistant section on the website."""
    return render_template("ai_assistant.html")


# =============================================================================
# AI Assistant API Endpoints (AJAX Backend)
# Never exposes API keys; Handles errors and fallbacks gracefully
# =============================================================================

@app.route("/api/ai/suggest-category", methods=["POST"])
def api_suggest_category():
    """AI Feature 1: Food category suggestion."""
    data = request.get_json(silent=True) or {}
    description = data.get("description", "").strip()
    model = data.get("model")
    result = ai_assistant.suggest_category(description, requested_model=model)
    return jsonify(result)


@app.route("/api/ai/suggest-storage", methods=["POST"])
def api_suggest_storage():
    """AI Feature 2: Storage and handling suggestion."""
    data = request.get_json(silent=True) or {}
    food_item = data.get("food_item", "").strip()
    model = data.get("model")
    result = ai_assistant.suggest_storage_and_handling(food_item, requested_model=model)
    return jsonify(result)


@app.route("/api/ai/summarize", methods=["POST"])
def api_summarize():
    """AI Feature 3: Summarizing food donation descriptions."""
    data = request.get_json(silent=True) or {}
    description = data.get("description", "").strip()
    model = data.get("model")
    result = ai_assistant.summarize_donation(description, requested_model=model)
    return jsonify(result)


@app.route("/api/ai/improve-description", methods=["POST"])
def api_improve_description():
    """AI Feature 4: Helping donors write clear and informative descriptions."""
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    model = data.get("model")
    result = ai_assistant.improve_donation_description(text, requested_model=model)
    return jsonify(result)


@app.route("/api/ai/qa", methods=["POST"])
def api_qa():
    """AI Feature 5: Answering general questions about reducing food waste."""
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    model = data.get("model")
    result = ai_assistant.answer_food_waste_question(question, requested_model=model)
    return jsonify(result)


@app.route("/api/ai/custom-prompt", methods=["POST"])
def api_custom_prompt():
    """AI Feature 6: Custom prompt execution in AI Assistant space."""
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "").strip()
    system_prompt = data.get("system_prompt", "").strip() or None
    model = data.get("model")
    result = ai_assistant.execute_custom_prompt(prompt, system_prompt=system_prompt, requested_model=model)
    return jsonify(result)


@app.route("/api/ai/check-donation", methods=["POST"])
def api_check_donation():
    """AI Feature 7: Automatic AI inspection of food donation listings."""
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    category = data.get("category", "Other").strip()
    quantity = data.get("quantity", "").strip()
    storage = data.get("storage_requirement", "Ambient / Room Temperature").strip()
    model = data.get("model")

    result = ai_assistant.check_donation(
        title=title,
        description=description,
        category=category,
        quantity=quantity,
        storage_requirement=storage,
        requested_model=model,
    )
    return jsonify(result)


@app.route("/api/ai/status", methods=["GET"])
def api_status():
    """Returns AI status and configured models without exposing secrets."""
    return jsonify({
        "enabled": ai_assistant.enabled,
        "is_available": ai_assistant.is_available(),
        "default_model": ai_assistant.default_model,
        "supported_models": SUPPORTED_MODELS,
        "disclaimer": SAFETY_DISCLAIMER,
    })


if __name__ == "__main__":
    # Create sample demo data if database is empty
    stats = db.get_stats()
    if stats["total"] == 0:
        now = datetime.now()
        db.create_donation(
            title="Assorted Artisan Breads & Pastries",
            description="15 fresh baguettes, 8 butter croissants, and 5 sourdough loaves baked this morning. Boxed and ready for pickup.",
            category="Bakery & Bread",
            quantity="28 bakery items",
            expiry_date_str=(now + timedelta(hours=36)).isoformat(),
            storage_requirement="Ambient / Room Temperature",
            pickup_address="Sunrise Bakery, 104 Market Street",
            donor_name="Sunrise Artisan Bakery",
            donor_contact="baker@sunrise.example.com",
        )
        db.create_donation(
            title="Fresh Organic Mixed Vegetables",
            description="Surplus organic produce box: zucchini, bell peppers, carrots, and sweet potatoes. Harvested yesterday.",
            category="Produce (Fruits & Veggies)",
            quantity="15 kg crate",
            expiry_date_str=(now + timedelta(days=3)).isoformat(),
            storage_requirement="Ambient / Room Temperature",
            pickup_address="Green Valley Farm Stand, 42 Elm Road",
            donor_name="Green Valley Organics",
            donor_contact="contact@greenvalley.example.com",
        )
        c_item = db.create_donation(
            title="Catered Mediterranean Lunch Boxes",
            description="Individually sealed boxed meals containing falafel, hummus, pita, and tabbouleh salad. Prepared today at 11 AM.",
            category="Prepared Meals & Cooked Food",
            quantity="20 boxed lunches",
            expiry_date_str=(now + timedelta(hours=20)).isoformat(),
            storage_requirement="Refrigerated (< 4°C / 40°F)",
            pickup_address="Summit Conference Center, Loading Bay 2",
            donor_name="Global Summit Catering",
            donor_contact="events@summitcatering.example.com",
        )
        db.claim_donation(c_item["id"], claimed_by="Hope Community Shelter")

    # Run Flask server locally
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
