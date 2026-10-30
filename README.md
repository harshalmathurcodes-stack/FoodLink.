# FoodLink - Community Food Sharing & Surplus Recovery

FoodLink is a resilient community food recovery and sharing platform built to bridge surplus food to shelters, pantries, and local community members.

It features an intelligent, decoupled **FoodLink AI Assistant** powered by **Google Gemma 4** models, with deterministic Python backend safeguards ensuring food safety and expiration validation.

---

## 🌟 Key Highlights

- **Deterministic Donate → View → Claim → Collect Workflow:** The core food rescue lifecycle runs with 100% deterministic backend business logic.
- **Google Gemma 4 Integration:**
  - `gemma-4-31b-it`: Deep reasoning for storage advice, description drafting, and food waste Q&A.
  - `gemma-4-26b-a4b-it`: High-speed, lightweight responses for smart category classification and listing summaries.
- **Configurable Model Selection:** Users and callers can configure model selection per task or toggle defaults. Only the chosen model is invoked per request.
- **Decoupled Architecture:** `ai_assistant.py` is segregated from the Flask application. If AI models or credentials are unconfigured or offline, the entire application operates seamlessly with deterministic fallbacks.
- **Zero API Key Exposure:** Secrets are read strictly from environment variables on the backend—never exposed to frontend JavaScript or public repositories.
- **Strict Food Safety Boundaries:** AI has zero authority to determine food safety or override expiration. Expired food donations are deterministically rejected.

---

## 🏗️ Architecture & Core Workflow

### 1. The Core Lifecycle: Donate → View → Claim → Collect

```
  ┌────────────────┐
  │ 1. Donate Food │ ──> Strict Python backend checks: expiry_date > now
  └────────┬───────┘     (Past dates deterministically rejected with HTTP 400)
           │
           ▼
  ┌────────────────┐
  │ 2. View Food   │ ──> Automatic check: if now > expiry_date, status = EXPIRED
  └────────┬───────┘     Search by keyword & filter by food category
           │
           ▼
  ┌────────────────┐
  │ 3. Claim Food  │ ──> Recipient reserves donation. Status = CLAIMED
  └────────┬───────┘     (Rejects claiming expired or already claimed food)
           │
           ▼
  ┌────────────────┐
  │ 4. Collect     │ ──> Donor/recipient confirms pickup. Status = COLLECTED
  └────────────────┘
```

### 2. FoodLink AI Assistant Features

| Feature | Primary Gemma Model | Purpose |
| :--- | :--- | :--- |
| **1. Category Suggestion** | `gemma-4-26b-a4b-it` | Classifies food descriptions into standard categories (Bakery, Produce, Prepared Meals, Dairy, etc.). |
| **2. Storage & Handling** | `gemma-4-31b-it` | Recommends appropriate storage (Ambient, Chilled, Frozen) with mandatory safety disclaimers. |
| **3. Summarizing Listings** | `gemma-4-26b-a4b-it` | Condenses verbose donation listings into concise 1–2 sentence briefs for recipients. |
| **4. Description Drafter** | `gemma-4-31b-it` | Helps donors structure listings with portion counts, packaging details, and allergen warnings. |
| **5. Food Waste Q&A** | `gemma-4-31b-it` | Answers questions regarding First-In, First-Out (FIFO), composting, and surplus reduction. |

---

## 🛡️ Critical Safety Guardrails

In adherence to food safety standards:
1. **No AI Safety Determinations:** AI cannot determine whether food is safe to consume, nor certify safety. Queries asking if spoiled, rotten, or expired food is safe to eat are intercepted by safety guards with a refusal notice: *"When in doubt, throw it out."*
2. **No AI Overrides on Expiry Dates:** Expiry date validation is enforced strictly by Python backend code. AI cannot adjust expiration dates or approve expired food.
3. **Never Recommend Donating Expired Food:** Expired food is strictly prohibited from donation on FoodLink.
4. **Deterministic Availability:** Items past their expiration timestamp are automatically marked `EXPIRED` in the database and cannot be claimed.
5. **No Invented Safety Certifications:** The platform never displays false certifications or safety guarantees.

---

## 📁 Project Structure

```
foodlink/
├── app.py                      # Core Flask web application & API routing
├── ai_assistant.py             # Decoupled Gemma 4 AI Assistant & fallback engine
├── models.py                   # Deterministic database layer, status lifecycle & schema
├── config.py                   # Configuration and environment variable loader
├── static/
│   ├── css/
│   │   └── style.css           # Clean modern responsive styling
│   └── js/
│       └── main.js             # Client-side scripts (Zero API keys exposed)
├── templates/
│   ├── base.html               # Shared layout, navbar, safety banners, footer
│   ├── index.html              # Landing page with stats, workflow & recent surplus
│   ├── listings.html           # Browse available food, category filter & search
│   ├── donate.html             # Donation form with integrated AI assistant helpers
│   ├── detail.html             # Item details, AI summary & claim/collect actions
│   └── ai_assistant.html       # Dedicated interactive FoodLink AI Assistant studio
├── tests/
│   ├── test_core_workflow.py   # Unit tests for Donate -> View -> Claim -> Collect
│   ├── test_ai_assistant.py    # Unit tests for Gemma AI, fallbacks, & safety guards
│   └── test_flask_app.py       # Integration tests for Flask web routes & API
├── .env.example                # Example environment configuration
├── .gitignore                  # Git ignore rules (secrets, databases, caches)
├── requirements.txt            # Python dependencies
└── README.md                   # Complete documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- pip

### 2. Installation
```bash
# Clone or navigate to the project directory
cd foodlink

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the example environment configuration:
```bash
cp .env.example .env
```
Edit `.env` to configure your settings:
```ini
# Flask Settings
SECRET_KEY=your-secret-key-here
PORT=5000

# Gemma AI Settings
AI_ENABLED=true
GEMMA_DEFAULT_MODEL=gemma-4-26b-a4b-it

# Compatible API Provider (e.g. Google AI Studio, vLLM, OpenRouter)
GEMMA_API_KEY=your_api_key_here
GEMMA_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai/
GEMMA_REQUEST_TIMEOUT=10
```
> **Note:** If `GEMMA_API_KEY` is omitted or unavailable, FoodLink runs in **Offline Fallback Mode** with high-quality deterministic suggestions. The core application functions without any degradation.

### 4. Running the Application
```bash
python app.py
```
Open your browser at:
```
http://localhost:5000
```

---

## 🧪 Running the Test Suite

Run all 22 automated tests:
```bash
python -m pytest tests -v
```

### Test Coverage Highlights:
- `test_core_workflow.py`: Validates deterministic creation, rejection of expired items, transitions from `AVAILABLE` to `CLAIMED` and `COLLECTED`, and clock-based auto-expiration.
- `test_ai_assistant.py`: Validates model routing (`gemma-4-31b-it` vs `gemma-4-26b-a4b-it`), all 5 features, safety interceptors, HTTP 429 rate limit handling, and offline fallbacks.
- `test_flask_app.py`: Validates Flask endpoints, form submissions, and AJAX `/api/ai/*` responses.
