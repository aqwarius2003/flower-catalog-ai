"""Ядро скрапера: движок + модель ScrapedProduct."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from scrapling.fetchers import StealthyFetcher

if TYPE_CHECKING:
    from src.scraper.adapters.base import ShopAdapter

logger = logging.getLogger(__name__)


@dataclass
class ScrapedProduct:
    """Товар, извлечённый со страницы конкурента."""

    name: str
    price: int | None = None
    url: str = ""
    image_url: str = ""
    source_shop: str = ""
    category: str = ""
    raw_html: str = ""
    rating: float | None = None


class ScraplerEngine:
    """Движок парсинга: получает страницу через StealthyFetcher,
    передаёт HTML адаптеру для извлечения товаров.

    Пример::

        from src.scraper import ScraplerEngine
        from src.scraper.adapters.flowwow import FlowwowAdapter

        engine = ScraplerEngine()
        products = engine.scrape(
            url="https://flowwow.com/search/?q=гипсофила",
            adapter=FlowwowAdapter(),
            category="Гипсофила",
        )
    """

    def __init__(
        self,
        headless: bool = True,
        disable_resources: bool = True,
        timeout: int = 120_000,
        network_idle: bool = True,
        interactive: bool = False,
    ):
        self.headless = headless
        self.disable_resources = disable_resources
        self.timeout = timeout
        self.network_idle = network_idle
        self.interactive = interactive

    def scrape(
        self,
        url: str,
        adapter: ShopAdapter,
        category: str = "",
    ) -> list[ScrapedProduct]:
        """Загружает страницу через StealthyFetcher и извлекает товары."""

        logger.info("Загрузка %s через StealthyFetcher...", url)

        def handle_captcha(page):
            """Автоматизация Playwright: ждем решения капчи, если она есть."""
            title = page.title().lower()
            if "captcha" in title or "servicepipe" in page.content().lower():
                logger.warning(
                    "🚨 ОБНАРУЖЕНА КАПЧА! Пожалуйста, решите её в открывшемся окне браузера."
                )
                try:
                    # Ждем 60 секунд, пока пользователь решает капчу,
                    # признак успеха - появление любого контента на странице
                    page.wait_for_selector(
                        '.ProductCard, [data-testid="product-card"], .product-card, .catalog-item, main, #main',
                        timeout=60_000,
                    )
                    logger.info("✅ Капча решена!")

                    # Если после капчи нас перекинуло на главную страницу (например /en-ru/)
                    if "search" not in page.url and url != page.url:
                        logger.info("Сайт перекинул на главную. Возвращаемся на поиск...")
                        page.goto(url)
                        page.wait_for_selector(
                            '.ProductCard, [data-testid="product-card"], .product-card, .catalog-item',
                            timeout=15_000,
                        )

                    logger.info("✅ Товары загружены!")
                except Exception as e:
                    logger.error("❌ Истекло время ожидания решения капчи: %s", e)

        try:
            page = StealthyFetcher.fetch(
                url,
                headless=self.headless,
                disable_resources=self.disable_resources,
                timeout=self.timeout,
                network_idle=self.network_idle,
                page_action=handle_captcha if self.interactive else None,
                extra_flags=["--remote-debugging-port=9222"],
            )
        except Exception as e:
            logger.error("Ошибка StealthyFetcher: %s", e)
            return []

        if page is None or page.status != 200:
            status = page.status if page else "None"
            logger.warning("Страница вернула статус %s: %s", status, url)
            return []

        products = adapter.extract(page, category=category, source_url=url)
        logger.info("Извлечено %d товаров с %s", len(products), url)
        return products

    def scrape_search(
        self,
        query: str,
        adapter: ShopAdapter,
        category: str = "",
        max_pages: int = 3,
    ) -> list[ScrapedProduct]:
        """Формирует URL поиска через адаптер и парсит результаты.

        В интерактивном режиме использует поведенческий обход: заходит на главную,
        вбивает текст как человек и нажимает Enter.
        """
        if not self.interactive:
            # Обычный режим (без видимого браузера)
            url = adapter.build_search_url(query)
            return self.scrape(url=url, adapter=adapter, category=category)

        # ── Интерактивный "человеческий" режим ──
        logger.info("Запуск 'человеческого' поиска для: %s", query)

        # Берем корень сайта (главную страницу)
        base_url = "https://flowwow.com/ru/moscow/"

        def human_behavior(page):
            # 1. Ждем загрузки реального сайта (ухода со страницы ServicePipe)
            logger.info("⏳ Ожидание загрузки интерфейса Flowwow (до 60 сек на решение капчи)...")
            try:
                # Ждем, пока страница перестанет быть "капчей"
                page.wait_for_function(
                    '() => !document.title.toLowerCase().includes("captcha") && !document.title.toLowerCase().includes("ой!")',
                    timeout=60_000,
                )
                page.wait_for_load_state("domcontentloaded")
                logger.info("✅ Интерфейс загружен!")
            except Exception:
                logger.error(
                    "❌ Сайт так и не загрузился за 60 секунд (капча не пройдена). Прерываем."
                )
                return

            # Ждем пару секунд для надежности (React hydration)
            page.wait_for_timeout(2000)

            # 2. Уничтожаем модальные окна через JS (чтобы 100% не перехватили клик)
            logger.info("🧹 Удаляем возможные всплывающие окна (CustomPopupModal)...")
            try:
                page.evaluate("""() => {
                    document.querySelectorAll('.neo-modal, [id*="Popup"], [class*="Modal"]').forEach(el => el.remove());
                }""")
                page.wait_for_timeout(500)
            except Exception:
                pass

            # 3. Ищем строку поиска
            logger.info("⌨️ Вводим запрос '%s' с клавиатуры...", query)
            try:
                # Универсальные локаторы для поиска инпута
                inp = page.locator(
                    'input[type="search"], input[placeholder*="Поиск"], input[placeholder*="поиск"]'
                ).first

                # Обязательно ждем появления инпута (React может рендерить его с задержкой)
                # Flowwow имеет "прыгающую" строку поиска: при клике открывается модалка или
                # инпут уезжает наверх. Старый элемент может исчезнуть.
                # 1. Сначала просто кликаем, чтобы активировать анимацию
                try:
                    inp.click(timeout=3000, force=True)
                except Exception:
                    # Если инпут не кликабелен, ищем лупу
                    page.locator("button svg, .search-icon").first.click(timeout=3000, force=True)

                # 2. Ждем, пока "прыгающая" полоса успокоится (анимация занимает время)
                page.wait_for_timeout(1500)

                # 3. Ищем настоящий, боевой инпут, который появился на экране (обычно он последний/единственный видимый)
                real_inp = (
                    page.locator(
                        'input[type="search"], input[placeholder*="Поиск"], input[placeholder*="поиск"]'
                    )
                    .locator("visible=true")
                    .last
                )

                # 4. Принудительно кликаем уже в него, чтобы 100% поставить фокус (и курсор замигал)
                real_inp.click(timeout=3000, force=True)
                page.wait_for_timeout(500)

                # Выделяем старый текст (если он был) и сразу печатаем новый поверх него.
                # Это безопаснее, чем Backspace, который может закрыть модалку, если поле было пустым.
                page.keyboard.press("Control+A")
                page.keyboard.press("Meta+A")

                # 6. Вводим текст честно по буквам (иначе React у Flowwow не поймет, что мы что-то ввели)
                page.keyboard.type(query, delay=100)
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")

                logger.info("⏳ Ждем результатов поиска...")
                page.wait_for_selector(
                    '.ProductCard, [data-testid="product-card"], .product-card, .catalog-item',
                    timeout=15_000,
                )

                # 3.5 Применяем сортировку "От новых к старым"
                logger.info("🔄 Включаем сортировку 'От новых к старым'...")
                try:
                    # Ищем выпадающий список сортировки (может называться по-разному в зависимости от того, что было выбрано ранее)
                    sort_btn = (
                        page.locator(
                            'text="По соответствию", text="Популярные", text="От новых к старым", text="Сначала дешевле", text="Сначала дороже"'
                        )
                        .locator("visible=true")
                        .first
                    )

                    if sort_btn.is_visible(timeout=5000):
                        sort_btn.click(force=True)

                        # Явно ЖДЕМ (ищем), пока появится пункт меню "От новых к старым"
                        page.wait_for_selector(
                            'text="От новых к старым"', state="visible", timeout=3000
                        )

                        # Нажимаем на него
                        new_to_old = (
                            page.locator('text="От новых к старым"').locator("visible=true").first
                        )
                        new_to_old.click()
                        page.wait_for_timeout(500)

                        # Нажимаем кнопку "Показать" внизу менюшки
                        apply_btn = (
                            page.locator('button:has-text("Показать")')
                            .locator("visible=true")
                            .first
                        )
                        if apply_btn.is_visible(timeout=1000):
                            apply_btn.click()

                        # Ждем пока товары обновятся после сортировки (ждем остановки сети)
                        page.wait_for_load_state("networkidle", timeout=10000)
                        page.wait_for_timeout(2000)
                        logger.info("✅ Сортировка успешно применена!")
                    else:
                        logger.warning(
                            "Кнопка сортировки не найдена на экране, продолжаем со стандартной."
                        )
                except Exception as e:
                    logger.warning(
                        "Не удалось применить сортировку (возможно уже применена): %s", e
                    )

                # 4. Собираем пагинацию (кликаем "Показать еще")
                logger.info("⏳ Подгружаем дополнительные товары (пагинация: %d раз)...", max_pages)
                for page_num in range(1, max_pages + 1):  # Кликаем заданное число раз (глубина)
                    # Скроллим вниз, чтобы кнопка появилась
                    page.mouse.wheel(0, 5000)
                    page.wait_for_timeout(1000)

                    try:
                        # Ищем кнопку "Показать еще"
                        more_btn = page.locator(
                            'button:has-text("Показать еще"), div:has-text("Показать еще"), a:has-text("Показать еще")'
                        ).last
                        if more_btn.is_visible(timeout=2000):
                            logger.info(
                                "Кликаем 'Показать еще' (подгрузка %d из %d)...",
                                page_num,
                                max_pages,
                            )
                            # Считаем сколько карточек сейчас
                            current_count = page.locator(
                                '.ProductCard, [data-testid="product-card"], .product-card'
                            ).count()
                            more_btn.click()

                            # Ждем, пока количество карточек не увеличится (lazy load)
                            try:
                                page.wait_for_function(
                                    f'document.querySelectorAll(".ProductCard, [data-testid=\\"product-card\\"], .product-card").length > {current_count}',
                                    timeout=10000,
                                )
                                logger.info("✅ Новые товары подгрузились.")
                            except Exception:
                                logger.warning("Новые товары не появились за 10 сек.")
                        else:
                            logger.info("Кнопки 'Показать еще' нет, конец списка.")
                            break
                    except Exception as e:
                        logger.warning("Не удалось подгрузить больше товаров: %s", e)
                        break

                logger.info("✅ Все товары загружены!")
            except Exception as e:
                logger.error("❌ Ошибка поведенческого обхода: %s", e)

        try:
            page = StealthyFetcher.fetch(
                base_url,
                headless=False,
                disable_resources=False,
                timeout=self.timeout,
                network_idle=self.network_idle,
                page_action=human_behavior,
                extra_flags=["--remote-debugging-port=9222"],
            )
        except Exception as e:
            logger.error("Ошибка StealthyFetcher: %s", e)
            return []

        if page is None or page.status != 200:
            return []

        products = adapter.extract(page, category=category, source_url=page.url)
        logger.info("Извлечено %d товаров", len(products))
        return products
