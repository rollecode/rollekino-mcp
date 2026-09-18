# Rollekino MCP server

Read and write the film archive at [rollekino.fi](https://www.rollekino.fi): about 3400 reviewed films, each with a personal 1-10 rating alongside IMDb and Metascore.

Runs on the same host as the site, served at `https://www.rollekino.fi/mcp` by nginx in front of the Python server on 8600 and its OAuth login on 8602. It is not WordPress and exposes only film tools.

## Tools

Reading: `search_films`, `get_film`, `list_films`, `get_stats`, `list_terms`, `list_queue`, `get_connection_status`.

Writing: `set_rating`, `write_review`, `create_film`, `trash_film`, `lookup_tmdb`.

`list_films` filters by year, genre, director, actor and rating range, orders by rating, title or date, and paginates.

## The site side

The film data comes from `rollekino/v1`, added to the theme in `inc/hooks/movies-api.php`. Writes go through that namespace rather than `/wp/v2/movie`, because the theme registers a REST field named `meta` for the Vue archive which shadows core's meta object.

`create_film` with a `tmdb_id` enriches from TMDB and OMDB using the helpers in `inc/movie-enrich.php`, shared with `quick-review.php`, so a film created here renders identically to one posted from the quick review page.

## Setup

```bash
uv venv && uv pip install -e .
```

```bash
export ROLLEKINO_URL=https://www.rollekino.fi
export ROLLEKINO_USER=...              # WordPress user with edit_posts
export ROLLEKINO_APP_PASSWORD=...      # application password
```

Reads are public; only writes need the credentials.
