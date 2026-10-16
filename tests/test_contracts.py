from src.clusterer import (
    calculate_commercial_share,
    calculate_freq_sum_and_max,
    calculate_growth,
    calculate_score,
    generate_cluster_id,
    get_tier,
    is_commercial,
)
from src.models import Cluster, WordstatPhrase


def test_pydantic_models():
    # Test valid phrase creation
    phrase = WordstatPhrase(
        phrase="купить розы",
        count=1000,
        kind="result",
        commercial=True,
        source="api",
        link_status="sku_specific",
    )
    assert phrase.phrase == "купить розы"

    # Test Cluster creation
    cluster = Cluster(
        cluster_id="s15|red|pNONE",
        stems=15,
        color="red",
        packaging=None,
        phrases=[phrase],
        freq_max=1000,
        freq_sum=1000,
        growth=0.5,
        commercial_share=1.0,
        score=85.5,
        tier="strong",
    )
    assert cluster.cluster_id == "s15|red|pNONE"


def test_is_commercial():
    assert is_commercial("купить гипсофилу") is True
    assert is_commercial("гипсофила цена") is True
    assert is_commercial("фото гипсофилы") is False


def test_generate_cluster_id():
    assert generate_cluster_id(15, "Розовый", "Крафт") == "s15|розовый|крафт"
    assert generate_cluster_id(None, None, None) == "sNONE|cNONE|pNONE"
    assert generate_cluster_id(51, " white ", None) == "s51|white|pNONE"


def test_calculate_growth():
    assert calculate_growth([100, 150]) == 0.5
    assert calculate_growth([100, 50]) == -0.5
    assert calculate_growth([100, 100]) == 0.0
    assert calculate_growth([100]) is None
    assert calculate_growth([]) is None
    # Division by zero protection
    assert calculate_growth([0, 50]) == 50.0


def test_calculate_commercial_share_and_freq():
    cluster_id = "s15|red|pNONE"
    phrases = [
        WordstatPhrase(
            phrase="купить",
            count=100,
            kind="result",
            commercial=True,
            source="api",
            link_status="sku_specific",
        ),
        WordstatPhrase(
            phrase="фото",
            count=50,
            kind="result",
            commercial=False,
            source="api",
            link_status="sku_specific",
        ),
        WordstatPhrase(
            phrase="generic",
            count=200,
            kind="result",
            commercial=False,
            source="api",
            link_status="category_generic",
        ),
        WordstatPhrase(
            phrase="manual_buy",
            count=50,
            kind="result",
            commercial=True,
            source="api",
            link_status="ambiguous",
            manually_linked_to=cluster_id,
        ),
    ]

    # Generic phrase is ignored. Manual linked is included.
    # Total valid: 100 + 50 + 50 = 200
    # Commercial valid: 100 + 50 = 150
    # Share: 150 / 200 = 0.75

    assert calculate_commercial_share(phrases, cluster_id) == 0.75

    freq_sum, freq_max = calculate_freq_sum_and_max(phrases, cluster_id)
    assert freq_sum == 200
    assert freq_max == 100


def test_calculate_score():
    score = calculate_score(
        freq_max=100,
        freq_sum=200,
        max_freq_max=1000,
        max_freq_sum=2000,
        growth=1.0,
        commercial_share=0.5,
    )
    # log1p(100)/log1p(1000) * 0.8 + log1p(200)/log1p(2000) * 0.1 + 0.07*(0.5+0.5*1) + 0.03*0.5
    assert isinstance(score, float)
    assert 0 <= score <= 100


def test_get_tier():
    assert get_tier(10, 300, 50, False) == "tail"
    assert get_tier(100, 300, 50, False) == "weak"
    assert get_tier(400, 300, 50, False) == "strong"
    assert get_tier(500, 300, 50, True) == "head"
