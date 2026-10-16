from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .models import Cluster
from .trace import tracer


class GeneratedMetadata(BaseModel):
    name: str = Field(
        description="Человекочитаемое название кластера (категории/товара) на русском"
    )
    folder_name: str = Field(description="Имя папки на английском, snake_case")
    description: str = Field(description="Короткое описание кластера для каталога")
    search_query: str = Field(
        description="Оптимальный поисковый запрос для поиска картинок для данного кластера (на английском)"
    )


def generate_cluster_metadata(cluster: Cluster) -> dict:
    model_name = "gemini-2.5-flash"
    temperature = 0.7

    with tracer.span(
        "generate_cluster_metadata",
        cluster_id=cluster.cluster_id,
        model=model_name,
        temp=temperature,
        op_type="READ_ONLY",
    ) as span:
        try:
            # Fallback logic relies on phrases
            top_phrase = (
                cluster.phrases[0].phrase if cluster.phrases else f"cluster_{cluster.cluster_id}"
            )

            client = genai.Client()  # Assumes GEMINI_API_KEY is in env

            phrases_str = ", ".join(p.phrase for p in cluster.phrases[:10])
            prompt = f"Сгенерируй метаданные для товарного кластера цветов. Фразы из кластера: {phrases_str}"

            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeneratedMetadata,
                    temperature=temperature,
                ),
            )

            if response.parsed and isinstance(response.parsed, BaseModel):
                return response.parsed.model_dump()
            else:
                raise ValueError("No parsed response returned")
        except Exception as e:  # noqa: BLE001
            span.metadata["fallback"] = True
            span.metadata["error_detail"] = str(e)

            top_phrase = (
                cluster.phrases[0].phrase if cluster.phrases else f"cluster_{cluster.cluster_id}"
            )
            return {
                "name": top_phrase.capitalize(),
                "folder_name": top_phrase.replace(" ", "_").lower(),
                "description": f"Кластер, основанный на запросе '{top_phrase}'",
                "search_query": top_phrase,
            }
