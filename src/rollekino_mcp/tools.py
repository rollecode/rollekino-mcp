"""Tools over rollekino.fi."""

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
        min_rating: Only films Rolle rated at least this, out of 10.
        max_rating: Only films he rated at most this.
        unrated: True for films with no rating yet.
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


@mcp.tool(annotations=_WRITE)
def set_rating(id: int, rating: float) -> str:
    """Set Rolle's own rating for a film, out of 10.

    Args:
        id: Film id.
        rating: 1 to 10. Half points are allowed.
    """
    try:
        if not 0 <= rating <= 10:
            raise ValueError("rating must be between 0 and 10")
        call("POST", f"{API}/films/{id}", body={"rating": rating})
        return _ok({"id": id, "rating": rating})
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def write_review(
    id: int,
    content: str,
    rating: float | None = None,
    publish: bool = False,
) -> str:
    """Write or replace the review text on a film.

    Args:
        id: Film id.
        content: The review, as HTML or plain paragraphs. Replaces what is there.
        rating: Optionally set the rating at the same time.
        publish: True moves a draft to published.
    """
    try:
        body: dict = {"content": content}
        if rating is not None:
            body["rating"] = rating
        if publish:
            body["status"] = "publish"
        result = call("POST", f"{API}/films/{id}", body=body)
        return _ok(
            {
                "id": id,
                "status": result.get("status"),
                "link": result.get("link"),
            }
        )
    except Exception as e:
        return _err(e)


@mcp.tool(annotations=_WRITE)
def create_film(
    title: str,
    tmdb_id: int | None = None,
    content: str = "",
    rating: float | None = None,
    year: str | None = None,
    imdb_url: str | None = None,
    plot: str | None = None,
    status: str = "draft",
) -> str:
    """Create a film entry, optionally enriched from TMDB.

    With tmdb_id the site fetches plot, poster, backdrop, cast, crew, genres,
    trailer, IMDb and Metascore and stores them exactly as quick-review.php
    does, so the film renders identically. Use lookup_tmdb to find the id.

    Args:
        title: Film title.
        tmdb_id: TMDB id, from lookup_tmdb. Strongly preferred.
        content: The review text.
        rating: Rolle's rating out of 10.
        year: Release year.
        imdb_url: Full IMDb URL for the film.
        plot: Synopsis, in Finnish, as the theme expects.
        status: draft or publish.
    """
    try:
        meta = {
            k: v
            for k, v in {
                "rating": rating,
                "_imdb_year": year,
                "imdb_url": imdb_url,
                "plot": plot,
            }.items()
            if v is not None
        }
        result = call(
            "POST",
            f"{API}/films",
            body={"title": title, "content": content, "status": status,
                  "tmdb_id": tmdb_id, **meta},
        )
        return _ok(
            {"id": result.get("id"), "status": result.get("status"),
             "link": result.get("link")}
        )
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
