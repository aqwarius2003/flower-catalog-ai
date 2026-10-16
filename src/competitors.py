"""Модуль анализа конкурентов: парсинг ассортимента цветочных магазинов и агрегаторов."""

import csv
import json
import re

from pydantic import BaseModel

from src.trace import tracer


class CompetitorProduct(BaseModel):
    """Товарная позиция конкурента."""

    name: str
    price: int | None = None
    source_shop: str
    source_url: str = ""
    category: str = ""
    color: str | None = None
    stems_count: int | None = None
    packaging: str | None = None
    rating: float | None = None
    in_our_catalog: bool = False


class CompetitorAnalysis(BaseModel):
    """Итог анализа конкурентов по категории."""

    category: str
    total_products: int
    unique_formats: list[str]
    missing_in_catalog: list[CompetitorProduct]
    popular_formats: list[dict[str, str | int]]  # {"format": str, "count": int}
    shops_analyzed: list[str]


# ─── Парсинг товаров из Flowwow (агрегатор) ───────────────────────


def _parse_flowwow_page(html: str, category: str) -> list[CompetitorProduct]:
    """Извлекаем товары из HTML-страницы Flowwow."""
    products: list[CompetitorProduct] = []
    # Ищем JSON-LD или карточки товаров
    ld_json_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    for block in ld_json_blocks:
        try:
            data = json.loads(block)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and data.get("@type") == "ItemList":
                items = data.get("itemListElement", [])
            elif isinstance(data, dict) and data.get("@type") == "Product":
                items = [data]
            else:
                continue

            for item in items:
                if isinstance(item, dict):
                    product_data = item.get("item", item)
                    name = product_data.get("name", "")
                    if not name:
                        continue
                    price = None
                    offers = product_data.get("offers", {})
                    if isinstance(offers, dict):
                        price_str = offers.get("price", offers.get("lowPrice"))
                        if price_str:
                            try:
                                price = int(float(str(price_str)))
                            except (ValueError, TypeError):
                                pass
                    url = product_data.get("url", "")
                    products.append(
                        CompetitorProduct(
                            name=name,
                            price=price,
                            source_shop="Flowwow",
                            source_url=url,
                            category=category,
                        )
                    )
        except (json.JSONDecodeError, KeyError):
            continue

    # Фолбэк: ищем карточки по HTML-паттернам
    if not products:
        card_pattern = re.findall(
            r'class="[^"]*(?:product|card|item)[^"]*"[^>]*>.*?'
            r'(?:title|alt|aria-label)=["\']([^"\']+)["\']',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        for name in card_pattern[:50]:
            name = name.strip()
            if len(name) > 3 and category.lower() in name.lower():
                products.append(
                    CompetitorProduct(
                        name=name,
                        source_shop="Flowwow",
                        category=category,
                    )
                )

    return products


def fetch_via_scrapling(
    category: str,
    max_pages: int = 3,
) -> list[CompetitorProduct]:
    """Парсинг Flowwow через Scrapling StealthyFetcher.

    Возвращает список CompetitorProduct или пустой список при ошибке.
    """
    from src.scraper import ScraplerEngine
    from src.scraper.adapters.flowwow import FlowwowAdapter

    # Включаем интерактивный режим: headless=False открывает видимый браузер,
    # disable_resources=False загружает картинки/скрипты,
    # interactive=True ставит поток на паузу, пока пользователь решает капчу
    engine = ScraplerEngine(headless=False, disable_resources=False, interactive=True)
    adapter = FlowwowAdapter()

    with tracer.span("competitors.scrapling", category=category) as span:
        scraped = engine.scrape_search(
            query=category, adapter=adapter, category=category, max_pages=max_pages
        )
        span.metadata["scrapled_count"] = len(scraped)

    # Конвертируем ScrapedProduct → CompetitorProduct
    products: list[CompetitorProduct] = []
    for s in scraped:
        products.append(
            CompetitorProduct(
                name=s.name,
                price=s.price,
                source_shop=s.source_shop or "flowwow.com",
                source_url=s.url,
                category=category,
            )
        )
    return products


def fetch_competitors_web(
    category: str,
    shops: list[str] | None = None,
    max_pages: int = 3,
) -> list[CompetitorProduct]:
    """Поиск товаров конкурентов.

    Стратегия:
    1. Scrapling StealthyFetcher → Flowwow (обход антиботов).
    2. Фолбэк: httpx + Yandex поиск (для остальных площадок).
    3. Если ничего не найдено — пустой список,
       пользователь переключится на ручной ввод или CSV.
    """
    import httpx

    if shops is None:
        shops = ["flowwow.com", "megaflowers.ru", "flor2u.ru", "buket.io"]

    all_products: list[CompetitorProduct] = []

    with tracer.span("competitors.fetch_web", category=category, shops_count=len(shops)) as span:
        # ── Стратегия 1: Scrapling (Flowwow) ──────────────────────
        if "flowwow.com" in shops:
            try:
                scrapling_products = fetch_via_scrapling(category, max_pages=max_pages)
                all_products.extend(scrapling_products)
            except Exception as e:
                with tracer.span("competitors.scrapling_error") as err:
                    err.metadata["error"] = str(e)
                # Фолбэк на httpx для Flowwow
                try:
                    with tracer.span("competitors.flowwow_httpx_fallback"):
                        slug = category.lower().replace(" ", "-")
                        headers = {
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/131.0.0.0 Safari/537.36"
                            ),
                            "Accept-Language": "ru-RU,ru;q=0.9",
                        }
                        for url in [
                            f"https://flowwow.com/flowers/{slug}/",
                            f"https://flowwow.com/search/?q={category}",
                        ]:
                            try:
                                with httpx.Client(
                                    headers=headers,
                                    follow_redirects=True,
                                    timeout=20.0,
                                ) as client:
                                    resp = client.get(url)
                                    if resp.status_code == 200:
                                        products = _parse_flowwow_page(resp.text, category)
                                        if products:
                                            all_products.extend(products)
                                            break
                            except httpx.HTTPError:
                                continue
                except Exception:
                    pass

        # ── Стратегия 2: httpx + Yandex (остальные площадки) ──────
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ru-RU,ru;q=0.9",
        }
        for shop in shops:
            if shop == "flowwow.com":
                continue
            try:
                with tracer.span("competitors.search_shop", shop=shop):
                    query = f"{category} купить"
                    search_url = f"https://yandex.ru/search/?text={query}+site%3A{shop}&lr=213"
                    try:
                        with httpx.Client(
                            headers=headers,
                            follow_redirects=True,
                            timeout=15.0,
                        ) as client:
                            resp = client.get(search_url)
                            if resp.status_code == 200:
                                titles = re.findall(
                                    r"<h2[^>]*>.*?<a[^>]*>(.*?)</a>.*?</h2>",
                                    resp.text,
                                    re.DOTALL,
                                )
                                if not titles:
                                    titles = re.findall(
                                        r'class="[^"]*(?:OrganicTitle|serp-item__title)[^"]*"'
                                        r"[^>]*>.*?<a[^>]*>(.*?)</a>",
                                        resp.text,
                                        re.DOTALL,
                                    )
                                for title_html in titles[:10]:
                                    clean = re.sub(r"<[^>]+>", "", title_html).strip()
                                    if not clean or len(clean) < 4:
                                        continue
                                    price = None
                                    pm = re.search(r"(\d[\d\s]*)\s*(?:руб|₽|р\.)", clean)
                                    if pm:
                                        try:
                                            price = int(pm.group(1).replace(" ", ""))
                                        except ValueError:
                                            pass
                                    all_products.append(
                                        CompetitorProduct(
                                            name=clean,
                                            price=price,
                                            source_shop=shop,
                                            category=category,
                                        )
                                    )
                    except httpx.HTTPError:
                        pass
            except Exception as e:
                with tracer.span("competitors.error", shop=shop) as err_span:
                    err_span.metadata["error"] = str(e)
                continue

        span.metadata["total_found"] = len(all_products)

    return all_products


