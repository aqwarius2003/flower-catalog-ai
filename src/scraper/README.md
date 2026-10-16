# Scrapling Scraper — подключаемый модуль парсинга

Модуль для парсинга товаров с цветочных маркетплейсов.
Использует [Scrapling](https://github.com/D4Vinci/Scrapling)
(`StealthyFetcher`) для обхода антибот-защит (Cloudflare, WAF).

## Быстрый старт

```python
from src.scraper import ScraplerEngine
from src.scraper.adapters.flowwow import FlowwowAdapter

engine = ScraplerEngine()
products = engine.scrape_search(
    query="Гипсофила",
    adapter=FlowwowAdapter(),
    category="Гипсофила",
)

for p in products:
    print(f"{p.name} — {p.price} руб. ({p.url})")
```

## Структура

```
src/scraper/
├── __init__.py          # Экспорт ScraplerEngine, ScrapedProduct, ShopAdapter
├── core.py              # Движок (StealthyFetcher) + модель ScrapedProduct
├── adapters/
│   ├── __init__.py
│   ├── base.py          # Абстрактный ShopAdapter (интерфейс)
│   └── flowwow.py       # Адаптер Flowwow (JSON-LD + CSS + alt fallback)
└── README.md            # Этот файл
```

## Как добавить новый магазин

1. Создайте файл `adapters/myshop.py`
2. Унаследуйте `ShopAdapter`
3. Реализуйте два метода:

```python
from src.scraper.adapters.base import ShopAdapter
from src.scraper.core import ScrapedProduct


class MyShopAdapter(ShopAdapter):
    shop_name = "myshop.ru"

    def build_search_url(self, query: str) -> str:
        return f"https://myshop.ru/search?q={query}"

    def extract(self, page, category="", source_url="") -> list[ScrapedProduct]:
        products = []
        for card in page.css(".product-card"):
            name = card.css("h3::text").get("")
            price_text = card.css(".price::text").get("0")
            price = int("".join(c for c in price_text if c.isdigit()) or "0")
            products.append(
                ScrapedProduct(
                    name=name,
                    price=price or None,
                    url=card.css("a::attr(href)").get(""),
                    image_url=card.css("img::attr(src)").get(""),
                    source_shop=self.shop_name,
                    category=category,
                )
            )
        return products
```

## Перенос в другой проект

1. Скопируйте папку `src/scraper/` в свой проект
2. Установите зависимость:
   ```bash
   pip install scrapling
   # или
   uv add scrapling
   ```
3. При первом запуске `StealthyFetcher` автоматически скачает Camoufox
4. Импортируйте и используйте:
   ```python
   from your_project.scraper import ScraplerEngine
   ```

## Настройки движка

```python
engine = ScraplerEngine(
    headless=True,  # Скрытый браузер (по умолчанию True)
    disable_resources=True,  # Не грузить картинки/шрифты (ускорение)
    timeout=30_000,  # Таймаут в мс
    network_idle=True,  # Ждать завершения сетевых запросов
)
```

## Зависимости

- `scrapling>=0.4` — ядро (тянет `lxml`, `cssselect`, `orjson`)
- Camoufox — скачивается автоматически при первом запуске `StealthyFetcher`
