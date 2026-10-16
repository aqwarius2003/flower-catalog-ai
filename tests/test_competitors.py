"""Тесты для модуля анализа конкурентов."""

from src.competitors import (
    CompetitorProduct,
    analyze_competitors,
    enrich_product_features,
    parse_manual_input,
)


def test_parse_manual_input():
    text = """Гипсофила розовая 15 шт — 2500
Монобукет гипсофилы белой
Букет гипсофилы в коробке — 3200
"""
    products = parse_manual_input(text, "Гипсофила")
    assert len(products) == 3
    assert products[0].name == "Гипсофила розовая 15 шт"
    assert products[0].price == 2500
    assert products[1].name == "Монобукет гипсофилы белой"
    assert products[1].price is None
    assert products[2].price == 3200


def test_enrich_product_features():
    p = CompetitorProduct(
        name="Гипсофила розовая 15 шт в коробке",
        source_shop="Test",
        category="Гипсофила",
    )
    enriched = enrich_product_features(p)
    assert enriched.color == "розовый"
    assert enriched.stems_count == 15
    assert enriched.packaging == "коробка"


def test_enrich_product_no_features():
    p = CompetitorProduct(
        name="Букет гипсофилы",
        source_shop="Test",
        category="Гипсофила",
    )
    enriched = enrich_product_features(p)
    assert enriched.color is None
    assert enriched.stems_count is None
    assert enriched.packaging is None


def test_enrich_monobouquet():
    p = CompetitorProduct(
        name="Монобукет белой гипсофилы",
        source_shop="Test",
        category="Гипсофила",
    )
    enriched = enrich_product_features(p)
    assert enriched.color == "белый"
    assert enriched.packaging == "монобукет"


def test_analyze_competitors():
    products = [
        CompetitorProduct(
            name="Гипсофила розовая 15 шт", source_shop="Shop A", category="Гипсофила"
        ),
        CompetitorProduct(name="Гипсофила белая 15 шт", source_shop="Shop A", category="Гипсофила"),
        CompetitorProduct(
            name="Гипсофила розовая 25 шт", source_shop="Shop B", category="Гипсофила"
        ),
        CompetitorProduct(name="Монобукет гипсофилы", source_shop="Shop B", category="Гипсофила"),
        CompetitorProduct(name="Букет гипсофилы", source_shop="Shop C", category="Гипсофила"),
    ]
    analysis = analyze_competitors(products, "Гипсофила")
    assert analysis.total_products == 5
    assert len(analysis.shops_analyzed) == 3
    assert len(analysis.popular_formats) > 0
    assert analysis.category == "Гипсофила"
