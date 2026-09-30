import os

from dotenv import load_dotenv

# 支持直接把 .env.example 复制为 .env 使用(此前 README 承诺了但代码从未加载 .env)
load_dotenv()

# Sciverse API Settings (Load token from environment variable SCIVERSE_TOKEN)
SCIVERSE_TOKEN = os.getenv("SCIVERSE_TOKEN", "")

# LLM Settings (DeepSeek / OpenAI compatible API, load key from DEEPSEEK_API_KEY)
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))

# Pipeline tuning
SEARCH_TOP_K = int(os.getenv("SEARCH_TOP_K", "3"))
NUM_FOLLOWUP_QUERIES = int(os.getenv("NUM_FOLLOWUP_QUERIES", "2"))
MAX_EXCERPT_CHARS = int(os.getenv("MAX_EXCERPT_CHARS", "3500"))
LLM_MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "4"))
LLM_REQUEST_RETRIES = int(os.getenv("LLM_REQUEST_RETRIES", "3"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# 结果缓存:设为 sqlite 路径即启用(同 prompt/query 的重复调研零 API 消耗)
THERMOLIT_CACHE = os.getenv("THERMOLIT_CACHE", "")


def is_configured(value: str) -> bool:
    """凭证是否已真正配置(排除空串和模板占位符)。"""
    return bool(value) and not value.startswith(("YOUR_", "your_"))
