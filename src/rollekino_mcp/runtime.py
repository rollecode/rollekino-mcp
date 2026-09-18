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
        "films, each with his own 1-10 rating alongside IMDb and Metascore. "
        "This is the authoritative record of what he has watched and what he "
        "thought of it. "
        "Use search_films to find a film by title, get_film for one record with "
        "its full review and credits, and list_films to filter by year, genre, "
        "director, actor or rating. get_stats answers questions about the "
        "archive as a whole. Ratings are his, out of 10; imdb_rating and "
        "metascore are external and should never be quoted as his opinion. "
        "Writing needs an application password."
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
        else:
            msg = f"{TITLE} API error (HTTP {status}): {_detail(e.response)}"
    elif isinstance(e, httpx.ConnectError):
        msg = f"Could not connect to {TITLE}. Check {ENV_URL}."
    elif isinstance(e, httpx.TimeoutException):
        msg = f"Request timed out. {TITLE} may be slow -- try again."
    else:
        msg = f"{type(e).__name__}: {e}"

    return json.dumps({"status": "error", "message": msg})


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
