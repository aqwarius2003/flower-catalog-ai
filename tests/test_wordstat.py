import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.wordstat import WordstatClient, parse_csv


@pytest.fixture
def top_requests_data():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "top_requests.json")
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def error_429_data():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "error_429.json")
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


def test_parse_csv():
    # Create a temporary CSV file
    csv_content = """поисковый запрос;популярность
купить розы;10 000
доставка цветов;5000
бесплатные картинки цветов; 100
"""
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write(csv_content)
        temp_path = f.name

    try:
        phrases = parse_csv(temp_path)
        assert len(phrases) == 3
        assert phrases[0].phrase == "купить розы"
        assert phrases[0].count == 10000
        assert phrases[0].commercial is True

        assert phrases[2].phrase == "бесплатные картинки цветов"
        assert phrases[2].count == 100
        assert phrases[2].commercial is False
    finally:
        os.unlink(temp_path)


def test_wordstat_client_avalanche_quota(top_requests_data):
    client = WordstatClient()

    with patch("src.wordstat.sse_client"), patch("src.wordstat.ClientSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.content = [MagicMock(type="text", text=json.dumps(top_requests_data))]
        mock_session.call_tool.return_value = mock_result
        mock_session_cls.return_value = mock_session

        with patch("src.wordstat.AsyncExitStack") as mock_stack_cls:
            mock_stack = mock_stack_cls.return_value.__aenter__.return_value
            mock_stack.enter_async_context.side_effect = [(MagicMock(), MagicMock()), mock_session]

            phrases = client.avalanche_queries(["query1", "query2"], max_requests=16)

            assert mock_session.call_tool.call_count == 1
            assert len(phrases) == 2
            assert phrases[0].phrase == "букет гипсофилы"


def test_wordstat_client_circuit_breaker(error_429_data):
    client = WordstatClient()

    with patch("src.wordstat.sse_client"), patch("src.wordstat.ClientSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.call_tool.side_effect = Exception("429 Too Many Requests")
        mock_session_cls.return_value = mock_session

        with patch("src.wordstat.AsyncExitStack") as mock_stack_cls:
            mock_stack = mock_stack_cls.return_value.__aenter__.return_value
            mock_stack.enter_async_context.side_effect = [(MagicMock(), MagicMock()), mock_session]

            phrases = client.avalanche_queries(["query1", "query2"], max_requests=100)

            assert mock_session.call_tool.call_count == 1
            assert len(phrases) == 0
            assert client.circuit_breaker_tripped is True
