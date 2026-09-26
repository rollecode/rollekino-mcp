"""Tools over rollekino.fi."""

import httpx

from .runtime import (
    _DESTRUCTIVE,
    _READ,
    _WRITE,
    API,
    WP,
    _err,
    _ok,
    authenticated,
    base_url,
    call,
    mcp,
)


@mcp.tool(annotations=_READ)
def search_films(title: str, limit: int = 10) -> str:
    """Find films by title.

    Start here when you know the name. Returns the id needed by get_film.

    Args:
        title: Part of the film's title.
        limit: How many matches to return.
    """
    try:
        data = call("GET", f"{API}/films", query={"search": title, "per_page": limit})
        return _ok(
            {
                "matches": data.get("total"),
                "films": [
                    {
                        "id": f["id"],
                        "title": f["title"],
                        "year": f.get("year"),
                        "rating": f.get("rating"),
                        "link": f.get("link"),
                    }
                    for f in data.get("films", [])
                ],
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_film(id: int) -> str:
    """Get one film in full: the review, the rating, credits and every field.

    Args:
        id: Film id, from search_films or list_films.
    """
    try:
        return _ok({"film": call("GET", f"{API}/films/{id}")})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def list_films(
    year: int | None = None,
    genre: str | None = None,
    director: str | None = None,
    actor: str | None = None,
    min_rating: float | None = None,
    max_rating: float | None = None,
    unrated: bool | None = None,
    imdb: str | None = None,
    status: str = "publish",
    orderby: str = "date",
    order: str = "DESC",
    page: int = 1,
    per_page: int = 20,
) -> str:
    """List films, filtered and ordered.

    Args:
        year: Release year, as the archive records it.
        genre: Genre name in Finnish, such as Komedia or Draama.
        director: Director's name.
        actor: Actor's name.
        min_rating: Only films Rolle rated at least this, 1 to 10.
        max_rating: Only films he rated at most this, 1 to 10.
        unrated: True for films with no rating yet.
        imdb: IMDb id, to find one specific film.
        status: publish, draft, or any.
        orderby: date, title or rating.
        order: ASC or DESC.
        page: Which page of results.
        per_page: Results per page, at most 100.
    """
    try:
        data = call(
            "GET",
            f"{API}/films",
            query={
                "year": year,
                "genre": genre,
                "director": director,
                "actor": actor,
                "min_rating": min_rating,
                "max_rating": max_rating,
                "unrated": unrated,
                "imdb": imdb,
                "status": status,
                "orderby": orderby,
                "order": order,
                "page": page,
                "per_page": per_page,
            },
        )
        return _ok(
            {
                "total": data.get("total"),
                "pages": data.get("pages"),
                "page": data.get("page"),
                "films": data.get("films", []),
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_stats() -> str:
    """Get archive-wide figures: totals, average rating, the rating spread and
    films per year.

    Use this for questions about the collection rather than one film.
    """
    try:
        return _ok({"stats": call("GET", f"{API}/stats")})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def list_queue() -> str:
    """List draft films waiting for a review.

    These are queued by the Trakt importer after Rolle watches something.
    Needs an application password.
    """
    try:
        return _ok({"queue": call("GET", f"{API}/queue")})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def list_terms(taxonomy: str, search: str | None = None, limit: int = 50) -> str:
    """List genres, directors, writers or actors used in the archive.

    Args:
        taxonomy: One of genre, director, writer, actor.
        search: Narrow to names containing this.
        limit: How many terms to return.
    """
    try:
        if taxonomy not in ("genre", "director", "writer", "actor"):
            raise ValueError("taxonomy must be genre, director, writer or actor")
        terms = call(
            "GET",
            f"{WP}/{taxonomy}",
            query={"search": search, "per_page": limit, "orderby": "count",
                   "order": "desc"},
        )
        return _ok(
            {
                "terms": [
                    {"name": t["name"], "films": t.get("count"), "id": t["id"]}
                    for t in terms
                ]
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def get_connection_status() -> str:
    """Report which site this points at and whether writing is possible."""
    try:
        stats = call("GET", f"{API}/stats")
        return _ok(
            {
                "site": base_url(),
                "can_write": authenticated(),
                "films": stats.get("published"),
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_READ)
def lookup_tmdb(query: str) -> str:
    """Search TMDB for a film, to get the tmdb_id that create_film enriches from.

    This goes through the site, which holds the TMDB key, so no key is needed
    here. Needs an application password.

    Args:
        query: Film title to search for.
    """
    try:
        return _ok({"results": call("GET", f"{API}/lookup", query={"query": query})
                    .get("results", [])})
    except Exception as e:
        return _err(e)


def _conflict(e: Exception) -> dict | None:
    """The existing film, when the site refused to create a duplicate."""
    if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 409:
        try:
            return e.response.json().get("existing")
        except ValueError:
            return None
    return None


@mcp.tool(annotations=_READ)
def find_film(imdb_id: str) -> str:
    """Find a film by its IMDb id, including drafts.

    The reliable way to check whether a film is already in the archive before
    adding it, since titles repeat across remakes and translations.

    Args:
        imdb_id: IMDb id such as tt0816692, or a full IMDb URL.
    """
    try:
        data = call(
            "GET",
            f"{API}/films",
            query={"imdb": imdb_id, "status": "any", "per_page": 5},
        )
        return _ok({"found": data.get("total", 0), "films": data.get("films", [])})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def set_rating(id: int, rating: int) -> str:
    """Set Rolle's own rating for a film.

    Args:
        id: Film id.
        rating: Whole number 1 to 10, or 0 to clear. See create_film for the scale.
    """
    try:
        call("POST", f"{API}/films/{id}", body={"rating": rating})
        return _ok({"id": id, "rating": rating})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def write_review(
    id: int,
    content: str,
    rating: int | None = None,
    date: str | None = None,
    publish: bool = False,
) -> str:
    """Put Rolle's review text on a film.

    The text is his: pass what he wrote, never compose one for him.

    Args:
        id: Film id.
        content: The review, as HTML or plain paragraphs. Replaces what is there.
        rating: Whole number 1 to 10. See create_film.
        date: Date shown on the review. See create_film.
        publish: True moves a draft to published.
    """
    try:
        body: dict = {"content": content, "rating": rating, "date": date}
        if publish:
            body["status"] = "publish"
        result = call("POST", f"{API}/films/{id}",
                      body={k: v for k, v in body.items() if v is not None})
        return _ok({"id": id, "status": result.get("status"),
                    "date": result.get("date"), "link": result.get("link")})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def create_film(
    title: str,
    tmdb_id: int | None = None,
    rating: int | None = None,
    date: str | None = None,
    content: str = "",
    status: str = "draft",
    imdb_url: str | None = None,
    year: str | None = None,
    plot: str | None = None,
    allow_duplicate: bool = False,
) -> str:
    """Add a film to the archive, enriched from TMDB.

    With tmdb_id the site fetches plot, poster, backdrop, cast, crew, genres,
    trailer, IMDb and Metascore exactly as the quick review page does. Find the
    id with lookup_tmdb.

    The archive keeps one entry per film. If this one is already there, nothing
    is created and the existing entry comes back instead: update that with
    update_film or write_review rather than adding a second.

    Args:
        title: Film title, usually the Finnish release title if it has one.
        tmdb_id: TMDB id, from lookup_tmdb. Strongly preferred.
        rating: Rolle's own rating: whole number 1 to 10, 0 for not rated. This
            is the archive's native scale, so never convert from IMDb or
            Metascore. If he gives stars out of 5, double them.
        date: Date shown on the review, YYYY-MM-DD or YYYY-MM-DD HH:MM,
            Helsinki time. Use the day he watched it, which Trakt history
            records, not today.
        content: His review text. Leave empty rather than writing one for him.
        status: draft or publish.
        imdb_url: Full IMDb URL, when there is no tmdb_id.
        year: Release year, when there is no tmdb_id.
        plot: Finnish synopsis, when there is no tmdb_id.
        allow_duplicate: Create even if the film exists. Almost never right.
    """
    try:
        body = {
            "title": title,
            "tmdb_id": tmdb_id,
            "rating": rating,
            "date": date,
            "content": content,
            "status": status,
            "imdb_url": imdb_url,
            "_imdb_year": year,
            "plot": plot,
            "allow_duplicate": allow_duplicate or None,
        }
        result = call("POST", f"{API}/films",
                      body={k: v for k, v in body.items() if v is not None})
        return _ok({"id": result.get("id"), "status": result.get("status"),
                    "date": result.get("date"), "rating": result.get("rating"),
                    "link": result.get("link")})
    except Exception as e:
        existing = _conflict(e)
        if existing:
            return _ok({
                "created": False,
                "reason": "Already in the archive. Update this entry instead.",
                "existing": existing,
            })
        return _err(e)


@mcp.tool(annotations=_WRITE)
def update_film(
    id: int,
    title: str | None = None,
    date: str | None = None,
    rating: int | None = None,
    status: str | None = None,
    tmdb_id: int | None = None,
    plot: str | None = None,
    imdb_url: str | None = None,
    genre: list[str] | None = None,
    director: list[str] | None = None,
    writer: list[str] | None = None,
    actor: list[str] | None = None,
) -> str:
    """Change anything about an existing film. Only the fields given change.

    Args:
        id: Film id.
        title: New title.
        date: Date shown on the review. See create_film.
        rating: Whole number 1 to 10, 0 for not rated. See create_film.
        status: publish or draft. Publishing a draft keeps its date.
        tmdb_id: Refresh every metadata field, poster and credits from TMDB.
            The rating and review text are kept.
        plot: Finnish synopsis.
        imdb_url: Full IMDb URL.
        genre: Replace the genres. Finnish names, as list_terms shows them.
        director: Replace the directors.
        writer: Replace the writers.
        actor: Replace the cast.
    """
    try:
        body = {
            "title": title, "date": date, "rating": rating, "status": status,
            "tmdb_id": tmdb_id, "plot": plot, "imdb_url": imdb_url,
            "genre": genre, "director": director, "writer": writer, "actor": actor,
        }
        result = call("POST", f"{API}/films/{id}",
                      body={k: v for k, v in body.items() if v is not None})
        return _ok({"film": result})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_DESTRUCTIVE)
def trash_film(id: int) -> str:
    """Move a film to the trash. It can be restored from the WordPress admin.

    Args:
        id: Film id.
    """
    try:
        call("DELETE", f"{API}/films/{id}")
        return _ok({"trashed": id})
    except Exception as e:
        return _err(e)
