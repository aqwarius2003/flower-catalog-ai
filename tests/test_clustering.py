from src.clusterer import (
    calculate_commercial_share,
    calculate_freq_sum_and_max,
    carry_over_decision,
    generate_cluster_id,
)
from src.models import WordstatPhrase


def test_cluster_id_deterministic():
    # 1. Порядок слов
    assert generate_cluster_id(15, "розовый яркий", "крафт") == generate_cluster_id(
        15, "яркий розовый", "крафт"
    )

    # 2. Регистр и пробелы
    assert generate_cluster_id(None, " Розовый ", "КРАФТ  ") == generate_cluster_id(
        None, "розовый", "крафт"
    )

    # 3. Отсутствие признака
    assert generate_cluster_id(15, None, None) == "s15|cNONE|pNONE"
    assert generate_cluster_id(None, None, None) == "sNONE|cNONE|pNONE"


def test_carry_over_decision():
    old_decisions = {"s15|розовый|pNONE": "approved", "s25|белый|pNONE": "rejected"}

    # 1. cluster_id не изменился, фразы те же
    decision, warning = carry_over_decision(
        "s15|розовый|pNONE", old_decisions, {"a", "b"}, {"a", "b"}
    )
    assert decision == "approved"
    assert warning is False

    # 2. cluster_id не изменился, фразы изменились
    decision, warning = carry_over_decision(
        "s15|розовый|pNONE", old_decisions, {"a", "b"}, {"a", "c"}
    )
    assert decision == "approved"
    assert warning is True

    # 3. cluster_id изменился (нет в старых)
    decision, warning = carry_over_decision("s11|розовый|pNONE", old_decisions, {"a"}, {"a"})
    assert decision == "pending"
    assert warning is False


def test_ambiguous_and_category_generic_handling():
    phrases = [
        WordstatPhrase(
            phrase="купить 15 роз",
            count=100,
            kind="result",
            commercial=True,
            source="api",
            link_status="sku_specific",
        ),
        WordstatPhrase(
            phrase="15 роз",
            count=50,
            kind="result",
            commercial=False,
            source="api",
            link_status="sku_specific",
        ),
        # ambiguous / category_generic НЕ привязаны вручную -> не должны учитываться
        WordstatPhrase(
            phrase="букет роз",
            count=500,
            kind="result",
            commercial=False,
            source="api",
            link_status="category_generic",
        ),
        WordstatPhrase(
            phrase="розы",
            count=1000,
            kind="result",
            commercial=False,
            source="api",
            link_status="ambiguous",
        ),
        # ambiguous привязана вручную к этому кластеру
        WordstatPhrase(
            phrase="розовые розы",
            count=200,
            kind="result",
            commercial=False,
            source="api",
            link_status="ambiguous",
            manually_linked_to="target_id",
        ),
        # sku_specific привязана вручную к ДРУГОМУ кластеру -> не должна учитываться здесь
        WordstatPhrase(
            phrase="красные розы",
            count=300,
            kind="result",
            commercial=False,
            source="api",
            link_status="sku_specific",
            manually_linked_to="other_id",
        ),
    ]

    # freq_sum = 100 + 50 + 200 = 350
    # freq_max = max(100, 50, 200) = 200
    freq_sum, freq_max = calculate_freq_sum_and_max(phrases, "target_id")
    assert freq_sum == 350
    assert freq_max == 200

    # commercial_share = 100 / 350 ≈ 0.2857
    comm_share = calculate_commercial_share(phrases, "target_id")
    assert abs(comm_share - (100 / 350)) < 1e-5
