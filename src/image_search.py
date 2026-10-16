import os

import httpx

from .trace import tracer


def search_images(query: str, limit: int = 5) -> list[str]:
    """
    Search images using Serper API with local filtering.
    """
    with tracer.span("search_images", query=query, limit=limit, op_type="READ_ONLY") as span:
        api_key = os.environ.get("SERPER_API_KEY")
        if not api_key:
            span.metadata["error"] = "SERPER_API_KEY not found"
            # Fallback for tests/stub
            return [f"https://example.com/stub_{query.replace(' ', '_')}.jpg"]

        url = "https://google.serper.dev/images"
        payload = {
            "q": query,
            "num": 20,  # Fetch more to allow for filtering
        }
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

        try:
            with httpx.Client() as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            images = data.get("images", [])
            valid_urls = []

            for img in images:
                img_url = img.get("imageUrl", "")
                # Local filtering: must be a string, and typically ends with image extensions
                # We can do a basic check or exclude certain formats like gif/svg
                img_url_lower = img_url.lower()
                if not img_url:
                    continue
                if img_url_lower.endswith((".gif", ".svg")):
                    continue

                # We could also check dimensions if provided by Serper
                width = img.get("imageWidth", 0)
                height = img.get("imageHeight", 0)
                if (
                    width > 0 and height > 0 and (width < 300 or height < 300)
                ):  # filter out very small images
                    continue

                valid_urls.append(img_url)
                if len(valid_urls) >= limit:
                    break

            span.metadata["found"] = len(valid_urls)
            return valid_urls

        except Exception as e:  # noqa: BLE001
            span.metadata["error"] = str(e)
            span.metadata["fallback"] = True
            return ["https://example.com/stub_error.jpg"]
