from typing import Literal

from pydantic import BaseModel


class WordstatPhrase(BaseModel):
    phrase: str
    count: int
    kind: Literal["result", "association"]
    commercial: bool
    source: Literal["api", "csv"]
    link_status: Literal["sku_specific", "ambiguous", "category_generic", "excluded"]
    manually_linked_to: str | None = None


class Cluster(BaseModel):
    cluster_id: str
    stems: int | None
    color: str | None
    packaging: str | None
    phrases: list[WordstatPhrase]
    freq_max: int
    freq_sum: int
    growth: float | None
    commercial_share: float
    score: float
    tier: Literal["head", "strong", "weak", "tail"]
    name: str | None = None
    folder_name: str | None = None
    search_query: str | None = None
    description: str | None = None
    decision: Literal["pending", "approved", "rejected"] = "pending"


class ProcessingOptions(BaseModel):
    remove_bg: bool = True
    seg_model: Literal["birefnet-general", "isnet-general-use"] = "birefnet-general"
    center: bool = True
    crop_ratio: float = 0.78
    shadow: bool = True
    canvas: tuple[int, int] = (1200, 1200)
    bg_color: str = "#F2F2F2"
    export_jpeg_q: int = 95
    export_webp: bool = True


class ItemInfo(BaseModel):
    name: str
    folder_name: str
    description: str
    color: str | None
    packaging: str | None
    queries: list[WordstatPhrase]
    manually_linked_queries: list[WordstatPhrase] = []
    freq_max: int
    freq_sum: int
    tier: str
    sources: list[str]
    photos_count: int