# ─── Импорт из CSV ────────────────────────────────────────────────


def import_competitors_csv(file_path: str, category: str) -> list[CompetitorProduct]:
    """Импорт данных конкурентов из CSV-файла.

    Ожидаемый формат: название;цена;магазин;ссылка
    """
    products: list[CompetitorProduct] = []
    with tracer.span("competitors.import_csv", file=file_path) as span:
        with open(file_path, encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            next(reader, None)  # Пропускаем заголовок
            for row in reader:
                if len(row) < 2:
                    continue
                name = row[0].strip()
                if not name:
                    continue

                price = None
                if len(row) >= 2 and row[1].strip():
                    try:
                        price = int(float(row[1].strip()))
                    except ValueError:
                        pass

                shop = row[2].strip() if len(row) >= 3 else "Неизвестный магазин"
                url = row[3].strip() if len(row) >= 4 else ""

                products.append(
                    CompetitorProduct(
                        name=name,
                        price=price,
                        source_shop=shop,
                        source_url=url,
                        category=category,
                    )
                )
        span.metadata["imported"] = len(products)
    return products


# ─── Ручной ввод ──────────────────────────────────────────────────


def parse_manual_input(text: str, category: str) -> list[CompetitorProduct]:
    """Парсинг ручного ввода товаров конкурентов.

    Каждая строка — одна позиция. Формат: «название» или «название — цена».
    """
    products: list[CompetitorProduct] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        # Пытаемся извлечь цену через разделитель
        parts = re.split(r"\s*[—–-]\s*", line, maxsplit=1)
        name = parts[0].strip()
        price = None
        if len(parts) == 2:
            price_match = re.search(r"(\d+)", parts[1])
            if price_match:
                price = int(price_match.group(1))

        if name:
            products.append(
                CompetitorProduct(
                    name=name,
                    price=price,
                    source_shop="Ручной ввод",
                    category=category,
                )
            )
    return products


# ─── Обогащение признаками ────────────────────────────────────────


def enrich_product_features(product: CompetitorProduct) -> CompetitorProduct:
    """Извлекает цвет, количество стеблей, упаковку из названия товара."""
    name_lower = product.name.lower()

    # Количество стеблей
    stems_match = re.search(r"\b(\d+)\s*(?:шт|штук|стебл)", name_lower)
    if not stems_match:
        stems_match = re.search(r"\b(\d+)\b", name_lower)
    if stems_match:
        num = int(stems_match.group(1))
        if 1 <= num <= 500:  # Разумный диапазон для количества цветов
            product.stems_count = num

    # Цвет
    color_map = {
        "бел": "белый",
        "розов": "розовый",
        "красн": "красный",
        "желт": "желтый",
        "син": "синий",
        "фиолетов": "фиолетовый",
        "сиренев": "сиреневый",
        "малинов": "малиновый",
        "персиков": "персиковый",
        "кремов": "кремовый",
        "голуб": "голубой",
        "оранжев": "оранжевый",
        "бордов": "бордовый",
        "микс": "микс",
    }
    for prefix, full_color in color_map.items():
        if prefix in name_lower:
            product.color = full_color
            break

    # Упаковка
    if "коробк" in name_lower or "шляпн" in name_lower:
        product.packaging = "коробка"
    elif "корзин" in name_lower:
        product.packaging = "корзина"
    elif "крафт" in name_lower:
        product.packaging = "крафт"
    elif "монобукет" in name_lower:
        product.packaging = "монобукет"

    return product


# ─── Аналитика ────────────────────────────────────────────────────


def analyze_competitors(products: list[CompetitorProduct], category: str) -> CompetitorAnalysis:
    """Формирует аналитический отчёт по собранным товарам конкурентов."""
    with tracer.span(
        "competitors.analyze", category=category, products_count=len(products)
    ) as span:
        # Обогащаем каждый товар признаками
        enriched = [enrich_product_features(p) for p in products]

        # Определяем уникальные форматы
        formats: dict[str, int] = {}
        for p in enriched:
            fmt_parts = []
            if p.stems_count:
                fmt_parts.append(f"{p.stems_count} шт")
            if p.color:
                fmt_parts.append(p.color)
            if p.packaging:
                fmt_parts.append(p.packaging)
            fmt = " / ".join(fmt_parts) if fmt_parts else "без уточнения"
            formats[fmt] = formats.get(fmt, 0) + 1

        # Сортируем форматы по популярности
        sorted_formats = sorted(formats.items(), key=lambda x: x[1], reverse=True)
        popular: list[dict[str, str | int]] = [
            {"format": str(f), "count": int(c)} for f, c in sorted_formats
        ]

        # Уникальные магазины
        shops = list({p.source_shop for p in enriched})

        analysis = CompetitorAnalysis(
            category=category,
            total_products=len(enriched),
            unique_formats=[f for f, _ in sorted_formats],
            missing_in_catalog=enriched,  # Пока все помечаем как отсутствующие
            popular_formats=popular,
            shops_analyzed=shops,
        )

        span.metadata["unique_formats"] = len(sorted_formats)
        span.metadata["shops"] = shops

    return analysis
