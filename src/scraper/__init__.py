"""Scrapling Scraper — подключаемый модуль парсинга конкурентов.

Использует Scrapling (StealthyFetcher) для обхода антибот-защит
и извлечения товаров с цветочных маркетплейсов.
"""

from src.scraper.adapters.base import ShopAdapter
from src.scraper.core import ScrapedProduct, ScraplerEngine

__all__ = ["ScrapedProduct", "ScraplerEngine", "ShopAdapter"]
