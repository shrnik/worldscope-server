from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Hugging Face
    hf_token: str = ""
    hf_bucket: str = ""  # "<namespace>/worldscope"
    hf_endpoint: str = "https://huggingface.co"
    hf_download_flavor: str = "cpu-upgrade"
    hf_embed_flavor: str = "t4-small"
    hf_cleanup_flavor: str = "cpu-basic"
    hf_job_timeout: str = "1h"

    # Embedding model (same checkpoint used by the server, the embed job, and the Space)
    embed_model: str = "google/tipsv2-b14"

    # Camera data sources
    sheet_url: str = (
        "https://sheets.googleapis.com/v4/spreadsheets/"
        "1_tbi4WTx9qGErN-2cvYvEd3qeJxgzd_9N9HJWWPD7SA/values/Main"
        "?alt=json&key=AIzaSyA6pmS1gW0a3dWzxdYOfo-sE5hmmvGrW8M"
    )
    faa_api_key: str = ""

    # Paths of artifacts inside the bucket
    manifest_path: str = "manifest.parquet"
    embeddings_path: str = "embeddings.parquet"

    # Search
    search_top_k: int = 50


settings = Settings()
