import json

import httpx
import pytest

from rollekino_mcp import runtime, tools


@pytest.fixture
def site(monkeypatch):
    monkeypatch.setenv("ROLLEKINO_URL", "https://kino.test")
    monkeypatch.setenv("ROLLEKINO_USER", "u")
    monkeypatch.setenv("ROLLEKINO_APP_PASSWORD", "p")
    seen: dict = {}
    reply: dict = {"status": 200, "json": {"id": 1}}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["query"] = dict(request.url.params)
        seen["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(reply["status"], json=reply["json"])

    runtime._http = httpx.Client(
        base_url="https://kino.test", transport=httpx.MockTransport(handler)
    )
    yield seen, reply
    runtime._http = None


def test_create_sends_date_rating_and_tmdb(site):
    seen, _ = site
    tools.create_film("Nuremberg", tmdb_id=1214931, rating=4, date="2025-12-08")
    assert seen["path"] == "/wp-json/rollekino/v1/films"
    assert seen["body"]["date"] == "2025-12-08"
    assert seen["body"]["rating"] == 4
    assert seen["body"]["tmdb_id"] == 1214931


def test_create_leaves_out_unset_fields(site):
    seen, _ = site
    tools.create_film("Nuremberg", tmdb_id=1)
    assert "date" not in seen["body"]
    assert "allow_duplicate" not in seen["body"]


def test_a_duplicate_returns_the_existing_film(site):
    _, reply = site
    reply["status"] = 409
    reply["json"] = {"code": "already_exists", "existing": {"id": 77916, "title": "Nuremberg"}}
    result = json.loads(tools.create_film("Nuremberg", tmdb_id=1))
    assert result["status"] == "success"
    assert result["created"] is False
    assert result["existing"]["id"] == 77916


def test_a_validation_error_reads_as_the_site_wrote_it(site):
    _, reply = site
    reply["status"] = 400
    reply["json"] = {"code": "bad_rating", "message": "Rating is a whole number from 1 to 10, or 0 for not rated."}
    result = json.loads(tools.set_rating(1, 4))
    assert result["status"] == "error"
    assert result["message"].startswith("Rating is a whole number")


def test_update_sends_only_what_changed(site):
    seen, _ = site
    tools.update_film(77916, date="2025-12-08 20:26")
    assert seen["path"] == "/wp-json/rollekino/v1/films/77916"
    assert seen["body"] == {"date": "2025-12-08 20:26"}


def test_update_can_refresh_from_tmdb(site):
    seen, _ = site
    tools.update_film(77916, tmdb_id=1214931)
    assert seen["body"] == {"tmdb_id": 1214931}


def test_write_review_carries_the_date(site):
    seen, _ = site
    tools.write_review(77916, "Hyvä.", rating=4, date="2025-12-08", publish=True)
    assert seen["body"] == {"content": "Hyvä.", "rating": 4, "date": "2025-12-08", "status": "publish"}


def test_find_film_searches_every_status_by_imdb(site):
    seen, reply = site
    reply["json"] = {"total": 1, "films": [{"id": 77916}]}
    result = json.loads(tools.find_film("tt29567915"))
    assert seen["query"] == {"imdb": "tt29567915", "status": "any", "per_page": "5"}
    assert result["found"] == 1


def test_instructions_state_the_scale_and_the_date():
    text = runtime.mcp.instructions
    assert "1 to 10" in text
    assert "never convert" in text
    assert "YYYY-MM-DD" in text


def test_every_tool_registers():
    import asyncio

    assert len(asyncio.run(runtime.mcp.list_tools())) == 14
