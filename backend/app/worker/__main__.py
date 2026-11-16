import asyncio
import logging
import signal
import sys

from app.ai.factory import build_engine
from app.core.config import Settings
from app.db.session import Database
from app.worker.runner import Worker

logger = logging.getLogger("app.worker")


async def main() -> int:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    engine = build_engine(settings)
    if engine is None:
        # Jobs stay queued and are reported as such; nothing pretends to run them.
        logger.error("No AI provider configured (AI_PROVIDER=none); worker not started.")
        return 1
    if engine.is_fake:
        logger.warning("Using the development fake AI engine; results are illustrative.")
    database = Database(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    logger.info("Worker started (concurrency=%s)", settings.worker_concurrency)
    try:
        await Worker(settings, database, engine).run_forever(stop)
    finally:
        await database.close()
    logger.info("Worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
