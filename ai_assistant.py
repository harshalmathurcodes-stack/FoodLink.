"""
ai_assistant.py - Google Gemma-4 AI Integration for FoodLink.

Integrates:
1. gemma-4-31b-it (for detailed reasoning and comprehensive responses)
2. gemma-4-26b-a4b-it (for faster, lightweight responses)

Features:
1. Food category suggestions based on food descriptions.
2. Suggestions for appropriate food storage and handling.
3. Summarizing food donation descriptions.
4. Helping donors write clear and informative donation descriptions.
5. Answering general questions about reducing food waste.

CRITICAL SAFETY RESTRICTIONS:
- Do not allow AI to determine whether food is safe to consume.
- Do not let AI override expiry-date validation.
- Never recommend donating expired food.
- Food availability and expiry must always be controlled by deterministic Python backend logic.
- Do not invent food safety certifications or guarantees.
- Handles API errors, rate limits, timeouts, and missing credentials with friendly fallback.
- API credentials are read from environment variables; NEVER exposed to frontend or repository.
"""

from __future__ import annotations

import os
import re
import json
import logging
from typing import Dict, Any, Optional, Tuple

import requests
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

logger = logging.getLogger("foodlink.ai")

# Model definitions
MODEL_31B = "gemma-4-31b-it"
MODEL_26B = "gemma-4-26b-a4b-it"

SUPPORTED_MODELS = [MODEL_26B, MODEL_31B]

SAFETY_DISCLAIMER = (
    "Disclaimer: FoodLink AI provides general culinary and storage suggestions for informational "
    "purposes only. AI cannot determine whether food is safe to consume, nor provide food safety "
    "certifications. Always inspect food and follow local health department regulations. "
    "When in doubt, throw it out."
)

SAFETY_QUERY_REFUSAL = (
    "⚠️ **Food Safety Notice:** FoodLink AI is not permitted to determine whether food is safe "
    "to consume or whether spoiled/expired items can be salvaged. "
    "Expired food must NEVER be donated or distributed on FoodLink. "
    "For health and safety reasons, food viability must be assessed by certified human inspectors "
    "or discarded if past expiry or questionable. Rule of thumb: *When in doubt, throw it out.*"
)

# Safety keywords that suggest user is asking if spoiled/expired food is safe to eat or seeking safety certification
SAFETY_PROMPT_PATTERNS = [
    r"\bsafe to (eat|consume|drink)\b",
    r"\b(can i|is it ok to) (eat|consume|drink|donate) .*(expired|spoiled|moldy|rotten|sour|bad)\b",
    r"\b(expired|spoiled|moldy|rotten|sour|bad) .*(safe|edible|good to eat|okay to eat)\b",
    r"\bis (this|it|food) .*(safe to|edible|safe for)\b",
    r"\bhow to tell if .* (is safe|won't make me sick)\b",
    r"\bwill i get sick if i eat\b",
    r"\bcertify (that )?.*safe\b",
    r"\bis .* still good after (expiry|expiration)\b",
    r"\bcan i donate (expired|spoiled)\b",
]


