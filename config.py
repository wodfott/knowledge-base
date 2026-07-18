"""Application configuration loaded from environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_chat_model: str = "deepseek-chat"
    deepseek_embed_model: str = "deepseek-embed"

    # Feishu
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # Database paths
    vector_db_path: str = str(BASE_DIR / "data" / "vectors")
    graph_db_path: str = str(BASE_DIR / "data" / "graph.json")
    sqlite_path: str = str(BASE_DIR / "data" / "metadata.db")

    # Collection
    rss_poll_interval_minutes: int = 30
    simhash_threshold: float = 0.85

    # QA
    vector_search_top_k: int = 20
    rerank_top_n: int = 3
    semantic_cache_ttl_days: int = 7

    # Review
    review_time: str = "09:00"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
