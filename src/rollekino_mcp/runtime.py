"""Server instance, client and the call helper every tool uses."""

import importlib.metadata
import json
import logging
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import Icon

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP = "rollekino"
TITLE = "Rollekino"
DEFAULT_URL = "https://www.rollekino.fi"
DEFAULT_PORT = 8600

ENV_URL = "ROLLEKINO_URL"
ENV_USER = "ROLLEKINO_USER"
ENV_PASSWORD = "ROLLEKINO_APP_PASSWORD"

# The theme's own namespace, added in inc/hooks/movies-api.php.
API = "/wp-json/rollekino/v1"
WP = "/wp-json/wp/v2"

try:
    __version__ = importlib.metadata.version(f"{APP}-mcp")
except importlib.metadata.PackageNotFoundError:  # running from a source tree
    __version__ = "0.0.0"

_ICON_BASE = os.getenv("MCP_PUBLIC_URL", "").rstrip("/")
_ICON_SIZES = (48, 96, 256)

mcp = FastMCP(
    APP,
    icons=(
        [
            Icon(
                src=f"{_ICON_BASE}/icon.png"
                if size == 256
                else f"{_ICON_BASE}/icon-{size}.png",
                mimeType="image/png",
                sizes=[f"{size}x{size}"],
            )
            for size in _ICON_SIZES
        ]
        if _ICON_BASE
        else None
    ),
    website_url=_ICON_BASE or None,
    instructions=(
        "Read and write rollekino.fi, Rolle's film archive: about 3400 reviewed "
        "films. It is the authoritative record of what he has watched and what "
        "he thought of it. "
        "RATINGS: his own, whole numbers 1 to 10, 0 for not rated. That is the "
        "archive's native scale: never convert from IMDb or Metascore, which "
        "are external and are never his opinion. If he gives stars out of 5, "
        "double them. "
        "DATES: each review carries the day he watched the film, which Trakt "
        "history records. Pass it as date, YYYY-MM-DD, never today's date by "
        "default. "
        "ADDING A FILM: lookup_tmdb for the id, then create_film with tmdb_id, "
        "rating and date. The archive keeps one entry per film, so create_film "
        "returns the existing entry instead of making a duplicate; update that "
        "with update_film or write_review. find_film checks by IMDb id first. "
        "The review text is his own: pass what he wrote, never compose one. "
        "READING: search_films by title, get_film for one full record, "
        "list_films to filter by year, genre, director, actor or rating, "
        "get_stats for the archive as a whole, list_queue for drafts waiting "
        "for a review. Writing needs an application password."
    ),
)

mcp._mcp_server.version = __version__

_READ = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}
_WRITE = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}
_DESTRUCTIVE = {**_WRITE, "destructiveHint": True}

_http: httpx.Client | None = None


def base_url() -> str:
    return (os.getenv(ENV_URL) or DEFAULT_URL).rstrip("/")


def _client() -> httpx.Client:
    global _http
    if _http is None:
        user = os.getenv(ENV_USER)
        password = os.getenv(ENV_PASSWORD)
        # Reads are public; only writes need the application password, so a
        # missing credential is not an error until something tries to write.
        auth = (user, password.replace(" ", "")) if user and password else None
        _http = httpx.Client(
            base_url=base_url(),
            auth=auth,
            timeout=httpx.Timeout(120.0, connect=15.0),
            follow_redirects=True,
            headers={"User-Agent": f"rollekino-mcp/{__version__}"},
        )
    return _http


def authenticated() -> bool:
    return bool(os.getenv(ENV_USER) and os.getenv(ENV_PASSWORD))


def _err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status in (401, 403):
            msg = (
                f"{TITLE} refused the write. Set {ENV_USER} and "
                f"{ENV_PASSWORD} to a WordPress application password for a "
                "user who can edit posts."
            )
        elif status == 404:
            msg = "No such film. Check the id, or search by title first."
        elif status == 400:
            msg = _message(e.response) or f"{TITLE} rejected the request."
        else:
            msg = f"{TITLE} API error (HTTP {status}): {_detail(e.response)}"
    elif isinstance(e, httpx.ConnectError):
        msg = f"Could not connect to {TITLE}. Check {ENV_URL}."
    elif isinstance(e, httpx.TimeoutException):
        msg = f"Request timed out. {TITLE} may be slow -- try again."
    else:
        msg = f"{type(e).__name__}: {e}"

    return json.dumps({"status": "error", "message": msg})


def _message(response: httpx.Response) -> str | None:
    """The human message WordPress puts in a WP_Error body."""
    try:
        return response.json().get("message")
    except (ValueError, AttributeError):
        return None


def _detail(response: httpx.Response) -> str:
    try:
        return json.dumps(response.json())[:600]
    except ValueError:
        return response.text[:300]


def _ok(data: dict) -> str:
    return json.dumps({"status": "success", **data}, indent=2)


def call(
    method: str,
    path: str,
    query: dict | None = None,
    body: dict | None = None,
) -> dict:
    """Perform one API call and return the decoded payload."""
    params = {k: v for k, v in (query or {}).items() if v is not None}
    response = _client().request(method, path, params=params or None, json=body)
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


def main() -> None:
    import argparse

    from dotenv import find_dotenv, load_dotenv

    from . import tools  # noqa: F401 -- importing registers every tool

    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path and load_dotenv(dotenv_path, override=False):
        logger.info("Loaded .env from %s", dotenv_path)

    parser = argparse.ArgumentParser(prog=f"{APP}-mcp")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default=os.getenv("MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("MCP_PORT", str(DEFAULT_PORT)))
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    if args.host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit(
            f"refusing to listen on {args.host}: this server has no login of "
            "its own. Keep it on the local machine and put a proxy in front."
        )

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    logger.info("Listening on http://%s:%d/mcp", args.host, args.port)
    mcp.run(transport="streamable-http")
