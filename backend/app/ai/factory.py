from app.ai.engine import AIEngine
from app.core.config import Settings


def build_engine(settings: Settings) -> AIEngine | None:
    """None when no provider is configured: jobs then stay queued, honestly reported."""
    if settings.ai_provider == "fake":
        from app.ai.fake import FakeAIEngine

        return FakeAIEngine()
    if settings.ai_provider == "router":
        from app.ai.router import RouterAIEngine

        return RouterAIEngine(settings)
    return None