class AIAssistant:
    """
    Encapsulates Gemma 4 AI Assistant capabilities for FoodLink.
    Decoupled from Flask web routing.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        default_model: Optional[str] = None,
        enabled: Optional[bool] = None,
        timeout: int = 10,
    ):
        # Credentials stored strictly in environment variables
        self.api_key = api_key or os.getenv("GEMMA_API_KEY", "").strip()
        # API Base defaults to standard compatible OpenAI-style endpoint (e.g. OpenRouter, vLLM, or Google Cloud)
        self.api_base = (
            api_base
            or os.getenv("GEMMA_API_BASE", "https://generativelanguage.googleapis.com/v1beta/openai/").rstrip("/")
        )
        # Default model configurable
        env_model = os.getenv("GEMMA_DEFAULT_MODEL", MODEL_26B).strip()
        self.default_model = default_model if default_model in SUPPORTED_MODELS else (
            env_model if env_model in SUPPORTED_MODELS else MODEL_26B
        )
        # Feature toggle (optional)
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = os.getenv("AI_ENABLED", "true").lower() in ("1", "true", "yes")

        self.timeout = int(os.getenv("GEMMA_REQUEST_TIMEOUT", str(timeout)))

    def is_available(self) -> bool:
        """Returns True if AI feature is enabled and API key is present."""
        return self.enabled and bool(self.api_key)

    def select_model(self, task: str, requested_model: Optional[str] = None) -> str:
        """
        DETERMINISTIC MODEL ROUTING:
        - gemma-4-31b-it: For detailed reasoning, storage/handling advice, donation description drafting, Q&A.
        - gemma-4-26b-a4b-it: For fast, lightweight responses like category suggestions and summaries.
        - User or caller can explicitly select a model.
        - Never calls both models for a single task!
        """
        if requested_model and requested_model in SUPPORTED_MODELS:
            return requested_model

        if task in ("storage_handling", "draft_description", "waste_qa"):
            return MODEL_31B
        elif task in ("suggest_category", "summarize"):
            return MODEL_26B
        return self.default_model

    def check_safety_restriction(self, text: str) -> Optional[str]:
        """
        Checks if the input violates safety restrictions (e.g., asking if spoiled food is safe).
        Returns refusal message if violated, None otherwise.
        """
        lower = text.lower()
        for pattern in SAFETY_PROMPT_PATTERNS:
            if re.search(pattern, lower):
                return SAFETY_QUERY_REFUSAL
        return None

    def call_gemma_api(self, prompt: str, system_prompt: str, model: str) -> Tuple[bool, str]:
        """
        Dispatches request to Gemma-compatible API provider.
        Catches timeouts, connection errors, HTTP errors, and rate limits.
        Returns: (success: bool, response_or_error: str)
        """
        if not self.is_available():
            return False, "AI Assistant is currently offline (API key not configured or AI disabled)."

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 600,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return True, content.strip()
            elif resp.status_code == 429:
                logger.warning("Gemma API rate limit hit (429).")
                return False, "Rate limit exceeded. Falling back to local offline assistant."
            elif resp.status_code == 401 or resp.status_code == 403:
                logger.warning(f"Gemma API authentication error ({resp.status_code}).")
                return False, "AI authentication error. Falling back to local offline assistant."
            else:
                logger.warning(f"Gemma API returned status {resp.status_code}: {resp.text}")
                return False, f"API error ({resp.status_code}). Falling back to local offline assistant."
        except requests.exceptions.Timeout:
            logger.warning("Gemma API call timed out.")
            return False, "AI service timed out. Falling back to local offline assistant."
        except requests.exceptions.RequestException as e:
            logger.warning(f"Gemma API network exception: {e}")
            return False, "Network error reaching AI service. Falling back to local offline assistant."
        except Exception as e:
            logger.exception(f"Unexpected error calling Gemma API: {e}")
            return False, "Unexpected error. Falling back to local offline assistant."

    # -------------------------------------------------------------------------
    # Feature 1: Food Category Suggestions based on Food Descriptions
    # -------------------------------------------------------------------------
    def suggest_category(
        self, description: str, requested_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Suggests food category from standard FoodLink categories.
        Uses lightweight gemma-4-26b-a4b-it by default.
        """
        if not description or not description.strip():
            return {"category": "Other", "model_used": None, "source": "fallback", "message": "No description provided."}

        model = self.select_model("suggest_category", requested_model)
        system_prompt = (
            "You are FoodLink AI, a classification assistant for food donations. "
            "Given a food description, choose the single most appropriate category from this exact list:\n"
            "- Produce (Fruits & Veggies)\n"
            "- Bakery & Bread\n"
            "- Prepared Meals & Cooked Food\n"
            "- Dairy & Eggs\n"
            "- Pantry & Canned Goods\n"
            "- Beverages\n"
            "- Meat & Poultry\n"
            "- Other\n"
            "Output ONLY the exact category name and nothing else."
        )

        success, response = self.call_gemma_api(description, system_prompt, model)
        if success:
            suggested = response.strip()
            # Verify category is in list
            for valid_cat in [
                "Produce (Fruits & Veggies)", "Bakery & Bread", "Prepared Meals & Cooked Food",
                "Dairy & Eggs", "Pantry & Canned Goods", "Beverages", "Meat & Poultry", "Other"
            ]:
                if valid_cat.lower() in suggested.lower():
                    return {
                        "category": valid_cat,
                        "model_used": model,
                        "source": "gemma_api",
                        "raw_output": suggested,
                    }

        # Deterministic Fallback if API fails or is offline
        fallback_cat = self._deterministic_category_fallback(description)
        return {
            "category": fallback_cat,
            "model_used": None,
            "source": "fallback",
            "message": "Suggested using deterministic rules (AI service offline or unconfigured).",
        }

    def _deterministic_category_fallback(self, desc: str) -> str:
        d = desc.lower()
        # Prepared meals & dishes check first (e.g. vegetable lasagna is a prepared meal, not raw produce)
        if any(w in d for w in ["soup", "lasagna", "curry", "rice", "pasta dish", "casserole", "sandwich", "pizza", "meal", "cooked", "stew", "platter", "portions"]):
            return "Prepared Meals & Cooked Food"
        if any(w in d for w in ["bread", "loaf", "bagel", "pastry", "croissant", "cake", "muffin", "sourdough", "bun", "baguette"]):
            return "Bakery & Bread"
        if any(w in d for w in ["apple", "banana", "tomato", "potato", "salad", "fruit", "veggie", "vegetable", "lettuce", "carrot", "orange", "spinach"]):
            return "Produce (Fruits & Veggies)"
        if any(w in d for w in ["milk", "cheese", "yogurt", "egg", "butter", "cream"]):
            return "Dairy & Eggs"
        if any(w in d for w in ["canned", "can", "beans", "tuna", "flour", "sugar", "oats", "cereal", "pasta dry", "sauce jar", "pantry"]):
            return "Pantry & Canned Goods"
        if any(w in d for w in ["juice", "water", "soda", "tea", "coffee", "beverage", "drink", "smoothie"]):
            return "Beverages"
        if any(w in d for w in ["chicken", "beef", "pork", "fish", "meat", "turkey", "ham"]):
            return "Meat & Poultry"
        return "Other"

    # -------------------------------------------------------------------------
    # Feature 2: Suggestions for Appropriate Food Storage and Handling
    # -------------------------------------------------------------------------
    def suggest_storage_and_handling(
        self, food_item: str, requested_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Suggests food storage condition and handling instructions.
        Uses detailed reasoning gemma-4-31b-it by default.
        Always includes safety disclaimer. AI never determines safety.
        """
        # Safety restriction check
        safety_violation = self.check_safety_restriction(food_item)
        if safety_violation:
            return {
                "advice": safety_violation,
                "recommended_condition": "Ambient / Room Temperature",
                "model_used": None,
                "source": "safety_guard",
                "disclaimer": SAFETY_DISCLAIMER,
            }

        model = self.select_model("storage_handling", requested_model)
        system_prompt = (
            "You are FoodLink AI Assistant. You provide practical storage and handling tips for food donations. "
            "CRITICAL RULES:\n"
            "- NEVER claim or certify that food is safe or free of pathogens.\n"
            "- NEVER suggest donating or consuming expired food.\n"
            "- Specify one of: Ambient / Room Temperature, Refrigerated (< 4°C / 40°F), or Frozen (< -18°C / 0°F).\n"
            "- Keep advice concise (3-4 bullet points).\n"
            "- Always end with standard storage guidance."
        )
        prompt = f"Provide standard storage and safe handling recommendations for: {food_item}"

        success, response = self.call_gemma_api(prompt, system_prompt, model)
        if success:
            advice = response.strip()
            condition = self._detect_storage_condition(advice)
            return {
                "advice": advice,
                "recommended_condition": condition,
                "model_used": model,
                "source": "gemma_api",
                "disclaimer": SAFETY_DISCLAIMER,
            }

        # Deterministic Fallback
        advice, condition = self._deterministic_storage_fallback(food_item)
        return {
            "advice": advice,
            "recommended_condition": condition,
            "model_used": None,
            "source": "fallback",
            "disclaimer": SAFETY_DISCLAIMER,
            "message": "Storage recommendations provided via deterministic food guidelines (AI offline).",
        }

    def _detect_storage_condition(self, text: str) -> str:
        t = text.lower()
        if "frozen" in t or "-18" in t or "freezer" in t:
            return "Frozen (< -18°C / 0°F)"
        if "refrigerat" in t or "chill" in t or "4°c" in t or "40°f" in t or "cool" in t:
            return "Refrigerated (< 4°C / 40°F)"
        return "Ambient / Room Temperature"

    def _deterministic_storage_fallback(self, item: str) -> Tuple[str, str]:
        t = item.lower()
        if any(w in t for w in ["frozen", "ice cream", "meat frozen", "frozen meal"]):
            cond = "Frozen (< -18°C / 0°F)"
            advice = (
                "• Keep solidly frozen at or below -18°C (0°F) until collection.\n"
                "• Use insulated thermal bags or coolers during transit.\n"
                "• Do not refreeze once thawed."
            )
        elif any(w in t for w in ["milk", "dairy", "cheese", "meat", "chicken", "cooked", "meal", "soup", "salad", "prepared", "sandwich"]):
            cond = "Refrigerated (< 4°C / 40°F)"
            advice = (
                "• Keep refrigerated in a sealed, food-grade container at or below 4°C (40°F).\n"
                "• Keep cooked foods separated from raw ingredients to prevent cross-contamination.\n"
                "• Ensure transport is temperature-controlled to preserve freshness."
            )
        else:
            cond = "Ambient / Room Temperature"
            advice = (
                "• Store in a clean, cool, dry place away from direct sunlight and pests.\n"
                "• Keep packaging tightly sealed to protect against moisture.\n"
                "• Handle cartons and baked goods gently to avoid crushing."
            )
        return advice, cond

    # -------------------------------------------------------------------------
    # Feature 3: Summarizing Food Donation Descriptions
    # -------------------------------------------------------------------------
    def summarize_donation(
        self, description: str, requested_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Summarizes food donation descriptions into a concise recipient-friendly brief.
        Uses lightweight gemma-4-26b-a4b-it by default.
        """
        if not description or not description.strip():
            return {"summary": "No description available.", "model_used": None, "source": "fallback"}

        model = self.select_model("summarize", requested_model)
        system_prompt = (
            "You are FoodLink AI. Summarize the following food donation description into 1-2 concise, "
            "clear sentences highlighting: what the food is, quantity/servings, and key packaging or handling condition. "
            "Do NOT invent details or guarantees."
        )

        success, response = self.call_gemma_api(description, system_prompt, model)
        if success:
            return {
                "summary": response.strip(),
                "model_used": model,
                "source": "gemma_api",
            }

        # Deterministic Fallback
        lines = [line.strip() for line in description.splitlines() if line.strip()]
        first_line = lines[0] if lines else description
        if len(first_line) > 140:
            first_line = first_line[:137] + "..."
        return {
            "summary": first_line,
            "model_used": None,
            "source": "fallback",
            "message": "Summary generated deterministically (AI offline).",
        }

    # -------------------------------------------------------------------------
    # Feature 4: Helping Donors Write Clear and Informative Descriptions
    # -------------------------------------------------------------------------
    def improve_donation_description(
        self, raw_input: str, requested_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Helps donors write clear, comprehensive, informative donation descriptions.
        Prompts for allergens, packaging, servings, and pickup notes.
        Uses detailed reasoning gemma-4-31b-it by default.
        """
        # Safety restriction check
        safety_violation = self.check_safety_restriction(raw_input)
        if safety_violation:
            return {
                "improved_text": "",
                "advice": safety_violation,
                "model_used": None,
                "source": "safety_guard",
            }

        model = self.select_model("draft_description", requested_model)
        system_prompt = (
            "You are FoodLink AI Assistant. Help the food donor polish their donation listing description. "
            "Rules:\n"
            "1. Output an improved, clear description emphasizing food type, estimated quantity/portions, packaging, and allergen notes.\n"
            "2. NEVER recommend donating expired food.\n"
            "3. Do not add fake certifications.\n"
            "4. Provide 2-3 quick bullet points of tips to make pickup smoother."
        )

        success, response = self.call_gemma_api(raw_input, system_prompt, model)
        if success:
            return {
                "improved_text": response.strip(),
                "model_used": model,
                "source": "gemma_api",
            }

        # Deterministic Fallback
        template = (
            f"**Donation Details:** {raw_input.strip()}\n\n"
            "**Key Donor Checklist for Description Clarity:**\n"
            "• **Quantity & Portions:** State exact count (e.g., '10 individual boxed meals' or '5 kg box').\n"
            "• **Packaging & Allergens:** Mention if items are sealed and list common allergens (contains nuts, dairy, gluten, or vegan).\n"
            "• **Storage & Pickup:** Specify if refrigerated/ambient and best pickup window (e.g., 'Pickup available between 2 PM - 5 PM')."
        )
        return {
            "improved_text": template,
            "model_used": None,
            "source": "fallback",
            "message": "Generated using donor best-practice templates (AI offline).",
        }

    # -------------------------------------------------------------------------
    # Feature 5: Answering General Questions About Reducing Food Waste
    # -------------------------------------------------------------------------
    def answer_food_waste_question(
        self, question: str, requested_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Answers general food waste reduction and donation questions.
        Uses detailed reasoning gemma-4-31b-it by default.
        """
        if not question or not question.strip():
            return {
                "answer": "Please ask a question about reducing food waste or donation best practices.",
                "model_used": None,
                "source": "fallback",
            }

        # Safety restriction check: refusal if asking if unsafe/expired food is safe to eat
        safety_violation = self.check_safety_restriction(question)
        if safety_violation:
            return {
                "answer": safety_violation,
                "model_used": None,
                "source": "safety_guard",
                "disclaimer": SAFETY_DISCLAIMER,
            }

        model = self.select_model("waste_qa", requested_model)
        system_prompt = (
            "You are FoodLink AI, an expert educational assistant on food waste reduction and community food sharing. "
            "Provide helpful, practical, encouraging answers on:\n"
            "- First-In, First-Out (FIFO) kitchen practices\n"
            "- Safe portion planning and surplus food management\n"
            "- Backyard composting basics\n"
            "- Supporting local food recovery organizations\n"
            "RESTRICTIONS:\n"
            "- Never tell anyone to eat expired or spoiled food.\n"
            "- Do not invent health certifications.\n"
            "- Keep answers well-structured and engaging."
        )

        success, response = self.call_gemma_api(question, system_prompt, model)
        if success:
            return {
                "answer": response.strip(),
                "model_used": model,
                "source": "gemma_api",
                "disclaimer": SAFETY_DISCLAIMER,
            }

        # Deterministic Fallback
        fallback_answer = self._deterministic_qa_fallback(question)
        return {
            "answer": fallback_answer,
            "model_used": None,
            "source": "fallback",
            "disclaimer": SAFETY_DISCLAIMER,
            "message": "Answer provided via FoodLink Community Knowledge Base (AI offline).",
        }

    def _deterministic_qa_fallback(self, question: str) -> str:
        q = question.lower()
        if "compost" in q:
            return (
                "**Composting Basics for Reducing Food Waste:**\n\n"
                "1. **Greens (Nitrogen):** Fruit scraps, vegetable peels, coffee grounds, and tea leaves.\n"
                "2. **Browns (Carbon):** Dry leaves, cardboard scraps, egg cartons, and paper napkins.\n"
                "3. **What to Avoid:** Cooked meats, dairy, oils, and diseased plants to deter pests.\n"
                "4. **Balance:** Keep a ratio of roughly 2 parts brown to 1 part green, and keep moist like a wrung-out sponge."
            )
        elif any(w in q for w in ["fifo", "fridge", "organize", "store"]):
            return (
                "**FIFO (First-In, First-Out) Storage Method:**\n\n"
                "• Place newer groceries behind older items on shelves and in the refrigerator.\n"
                "• Label leftovers with the date they were prepared.\n"
                "• Dedicate an 'Eat First' bin in your fridge for produce and dairy nearing their use-by dates."
            )
        elif any(w in q for w in ["donate", "organization", "charity", "food link", "foodlink"]):
            return (
                "**FoodLink Donation Guidelines:**\n\n"
                "• **What Can Be Donated:** Unopened packaged goods, fresh produce, commercial bakery items, and properly handled prepared meals within safe date limits.\n"
                "• **What CANNOT Be Donated:** Expired food, items with broken seals, unpasteurized dairy, or food held at unsafe temperatures.\n"
                "• **Safety First:** Donors must specify proper storage requirements (ambient, refrigerated, frozen) upon listing."
            )
        else:
            return (
                "**Top 4 Everyday Tips to Reduce Food Waste:**\n\n"
                "1. **Meal Planning:** Check your pantry and make a grocery list before shopping to avoid impulse surplus.\n"
                "2. **Smart Storage:** Keep apples away from other fruits (they release ethylene gas); keep leafy greens dry with a paper towel.\n"
                "3. **Creative Leftovers:** Transform vegetable trimmings into broth, and stale bread into croutons or breadcrumbs.\n"
                "4. **Share Surplus via FoodLink:** If you have wholesome unexpired food you cannot use, post a donation on FoodLink for local community members."
            )

    # -------------------------------------------------------------------------
    # Feature 6: Custom AI Prompt Playground in AI Assistant Space
    # -------------------------------------------------------------------------
    def execute_custom_prompt(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        requested_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes an open-ended custom prompt in the FoodLink AI Assistant Space.
        Enforces safety guardrails while allowing full flexibility with Gemma 4.
        Defaults to gemma-4-31b-it for detailed reasoning.
        """
        if not prompt or not prompt.strip():
            return {
                "response": "Please enter a prompt for the AI Assistant.",
                "model_used": None,
                "source": "fallback",
                "disclaimer": SAFETY_DISCLAIMER,
            }

        # Safety restriction check: intercepts queries asking to certify spoiled food
        safety_violation = self.check_safety_restriction(prompt)
        if safety_violation:
            return {
                "response": safety_violation,
                "model_used": None,
                "source": "safety_guard",
                "disclaimer": SAFETY_DISCLAIMER,
            }

        model = self.select_model("custom_prompt", requested_model) if requested_model in SUPPORTED_MODELS else (
            requested_model if requested_model in SUPPORTED_MODELS else MODEL_31B
        )

        sys_prompt = system_prompt or (
            "You are FoodLink AI Assistant, powered by Google Gemma 4. "
            "You help users with food surplus reduction, community sharing, meal planning, "
            "and food donation organization. Provide clear, well-structured, actionable answers. "
            "RESTRICTIONS: Never recommend eating or donating expired/spoiled food. "
            "Do not invent fake health certifications."
        )

        success, response = self.call_gemma_api(prompt, sys_prompt, model)
        if success:
            return {
                "response": response.strip(),
                "model_used": model,
                "source": "gemma_api",
                "disclaimer": SAFETY_DISCLAIMER,
            }

        # Deterministic offline fallback response
        offline_reply = (
            f"**FoodLink AI Assistant (Offline Mode):**\n\n"
            f"Thank you for your prompt: *\"{prompt.strip()[:100]}...\"*\n\n"
            "Live Gemma 4 API is currently offline or operating without an API key. "
            "For food surplus recovery and community sharing, remember our standard best practices:\n"
            "• Ensure all donated food is strictly within its expiration date.\n"
            "• Maintain proper temperature control (chilled < 4°C, frozen < -18°C).\n"
            "• Provide detailed portion counts and clear allergen warnings on all listings."
        )
        return {
            "response": offline_reply,
            "model_used": None,
            "source": "fallback",
            "disclaimer": SAFETY_DISCLAIMER,
            "message": "Generated via offline fallback engine.",
        }

    # -------------------------------------------------------------------------
    # Feature 7: Automatic AI Inspection for Every Donation
    # -------------------------------------------------------------------------
    def check_donation(
        self,
        title: str,
        description: str,
        category: str,
        quantity: str,
        storage_requirement: str,
        requested_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Integrates AI into the donation submission pipeline to inspect every donation.
        Evaluates:
        1. Safety & Policy Pre-check (flags any mention of expired/spoiled/prohibited food)
        2. Description clarity and completeness (portions, packaging, allergens)
        3. Category alignment
        4. Storage condition suitability
        5. Generated recipient summary

        NOTE: AI check is assistive. Deterministic Python backend checks strictly control
        expiry dates and database availability.
        """
        combined_text = f"{title} {description}".lower()

        # Check for spoiled or expired food mentions
        unsafe_keywords = ["expired", "spoiled", "moldy", "rotten", "sour milk", "bad smell", "smelly"]
        flagged_unsafe = any(k in combined_text for k in unsafe_keywords)

        if flagged_unsafe:
            return {
                "status": "FLAGGED_UNSAFE",
                "clarity_score": 20,
                "summary": f"Listing flagged for review: potential mention of expired or spoiled items.",
                "feedback": [
                    "⚠️ CRITICAL: FoodLink strictly prohibits donating expired, spoiled, or questionable food.",
                    "Please verify that this food is fresh and within safe consumption limits before posting.",
                ],
                "allergen_notice": "Cannot assess due to safety flag.",
                "storage_evaluation": "Please discard spoiled food responsibly.",
                "model_used": None,
                "source": "safety_guard",
                "disclaimer": SAFETY_DISCLAIMER,
            }

        model = self.select_model("draft_description", requested_model)
        system_prompt = (
            "You are FoodLink AI Quality Inspector. Review this food donation listing for a community food sharing app. "
            "Analyze: 1) Quality & clarity score (0-100), 2) Category suitability, 3) Storage suitability, "
            "4) Allergen & packaging notices, 5) A concise 1-sentence recipient summary. "
            "Output valid JSON format with keys: clarity_score (int), category_ok (bool), storage_ok (bool), "
            "summary (str), feedback (list of str), allergen_notice (str)."
        )
        prompt = (
            f"Title: {title}\n"
            f"Description: {description}\n"
            f"Category: {category}\n"
            f"Quantity: {quantity}\n"
            f"Storage Condition: {storage_requirement}"
        )

        success, response = self.call_gemma_api(prompt, system_prompt, model)
        if success:
            try:
                # Attempt to parse JSON from Gemma
                clean_json = response.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()
                data = json.loads(clean_json)
                return {
                    "status": "APPROVED" if data.get("clarity_score", 80) >= 60 else "NEEDS_ATTENTION",
                    "clarity_score": int(data.get("clarity_score", 85)),
                    "summary": data.get("summary", f"{quantity} of {title} in {storage_requirement} condition."),
                    "feedback": data.get("feedback", ["Listing reviewed by Gemma 4 AI Inspector."]),
                    "allergen_notice": data.get("allergen_notice", "Standard allergen review completed."),
                    "storage_evaluation": "Verified matching storage requirements." if data.get("storage_ok", True) else "Review recommended storage condition.",
                    "model_used": model,
                    "source": "gemma_api",
                    "disclaimer": SAFETY_DISCLAIMER,
                }
            except Exception:
                # Fallback to deterministic parser if response is text
                pass

        # Deterministic Inspection Fallback
        return self._deterministic_donation_inspection(
            title, description, category, quantity, storage_requirement
        )

    def _deterministic_donation_inspection(
        self, title: str, description: str, category: str, quantity: str, storage: str
    ) -> Dict[str, Any]:
        feedback = []
        clarity_score = 70

        # Check quantity detail
        if len(quantity.strip()) < 3 or quantity.isdigit():
            feedback.append("• Tip: Specify exact units in quantity (e.g., '10 boxed meals' or '5 kg box').")
        else:
            clarity_score += 10
            feedback.append("• Quantity details are clear.")

        # Check description length
        if len(description.strip()) < 20:
            feedback.append("• Description is very brief. Adding packaging or pickup notes helps recipients.")
        else:
            clarity_score += 10
            feedback.append("• Description provides helpful details.")

        # Check allergens
        d_lower = description.lower()
        has_allergen_mention = any(a in d_lower for a in ["nuts", "peanut", "gluten", "wheat", "dairy", "milk", "egg", "soy", "vegan", "vegetarian"])
        if has_allergen_mention:
            allergen_notice = "Allergen or dietary information provided."
            clarity_score += 10
            feedback.append("• Allergen/dietary keywords identified.")
        else:
            allergen_notice = "No explicit allergen declaration detected (consider noting if nuts, gluten, or dairy are present)."
            feedback.append("• Recommended: Note any common allergens (nuts, gluten, dairy) if applicable.")

        # Check storage suitability
        storage_eval = "Storage condition appears consistent with food type."
        is_perishable = any(w in (title + " " + description).lower() for w in ["chicken", "meat", "fish", "dairy", "milk", "cheese", "curry", "soup", "lasagna", "cooked"])
        if is_perishable and "Ambient" in storage:
            storage_eval = "⚠️ Warning: Cooked foods and dairy should typically be kept Refrigerated (< 4°C)."
            feedback.append("• Temperature advisory: Consider updating storage requirement to Refrigerated for cooked/perishable items.")
            clarity_score -= 15

        # Generated summary
        summary = f"{quantity} of {title}; {storage.split('/')[0].strip()} storage."

        return {
            "status": "APPROVED" if clarity_score >= 60 else "NEEDS_ATTENTION",
            "clarity_score": min(100, max(20, clarity_score)),
            "summary": summary,
            "feedback": feedback,
            "allergen_notice": allergen_notice,
            "storage_evaluation": storage_eval,
            "model_used": None,
            "source": "fallback",
            "disclaimer": SAFETY_DISCLAIMER,
        }
