from forex_intelligence.config import load_settings
from forex_intelligence.observability import configure_logging


def startup() -> None:
    settings = load_settings()
    logger = configure_logging()
    logger.info(settings.startup_banner)
