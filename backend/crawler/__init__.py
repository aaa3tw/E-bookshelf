from .service import crawler_service, SUPPORTED_SITES
from .downloader import NovelDownloader
from .adapters import get_adapter

__all__ = ["crawler_service", "SUPPORTED_SITES", "NovelDownloader", "get_adapter"]
