import math
import re
from typing import Literal

from src.models import Cluster, WordstatPhrase

COMMERCIAL_WORDS = {"купить", "цена", "доставка", "заказать", "недорого"}


def is_commercial(phrase: str) -> bool:
    phrase_lower = phrase.lower()
    return any(word in phrase_lower for word in COMMERCIAL_WORDS)


def generate_cluster_id(stems: int | None, color: str | None, packaging: str | None) -> str:
    s = f"s{stems}" if stems is not None else "sNONE"

    if color is not None:
        c = " ".join(sorted(color.strip().lower().split()))
    else:
        c = "cNONE"

    if packaging is not None:
        p = " ".join(sorted(packaging.strip().lower().split()))
    else:
        p = "pNONE"

    return f"{s}|{c}|{p}"


def calculate_growth(dynamics_data: list[int]) -> float | None:
    if len(dynamics_data) < 2:
        return None
    last_count = dynamics_data[-1]
    prev_count = dynamics_data[-2]
    return (last_count - prev_count) / max(prev_count, 1)


def calculate_commercial_share(phrases: list[WordstatPhrase], cluster_id: str) -> float:
    # 5.2.1: freq_sum = сумма count фраз, фактически привязанных к этому SKU (авто + ручные)
    valid_phrases = [
        p
        for p in phrases
        if (p.link_status == "sku_specific" and p.manually_linked_to is None)
        or p.manually_linked_to == cluster_id
    ]
    total_count = sum(p.count for p in valid_phrases)
    if total_count == 0:
        return 0.0
    commercial_count = sum(p.count for p in valid_phrases if p.commercial)
    return commercial_count / total_count


def calculate_freq_sum_and_max(phrases: list[WordstatPhrase], cluster_id: str) -> tuple[int, int]:
    valid_phrases = [
        p
        for p in phrases
        if (p.link_status == "sku_specific" and p.manually_linked_to is None)
        or p.manually_linked_to == cluster_id
    ]
    freq_sum = sum(p.count for p in valid_phrases)
    freq_max = max((p.count for p in valid_phrases), default=0)
    return freq_sum, freq_max


def calculate_score(
    freq_max: int,
    freq_sum: int,
    max_freq_max: int,
    max_freq_sum: int,
    growth: float | None,
    commercial_share: float,
) -> float:
    Fmax = math.log1p(freq_max) / math.log1p(max_freq_max) if max_freq_max > 0 else 0.0
    Fsum = math.log1p(freq_sum) / math.log1p(max_freq_sum) if max_freq_sum > 0 else 0.0

    if growth is not None:
        T = 0.5 + 0.5 * max(-1.0, min(1.0, growth))
    else:
        T = 0.5

    C = commercial_share

    score = 100 * (0.80 * Fmax + 0.10 * Fsum + 0.07 * T + 0.03 * C)
    return round(score, 2)


def get_tier(
    freq_max: int, min_count: int, tail_count: int, is_top_20_percent: bool
) -> Literal["head", "strong", "weak", "tail"]:
    if freq_max < tail_count:
        return "tail"
    if freq_max < min_count:
        return "weak"
    if is_top_20_percent:
        return "head"
    return "strong"


def carry_over_decision(
    cluster_id: str,
    old_decisions: dict[str, Literal["pending", "approved", "rejected"]],
    old_phrases: set[str],
    new_phrases: set[str],
) -> tuple[Literal["pending", "approved", "rejected"], bool]:
    if cluster_id not in old_decisions:
        return "pending", False

    decision = old_decisions[cluster_id]
    phrases_changed = old_phrases != new_phrases
    return decision, phrases_changed


def parse_phrase_features(
    phrase: str,
) -> tuple[
    int | None, str | None, str | None, Literal["sku_specific", "ambiguous", "category_generic"]
]:
    phrase_lower = phrase.lower()
    stems = None
    color = None
    packaging = None

    match_stems = re.search(r"\b(\d+)\b", phrase_lower)
    if match_stems:
        stems = int(match_stems.group(1))

    colors = [
        "бел",
        "розов",
        "красн",
        "желт",
        "син",
        "фиолетов",
        "малинов",
        "сиренев",
        "персиков",
        "кремов",
        "голуб",
        "черн",
        "оранжев",
        "бордов",
        "светл",
        "темн",
        "микс",
        "разноцветн",
    ]
    for c in colors:
        if c in phrase_lower:
            match_color = re.search(rf"\b({c}[а-я]*)\b", phrase_lower)
            if match_color:
                color = match_color.group(1)
                break

    if "коробк" in phrase_lower:
        packaging = "коробка"
    elif "корзин" in phrase_lower:
        packaging = "корзина"
    elif "крафт" in phrase_lower:
        packaging = "крафт"
    elif "пленк" in phrase_lower or "плёнк" in phrase_lower:
        packaging = "пленка"
    elif "монобукет" in phrase_lower:
        packaging = "монобукет"

    status: Literal["sku_specific", "ambiguous", "category_generic"]
    if not stems and not color and not packaging:
        status = "category_generic"
    elif (stems and not color and not packaging) or (not stems and color and not packaging):
        status = "ambiguous"
    else:
        status = "sku_specific"

    return stems, color, packaging, status


def build_clusters(phrases: list[WordstatPhrase], category: str) -> list[Cluster]:
    cluster_map: dict[str, Cluster] = {}

    for p in phrases:
        stems, color, packaging, status = parse_phrase_features(p.phrase)
        p.link_status = status

        if status == "sku_specific":
            cid = generate_cluster_id(stems, color, packaging)
            if cid not in cluster_map:
                cluster_map[cid] = Cluster(
                    cluster_id=cid,
                    stems=stems,
                    color=color,
                    packaging=packaging,
                    phrases=[],
                    freq_max=0,
                    freq_sum=0,
                    growth=None,
                    commercial_share=0.0,
                    score=0.0,
                    tier="tail",
                )
            cluster_map[cid].phrases.append(p)

    clusters = list(cluster_map.values())
    if not clusters:
        return []

    for c in clusters:
        c.freq_sum, c.freq_max = calculate_freq_sum_and_max(c.phrases, c.cluster_id)
        c.commercial_share = calculate_commercial_share(c.phrases, c.cluster_id)

    max_freq_max = max(c.freq_max for c in clusters)
    max_freq_sum = max(c.freq_sum for c in clusters)

    for c in clusters:
        c.score = calculate_score(
            c.freq_max, c.freq_sum, max_freq_max, max_freq_sum, c.growth, c.commercial_share
        )

    clusters.sort(key=lambda x: (x.score, x.freq_max), reverse=True)

    top_20_idx = int(len(clusters) * 0.2)
    for i, c in enumerate(clusters):
        c.tier = get_tier(
            c.freq_max, min_count=300, tail_count=50, is_top_20_percent=i < top_20_idx
        )
        if not c.name:
            st_str = f"{c.stems} " if c.stems else ""
            col_str = f"{c.color} " if c.color else ""
            pkg_str = f" в {c.packaging}" if c.packaging else ""
            c.name = f"{st_str}{col_str}{category}{pkg_str}".strip().title()

    return clusters
