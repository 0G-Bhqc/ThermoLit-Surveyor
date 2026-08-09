import os

# Sciverse API Settings (Load token from environment variable SCIVERSE_TOKEN)
SCIVERSE_TOKEN = os.getenv("SCIVERSE_TOKEN", "YOUR_SCIVERSE_TOKEN_HERE")

# LLM Settings (DeepSeek / OpenAI compatible API, load key from DEEPSEEK_API_KEY)
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "YOUR_DEEPSEEK_API_KEY_HERE")
LLM_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# Physical Constants for Thermoelectric Analysis
LORENZ_STANDARD = 2.44e-8  # W * Ohm * K^-2 (Standard degenerate limit)
LORENZ_NONDEGENERATE_LOW = 1.5e-8
LORENZ_NONDEGENERATE_HIGH = 2.2e-8
TEMPERATURE_ROOM = 300  # Kelvin
