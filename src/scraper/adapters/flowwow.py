"""Адаптер Flowwow — крупнейший агрегатор цветов в РФ."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

from src.scraper.adapters.base import ShopAdapter
from src.scraper.core import ScrapedProduct

logger = logging.getLogger(__name__)


class FlowwowAdapter(ShopAdapter):
    """Парсер каталога Flowwow.

    Flowwow рендерит каталог через React/Next.js.
    Карточки товаров содержатся в контейнерах с атрибутами
    data-testid или классами вида ``ProductCard``, ``product-card``.

    Адаптер пробует несколько стратегий извлечения:
    1. JSON-LD (schema.org Product/ItemList)
    2. CSS-селекторы карточек
    3. Фолбэк по title/alt атрибутам
    """

    shop_name = "flowwow.com"

    def build_search_url(self, query: str) -> str:
        """URL поиска на Flowwow (обязательно с указанием языка и города)."""
        return f"https://flowwow.com/ru/moscow/search/?q={quote(query)}"

    def extract(
        self,
        page: Any,
        category: str = "",
        source_url: str = "",
    ) -> list[ScrapedProduct]:
        """Извлекает товары из ответа Scrapling."""
        products: list[ScrapedProduct] = []

        # ── Стратегия 2: CSS-селекторы карточек ───────────────────

        # ── Стратегия 2: CSS-селекторы карточек ───────────────────
        # Flowwow использует разные классы, пробуем несколько вариантов
        card_selectors = [
            '[data-testid="product-card"]',
            ".ProductCard",
            ".product-card",
            '[class*="ProductCard"]',
            '[class*="product-card"]',
            ".catalog-item",
            ".goods-item",
        ]

        cards = []
        for sel in card_selectors:
            try:
                cards = page.css(sel)
                if cards:
                    logger.debug("Нашли карточки по селектору: %s", sel)
                    break
            except Exception:
                continue

        if cards:
            for card in cards:
                # Название
                name = ""
                for name_sel in [
                    "h3::text",
                    "h2::text",
                    '[class*="title"]::text',
                    '[class*="name"]::text',
                    "a::attr(title)",
                    "img::attr(alt)",
                ]:
                    try:
                        name = (card.css(name_sel).get() or "").strip()
                        if name:
                            break
                    except Exception:
                        continue

                if not name:
                    continue

                # Собираем весь текст внутри карточки (спасает от зашифрованных классов React)
                all_text_nodes = card.xpath(".//text()").getall()
                all_text = " ".join([t.strip() for t in all_text_nodes if t.strip()])

                # Цена
                price = None
                pm = re.search(r"(\d[\d\s]*)\s*[₽р]", all_text)
                if pm:
                    price_str = re.sub(r"[^\d]", "", pm.group(1))
                    if price_str:
                        price = int(price_str)

                # Рейтинг
                rating = None
                rm = re.search(r"(?:⭐|★)?\s*(\d[.,]\d+)", all_text)
                if rm:
                    rating_str = rm.group(1).replace(",", ".")
                    rating = float(rating_str)

                # URL
                link = ""
                try:
                    link = card.css("a::attr(href)").get() or ""
                    if link and not link.startswith("http"):
                        link = f"https://flowwow.com{link}"
                except Exception:
                    pass

                # Изображение
                img = ""
                try:
                    img = (
                        card.css("img::attr(src)").get()
                        or card.css("img::attr(data-src)").get()
                        or ""
                    )
                except Exception:
                    pass

                products.append(
                    ScrapedProduct(
                        name=name,
                        price=price,
                        rating=rating,
                        url=link,
                        image_url=img,
                        source_shop=self.shop_name,
                        category=category,
                    )
                )

        if products:
            logger.info("Извлечено %d товаров через CSS-селекторы", len(products))
            return products

        # Третью стратегию (фолбэк по alt) удалили, так как она собирала мусор из меню.
        logger.info("Итого извлечено %d товаров", len(products))
        return products
