"""
config.py - Application configuration for FoodLink.

Loads settings from environment variables with safe defaults.
Ensures API keys are never hardcoded or exposed to frontend.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "foodlink-dev-secret-key-change-in-prod-2026")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "foodlink.db")

    # Gemma AI configuration
    GEMMA_API_KEY = os.getenv("GEMMA_API_KEY", "").strip()
    GEMMA_API_BASE = os.getenv("GEMMA_API_BASE", "https://generativelanguage.googleapis.com/v1beta/openai/").strip()
    GEMMA_DEFAULT_MODEL = os.getenv("GEMMA_DEFAULT_MODEL", "gemma-4-26b-a4b-it").strip()
    GEMMA_REQUEST_TIMEOUT = int(os.getenv("GEMMA_REQUEST_TIMEOUT", "10"))
    AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() in ("1", "true", "yes")
