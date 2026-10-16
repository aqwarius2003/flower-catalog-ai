import json
import logging
import os
import time
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.sse import sse_client

from src.clusterer import is_commercial
from src.models import WordstatPhrase
from src.trace import tracer

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    pass


class UnauthorizedError(Exception):
    pass


def parse_csv(file_path: str) -> list[WordstatPhrase]:
    """Parse CSV export from wordstat.yandex.ru."""
    phrases = []
    with tracer.span("parse_csv", file=file_path) as span:
        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if "\t" in line:
                    parts = line.split("\t")
                else:
                    parts = line.split(";")

                if len(parts) >= 2:
                    phrase_text = parts[0].strip(' "')
                    if not phrase_text or phrase_text.lower() == "поисковый запрос":
                        continue

                    try:
                        # Clean count string
                        count_str = parts[1].replace(" ", "").replace('"', "")
                        count = int(count_str)
                    except ValueError:
                        continue

                    phrases.append(
                        WordstatPhrase(
                            phrase=phrase_text,
                            count=count,
                            kind="result",
                            commercial=is_commercial(phrase_text),
                            source="csv",
                            link_status="sku_specific",
                        )
                    )
            span.metadata["count"] = len(phrases)
        except Exception as e:
            span.metadata["error"] = str(e)
            raise
    return phrases


class WordstatClient:
    def __init__(self, api_key: str | None = None, folder_id: str | None = None):
        self.mcp_url = os.getenv(
            "WORDSTAT_MCP_URL",
            "https://db8kldi3ibgqsvlmlq1g.58zke0qh.mcpgw.serverless.yandexcloud.net/sse",
        )
        self.circuit_breaker_tripped = False
        self.tripped_at: float = 0.0

    def avalanche_queries(
        self, queries: list[str], max_requests: int | None = None
    ) -> list[WordstatPhrase]:
        """Process an avalanche of queries with quota reservation using MCP."""
        import asyncio

        return asyncio.run(self._avalanche_queries_async(queries, max_requests))

    async def _avalanche_queries_async(
        self, queries: list[str], max_requests: int | None
    ) -> list[WordstatPhrase]:
        results: list[WordstatPhrase] = []
        if max_requests is None:
            max_requests = int(os.getenv("WORDSTAT_MAX_REQUESTS", "200"))

        available_quota = max(0, max_requests - 15)  # Reservation of 15
        requests_made = 0

        with tracer.span(
            "avalanche_queries", num_queries=len(queries), quota=available_quota
        ) as span:
            try:
                headers = {}
                api_key = os.getenv("YANDEX_CLOUD_API_KEY")
                if api_key:
                    headers["Authorization"] = f"Api-Key {api_key}"

                async with AsyncExitStack() as stack:
                    transport = await stack.enter_async_context(
                        sse_client(self.mcp_url, headers=headers)
                    )
                    session = await stack.enter_async_context(
                        ClientSession(transport[0], transport[1])
                    )
                    await session.initialize()

                    for q in queries:
                        if requests_made >= available_quota:
                            logger.info("Quota exceeded.")
                            break

                        if self.circuit_breaker_tripped:
                            if time.time() - self.tripped_at > 60:
                                self.circuit_breaker_tripped = False
                            else:
                                logger.warning("Circuit breaker is open")
                                return results

                        try:
                            with tracer.span("api.fetch_top", query=q):
                                folder_id = os.getenv("YC_FOLDER_ID")
                                args = {"phrase": q, "numPhrases": 200}
                                if folder_id:
                                    args["folderId"] = folder_id

                                result = await session.call_tool("topRequests", arguments=args)
                                requests_made += 1

                                data = {}
                                if result.content and result.content[0].type == "text":
                                    data = json.loads(result.content[0].text)

                                items = data.get("results", []) + data.get("associations", [])
                                for item in items:
                                    phrase_text = item.get("phrase", "")
                                    count_str = item.get("count", "0")
                                    try:
                                        count = int(count_str)
                                    except ValueError:
                                        count = 0

                                    results.append(
                                        WordstatPhrase(
                                            phrase=phrase_text,
                                            count=count,
                                            kind="result",
                                            commercial=is_commercial(phrase_text),
                                            source="api",
                                            link_status="sku_specific",
                                        )
                                    )

                        except Exception as e:
                            if "429" in str(e) or "Too Many Requests" in str(e):
                                span.metadata["circuit_breaker"] = "triggered"
                                self.circuit_breaker_tripped = True
                                self.tripped_at = time.time()
                                logger.warning("Circuit breaker triggered due to 429.")
                                return results
                            else:
                                raise

            except Exception as e:
                logger.error(f"MCP connection error: {e}")
                raise

            span.metadata["requests_made"] = requests_made
            span.metadata["phrases_fetched"] = len(results)

        return results
