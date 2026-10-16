import os
import sqlite3

import pandas as pd
import streamlit as st

from src.db import DB_PATH, init_db
from src.models import WordstatPhrase
from src.trace import tracer
from src.wordstat import WordstatClient, parse_csv

st.set_page_config(page_title="Flower Catalog AI", layout="wide")


@st.cache_resource
def init_app_db():
    init_db(DB_PATH)
    return True


init_app_db()


def get_connection():
    # Use standard context manager from db.py or provide a cached one
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def main():
    st.sidebar.title("Flower Catalog AI")

    # Navigation — 6 экранов по заданию
    screens = [
        "1. Параметры сбора",
        "2. Сырой Wordstat",
        "3. Анализ конкурентов",
        "4. Очередь карточек",
        "5. Референсы и обработка",
        "6. Результат и структура",
    ]

    # State
    if "current_screen" not in st.session_state:
        st.session_state.current_screen = screens[0]
    if "category" not in st.session_state:
        st.session_state.category = ""

    def set_screen(screen_name):
        st.session_state.current_screen = screen_name

    selected_screen = st.sidebar.radio(
        "Пайплайн категории", screens, index=screens.index(st.session_state.current_screen)
    )
    if selected_screen != st.session_state.current_screen:
        st.session_state.current_screen = selected_screen
        st.rerun()

    # ── Экран 1: Параметры сбора ──────────────────────────────────
    if st.session_state.current_screen == screens[0]:
        st.title("Параметры сбора семантики")

        col1, col2 = st.columns(2)
        with col1:
            category = st.text_input(
                "Категория цветов", key="category", placeholder="Например: Розы"
            )
            region = st.selectbox(
                "Регион", ["Россия", "Москва и область", "Санкт-Петербург и область"]
            )
            threshold_type = st.radio(
                "Порог частотности", ["Только супер-популярные (≥ 1 000)", "Свой порог"]
            )
            if threshold_type == "Свой порог":
                threshold = st.number_input("Значение", value=300, min_value=1)
            else:
                threshold = 1000

        with col2:
            source = st.radio("Источник спроса", ["Wordstat API", "Импорт CSV"])
            csv_file = None
            if source == "Импорт CSV":
                csv_file = st.file_uploader("Перетащите CSV-выгрузку Wordstat", type=["csv"])

        st.info(
            "Без частотности пайплайн не стартует: карточки создаются только из реального поискового спроса."
        )

        st.subheader("Как работает лавина запросов")
        st.markdown("""
        * **Шаг 1** Сиды: гипсофила, букет гипсофилы, монобукет
        * **Шаг 2** GetTop по каждому сиду: results + associations
        * **Шаг 3** В очередь — только фразы выше порога
        * **Шаг 4** Стоп: 200 фраз или исчерпана жирная голова
        """)

        if st.button("Собрать семантику", type="primary"):
            with tracer.span("ui.collect_semantics"):
                # Save to session_state
                st.session_state.region = region
                st.session_state.threshold = threshold
                st.session_state.source = source

                # Mock processing or real processing
                if source == "Импорт CSV" and csv_file is not None:
                    # Save uploaded file to temp
                    os.makedirs("data", exist_ok=True)
                    temp_path = os.path.join("data", csv_file.name)
                    with open(temp_path, "wb") as f:
                        f.write(csv_file.getbuffer())
                    st.session_state.phrases = parse_csv(temp_path)
                    st.success("Данные успешно импортированы!")
                elif source == "Wordstat API":
                    with st.spinner("Сбор семантики через API..."):
                        client = WordstatClient()
                        seeds = [category.lower(), f"букет {category.lower()}", "монобукет"]
                        try:
                            raw_phrases = client.avalanche_queries(seeds)
                            # Фильтруем по порогу
                            filtered_phrases = [p for p in raw_phrases if p.count >= threshold]
                            st.session_state.phrases = filtered_phrases
                            st.success(
                                f"Загружено {len(filtered_phrases)} фраз (после фильтрации)!"
                            )
                        except Exception as e:
                            st.error(f"Ошибка при работе с API: {e}")
                            st.session_state.phrases = []

                set_screen(screens[1])

    # ── Экран 2: Сырой Wordstat ───────────────────────────────────
    elif st.session_state.current_screen == screens[1]:
        st.title("Сырой Wordstat")
        if "phrases" not in st.session_state:
            st.warning("Нет данных. Вернитесь на первый шаг.")
        else:
            phrases: list[WordstatPhrase] = st.session_state.phrases

            total = len(phrases)
            commercial = sum(1 for p in phrases if p.commercial)
            info = total - commercial

            st.markdown(
                f"**Все**: {total} | **Коммерческие**: {commercial} | **Инфо-запросы**: {info}"
            )

            if phrases:
                df = pd.DataFrame([p.model_dump() for p in phrases])
                st.dataframe(df)

            col_w1, col_w2 = st.columns(2)
            with col_w1:
                if st.button("Анализ конкурентов →", type="secondary"):
                    set_screen(screens[2])
            with col_w2:
                if st.button("Кластеризовать в карточки →", type="primary"):
                    from src.clusterer import build_clusters

                    st.session_state.clusters = build_clusters(phrases, st.session_state.category)
                    set_screen(screens[3])

    # ── Экран 3: Анализ конкурентов ───────────────────────────────
    elif st.session_state.current_screen == screens[2]:
        from src.competitors import (
            analyze_competitors,
            fetch_competitors_web,
            import_competitors_csv,
            parse_manual_input,
        )

        st.title("Анализ конкурентов")

        category = st.session_state.category
        if category:
            st.markdown(f"**Категория:** {category}")

        st.markdown("""
        Изучаем ассортимент магазинов цветов, маркетплейсов и агрегаторов:
        - определяем популярные форматы товаров;
        - находим позиции, которые имеют спрос и отсутствуют в нашем каталоге.
        """)

        # Источник данных конкурентов
        comp_source = st.radio(
            "Источник данных о конкурентах",
            ["Поиск в интернете", "Импорт CSV", "Ручной ввод"],
            horizontal=True,
        )

        if comp_source == "Поиск в интернете":
            st.markdown("Поиск товаров на популярных цветочных площадках.")

            default_shops = "flowwow.com\nmegaflowers.ru\nflor2u.ru\nbuket.io"
            shops_text = st.text_area(
                "Площадки для анализа (по одной на строку)",
                value=default_shops,
                height=120,
            )
            shops = [s.strip() for s in shops_text.strip().splitlines() if s.strip()]
            # Блок с настройками и кнопкой
            col1, col2 = st.columns([1, 2])
            with col1:
                max_pages = st.number_input(
                    "Глубина пагинации",
                    min_value=1,
                    max_value=20,
                    value=3,
                    help="Сколько раз нажимать кнопку 'Показать еще'",
                )
            with col2:
                st.write("")  # отступ
                st.write("")  # отступ
                search_clicked = st.button("Найти товары конкурентов", type="primary")

            if search_clicked:
                with st.spinner(
                    f"Поиск «{category}» на {len(shops)} площадках (глубина: {max_pages})..."
                ):
                    products = fetch_competitors_web(category, shops, max_pages=max_pages)
                    st.session_state.competitor_products = products
                    if products:
                        st.success(f"Найдено {len(products)} товаров конкурентов!")
                    else:
                        st.warning(
                            "Автопоиск не дал результатов (площадки блокируют ботов). Воспользуйтесь ручным вводом или CSV."
                        )

        elif comp_source == "Импорт CSV":
            st.markdown("Формат CSV: `название;цена;магазин;ссылка`")
            comp_csv = st.file_uploader(
                "CSV с данными конкурентов",
                type=["csv"],
                key="comp_csv",
            )
            if comp_csv is not None:
                os.makedirs("data", exist_ok=True)
                path = os.path.join("data", f"competitors_{comp_csv.name}")
                with open(path, "wb") as f:
                    f.write(comp_csv.getbuffer())
                products = import_competitors_csv(path, category)
                st.session_state.competitor_products = products
                st.success(f"Импортировано {len(products)} товаров!")

        elif comp_source == "Ручной ввод":
            st.markdown(
                "Введите позиции конкурентов (каждая на новой строке). Формат: `название` или `название — цена`"
            )
            manual_text = st.text_area(
                "Товары конкурентов",
                placeholder=(
                    "Гипсофила розовая 15 шт — 2500\n"
                    "Монобукет гипсофилы белой\n"
                    "Букет гипсофилы в коробке — 3200\n"
                    "Гипсофила 25 шт микс — 4500"
                ),
                height=200,
                key="manual_competitors",
            )
            if st.button("Добавить позиции", type="primary") and manual_text.strip():
                products = parse_manual_input(manual_text, category)
                existing = st.session_state.get("competitor_products", [])
                st.session_state.competitor_products = existing + products
                st.success(f"Добавлено {len(products)} позиций!")

        # ── Результаты анализа ────────────────────────────────────
        if "competitor_products" in st.session_state and st.session_state.competitor_products:
            products = st.session_state.competitor_products
            analysis = analyze_competitors(products, category)
            st.session_state.competitor_analysis = analysis

            st.divider()
            st.subheader("Результаты анализа конкурентов")

            # Метрики
            m1, m2, m3 = st.columns(3)
            m1.metric("Товаров найдено", analysis.total_products)
            m2.metric("Уникальных форматов", len(analysis.unique_formats))
            m3.metric("Площадок", len(analysis.shops_analyzed))

            # Популярные форматы
            st.subheader("Популярные форматы товаров")
            if analysis.popular_formats:
                fmt_df = pd.DataFrame(analysis.popular_formats)
                fmt_df.columns = ["Формат", "Количество"]
                st.dataframe(fmt_df, use_container_width=True, hide_index=True)

            # Таблица товаров
            st.subheader("Найденные товары конкурентов")
            products_data = []
            for p in products:
                products_data.append(
                    {
                        "Название": p.name,
                        "Цена": p.price,
                        "Рейтинг": getattr(p, "rating", None),
                        "Магазин": p.source_shop,
                        "Цвет": p.color,
                        "Кол-во": p.stems_count,
                        "Упаковка": p.packaging,
                    }
                )
            st.dataframe(
                pd.DataFrame(products_data),
                hide_index=True,
            )

            # Площадки
            st.subheader("Проанализированные площадки")
            st.write(", ".join(analysis.shops_analyzed))

        st.divider()
        if st.button("Кластеризовать в карточки →", type="primary"):
            if "phrases" in st.session_state:
                from src.clusterer import build_clusters

                st.session_state.clusters = build_clusters(st.session_state.phrases, category)
            set_screen(screens[3])

    # ── Экран 4: Очередь карточек ─────────────────────────────────
    elif st.session_state.current_screen == screens[3]:
        st.title("Очередь карточек")

        if "clusters" not in st.session_state:
            st.warning("Нет данных кластеров. Вернитесь на первый шаг и соберите данные.")
        else:
            clusters = st.session_state.clusters
            head = [c for c in clusters if c.tier == "head"]
            strong = [c for c in clusters if c.tier == "strong"]
            weak = [c for c in clusters if c.tier == "weak"]

            # Показываем подсказки из анализа конкурентов, если есть
            if "competitor_analysis" in st.session_state:
                analysis = st.session_state.competitor_analysis
                with st.expander("💡 Подсказки из анализа конкурентов", expanded=False):
                    st.markdown(
                        f"У конкурентов найдено **{analysis.total_products}** товаров в категории «{analysis.category}»."
                    )
                    if analysis.popular_formats:
                        st.markdown("**Самые популярные форматы у конкурентов:**")
                        for fmt in analysis.popular_formats[:5]:
                            st.markdown(f"- {fmt['format']} ({fmt['count']} шт)")

            st.info(
                f"Сформировано кластеров: {len(clusters)} (Head: {len(head)}, Strong: {len(strong)}, Weak: {len(weak)})"
            )

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Must-have (Head)")
                if not head:
                    st.write("Нет карточек этого уровня.")
                for c in head:
                    st.checkbox(
                        f"{c.name} (Max: {c.freq_max}, Score: {c.score})",
                        value=True,
                        key=c.cluster_id,
                    )

            with col2:
                st.subheader("Сильный корпус (Strong)")
                if not strong:
                    st.write("Нет карточек этого уровня.")
                for c in strong:
                    st.checkbox(
                        f"{c.name} (Max: {c.freq_max}, Score: {c.score})",
                        value=False,
                        key=c.cluster_id,
                    )

            # Слабый хвост — свёрнутый
            if weak:
                with st.expander(f"Слабый хвост ({len(weak)} позиций)"):
                    for c in weak:
                        st.checkbox(
                            f"{c.name} (Max: {c.freq_max}, Score: {c.score})",
                            value=False,
                            key=c.cluster_id,
                        )

            if st.button("Найти референсы", type="primary"):
                set_screen(screens[4])

    # ── Экран 5: Референсы и обработка ────────────────────────────
    elif st.session_state.current_screen == screens[4]:
        st.title("Референсы и обработка")
        st.info("Макет референсов")

        st.subheader("Параметры обработки")
        st.checkbox("Удалить фон (birefnet-general)", value=True)
        st.checkbox("Отцентрировать букет", value=True)
        st.checkbox("Кадрировать до 75-80% высоты", value=True)
        st.checkbox("Контактная тень", value=True)
        st.checkbox("Студийный фон (#F2F2F2)", value=True)

        if st.button("Запустить обработку", type="primary"):
            set_screen(screens[5])

    # ── Экран 6: Результат и структура ────────────────────────────
    elif st.session_state.current_screen == screens[5]:
        st.title("Результат и структура")
        st.success("Готово!")
        st.markdown("### Карточек готово: 4 из 4")
        st.code("""
        catalog/
          gipsofila/
            monobuket/
              main.webp
              refs.json
            15_white/
              main.webp
        """)


if __name__ == "__main__":
    main()
