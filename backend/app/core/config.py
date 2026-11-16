from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "English Practice API"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    cors_origins: list[str] = Field(default_factory=list)
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = Field(default="english_practice", min_length=1)
    postgres_user: str = Field(default="english_app", min_length=1)
    postgres_password: SecretStr = Field(min_length=1)

    # Authentication. No default secret: the app refuses to start without one.
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_issuer: str = "english-practice-api"
    jwt_audience: str = "english-practice-app"
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    # Sliding window: each successful refresh extends the session by this many days.
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=365)
    password_min_length: int = Field(default=8, ge=8)
    # Bounds hashing work only; not a composition rule. Passphrases are welcome.
    password_max_length: int = Field(default=256, ge=64, le=4096)
    # OWASP Argon2id minimum (m=19 MiB, t=2, p=1). Raise after benchmarking the VPS.
    argon2_memory_kib: int = Field(default=19_456, ge=8_192)
    argon2_time_cost: int = Field(default=2, ge=1)
    argon2_parallelism: int = Field(default=1, ge=1)
    # In-memory, per-process limits. With several API workers each worker counts
    # separately; use a shared store (e.g. Redis/PostgreSQL) before scaling out.
    auth_rate_limit_enabled: bool = True
    login_attempts_per_window: int = Field(default=10, ge=1)
    register_attempts_per_window: int = Field(default=10, ge=1)
    refresh_attempts_per_window: int = Field(default=30, ge=1)
    auth_rate_limit_window_seconds: int = Field(default=300, ge=1)
    # Per email (identical for known/unknown), to stop flooding someone's inbox.
    forgot_password_per_window: int = Field(default=3, ge=1)
    password_reset_ttl_minutes: int = Field(default=30, ge=5, le=1_440)
    # None picks a safe default: "outbox" in development/test, "disabled" in production.
    password_reset_delivery: Literal["disabled", "outbox", "memory"] | None = None
    password_reset_outbox_dir: Path = PROJECT_ROOT / "var" / "outbox"

    # Reported by GET /capabilities. Illustrative defaults until benchmarked on the VPS.
    # max_request_bytes is enforced for every request; the audio limits bound Speaking
    # recordings (uploads).
    max_request_bytes: int = Field(default=12 * 1024 * 1024, ge=64 * 1024)
    max_audio_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    max_audio_duration_ms: int = Field(default=120_000, ge=1_000)

    # AI provider. No model is chosen yet. "fake" is a deterministic stand-in for
    # development/tests; "none" leaves jobs queued (the worker refuses to start).
    # None picks "fake" outside production and "none" in production.
    ai_provider: Literal["none", "fake"] | None = None
    ai_request_timeout_seconds: float = Field(default=120, gt=0)

    # Durable job queue and worker.
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    job_lease_seconds: int = Field(default=180, ge=10)
    job_retry_base_seconds: float = Field(default=5, ge=0)
    job_retry_max_seconds: float = Field(default=300, ge=0)
    worker_poll_seconds: float = Field(default=1.0, gt=0)
    worker_concurrency: int = Field(default=1, ge=1, le=16)
    max_active_generation_jobs_per_user: int = Field(default=3, ge=1)
    idempotency_ttl_hours: int = Field(default=24, ge=1)
    # Model-capacity bound for evaluation (not a UI limit): longer text is rejected with
    # 413 at submit and the draft is kept. Drafts themselves have no length limit.
    writing_max_submission_chars: int = Field(default=20_000, ge=1_000)

    # Reading generation bounds. Requests above them get 413 rather than being shrunk.
    reading_max_questions: int = Field(default=15, ge=1)
    reading_max_word_count: int = Field(default=1_200, ge=100)
    # A passage needs room for its questions: requested words >= this x question count.
    reading_min_words_per_question: int = Field(default=20, ge=1)
    reading_vocabulary_count: int = Field(default=5, ge=0, le=20)
    # Accepted deviation of the generated passage length from the requested length.
    reading_word_count_tolerance: float = Field(default=0.4, gt=0, lt=1)

    # Listening generation bounds; same explicit-error policy as Reading.
    listening_max_questions: int = Field(default=10, ge=1)
    listening_max_word_count: int = Field(default=600, ge=50)
    listening_min_words_per_question: int = Field(default=20, ge=1)
    listening_word_count_tolerance: float = Field(default=0.4, gt=0, lt=1)
    # Abstract voice keys; each TTS adapter maps them to its own voices.
    listening_voices: list[str] = Field(
        default_factory=lambda: ["female_1", "male_1"], min_length=1
    )
    # Speaking. Only the most recent successful messages are sent to the model.
    speaking_context_messages: int = Field(default=20, ge=2, le=200)
    speaking_max_user_turns: int = Field(default=40, ge=1)
    # Spoken replies above this length are rejected as invalid model output.
    speaking_max_reply_chars: int = Field(default=1_000, ge=50)

    # Generated audio (Listening recordings, Speaking replies) is untrusted model output:
    # bounded before it is stored.
    tts_max_audio_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    tts_max_audio_duration_ms: int = Field(default=600_000, ge=1_000)

    # How long a waiting Listening coordinator sleeps before re-checking its grades.
    # Finished grades also wake it immediately; this is only the fallback.
    coordinator_poll_seconds: float = Field(default=15, gt=0)

    # Private media files (never served statically). API and worker must share this
    # directory. Files without a database row are removed after the grace period.
    media_storage_dir: Path = PROJECT_ROOT / "var" / "media"
    media_orphan_grace_seconds: int = Field(default=3_600, ge=60)
    media_sweep_interval_seconds: int = Field(default=3_600, ge=60)

    @model_validator(mode="after")
    def _resolve_ai(self) -> Settings:
        if self.ai_provider is None:
            self.ai_provider = "none" if self.app_env == "production" else "fake"
        if self.app_env == "production" and self.ai_provider == "fake":
            raise ValueError("The fake AI engine is for development and tests only.")
        return self

    @model_validator(mode="after")
    def _resolve_delivery(self) -> Settings:
        if self.password_reset_delivery is None:
            self.password_reset_delivery = "disabled" if self.app_env == "production" else "outbox"
        if self.app_env == "production" and self.password_reset_delivery != "disabled":
            # Local sinks would silently swallow real users' reset messages.
            raise ValueError("Production needs a real reset-email provider; none exists yet.")
        return self

    @property
    def database_url(self) -> URL:
        # URL.create safely handles reserved characters in credentials.
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
