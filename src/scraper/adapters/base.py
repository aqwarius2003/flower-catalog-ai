"""Базовый адаптер площадки — интерфейс для всех конкретных адаптеров."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.scraper.core import ScrapedProduct


class ShopAdapter(ABC):
    """Абстрактный адаптер магазина.

    Для поддержки нового магазина:
    1. Создайте файл ``adapters/myshop.py``
    2. Унаследуйте ``ShopAdapter``
    3. Реализуйте ``extract()`` и ``build_search_url()``
    4. Укажите CSS-селекторы для карточек товаров

    Пример::

        class MyShopAdapter(ShopAdapter):
            shop_name = "myshop.ru"

            def build_search_url(self, query: str) -> str:
                return f"https://myshop.ru/search?q={query}"

            def extract(self, page, **kwargs) -> list[ScrapedProduct]:
                products = []
                for card in page.css('.product-card'):
                    products.append(ScrapedProduct(
                        name=card.css('h3::text').get(''),
                        price=int(card.css('.price::text').get('0')),
                        source_shop=self.shop_name,
                    ))
                return products
    """

    shop_name: str = "unknown"

    @abstractmethod
    def build_search_url(self, query: str) -> str:
        """Формирует URL страницы поиска по запросу."""
        ...

    @abstractmethod
    def extract(
        self,
        page: Any,
        category: str = "",
        source_url: str = "",
    ) -> list[ScrapedProduct]:
        """Извлекает товары из объекта ответа Scrapling.

        Args:
            page: Объект Response от Scrapling (поддерживает .css()).
            category: Название категории для метаданных.
            source_url: URL исходной страницы.

        Returns:
            Список ScrapedProduct.
        """
        ...
