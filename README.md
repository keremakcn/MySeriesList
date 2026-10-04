# MySeriesList v1.0.0

A standalone TV journal inspired by MyMovieList. It has its own source folder, desktop window and database. It does not import or alter the movie library.

## First public release — 1.0.0

- **Discovery without setup:** the shared `api.myshelf.cloud` service handles TMDB requests; users no longer need an API key or token.
- **Simpler Settings:** credential entry and verification are removed. Existing local credential settings are securely deleted on startup without changing your journal or episode progress.
- **Independent private libraries:** MyMovieList and MySeriesList use the same hosted discovery service, but keep separate local databases.
- **Verified integration:** 29 automated tests, 50 responsive page checks and live TV search in the packaged Windows app passed before the version bump. TV details, season episodes and people credits were also checked against the live service.

## Features

- Discovery works immediately through `https://api.myshelf.cloud`, shared with MyMovieList. No personal TMDB key or account is required.
- TMDB TV search, pagination, deduplicated results and duplicate-safe additions directly from search. Add without leaving your results.
- Explore series details, cast, seasons and episodes **before adding anything to your library**. Episode synopses are collapsed to avoid accidental spoilers.
- One card per series; season and episode lists on the detail page.
- Open a season to load its episodes automatically in place, with loading/error feedback and retry. Loaded seasons reopen without another request. Refresh remains available.
- Change the status to **Completed** and save to load all seasons and mark every aired episode, including specials, watched. Existing watched timestamps are preserved; future and undated episodes remain unmarked. A failed fetch leaves the entire journal/progress unchanged.
- Click cast and director names on library cards or series details to explore a profile and its TV credits, filter by acting/directing, and add other series. Aggregate credits cover the entire series; creators and directors are labeled separately.
- Mark individual episodes or the next available regular episode watched. Repeated submissions cannot skip episodes. Specials are handled separately; future or unknown-air-date episodes cannot be marked watched.
- Watching, Want to watch, On hold, Dropped and Completed statuses.
- Private notes, ratings, favorites, status/favorite filters, title/rating sorting and soft-delete Undo.
- Refreshed responsive interface, fixed-height library cards, an up-next panel, season progress and keyboard focus with **Ctrl+K** (or **Cmd+K**).
- Refresh series metadata and season lists without changing notes, ratings, favorites or episode progress.
- Local CSRF protection, validated input and bounded TMDB cache with duplicate-request prevention.

## Run

Python 3.12 recommended:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python run_desktop.py
```

For the browser interface, run `python app.py`. Both entry points bind only to localhost on an available port.

Data is saved in `%APPDATA%\SeriesWatchlist\series.db` on Windows (otherwise `~/SeriesWatchlist/series.db`). MyMovieList's database and settings are never loaded. The TMDB credential stays in a Cloudflare Secret, outside the desktop app. Searches and catalog requests pass through our shared Cloudflare gateway to TMDB. Legacy local token settings are removed on startup. `TMDB_ACCESS_TOKEN` is no longer used. `SERIES_WATCHLIST_GATEWAY_URL` can override the HTTPS gateway for deployments. Notes and viewing progress are not sent to TMDB.

Opening an existing 0.1 library upgrades it automatically and creates `series.db.before-v2.bak` before the first migration. Existing notes, episode progress, ratings, favorites and creation times are preserved. Close the old application before opening the new executable. The optional `SERIES_WATCHLIST_DATA_DIR` environment variable selects an isolated data directory for development and QA.

## Windows build

```powershell
.\build.ps1
```

Requires the desktop dependencies, including PyInstaller. The output is `dist\MySeriesList.exe`, with the custom application icon embedded. This is the standalone MySeriesList Windows release.

## Logo and icon

The lavender ribbon combines an S-shaped fold, a bookmark and a play symbol. [Logo PNG](static/branding/series-watchlist-logo.png) · [Windows ICO](static/branding/series-watchlist.ico). The ICO contains 16, 20, 24, 32, 40, 48, 64, 128 and 256 pixel versions. The logo is used in the sidebar, browser tab and desktop window. See [BRANDING.md](BRANDING.md) for the original generation prompt and asset details.

## Tests

Install pytest, then run `python -m pytest -q` from this folder. Tests use temporary databases and mocked TMDB data. `tests/preview.py` serves an isolated browser fixture on port 5063. `tests/browser.cjs` runs Playwright checks using `PLAYWRIGHT_MODULE` and `EDGE_PATH`. Create `.qa` before running browser screenshots. On Windows, `tests/desktop_smoke.py` checks WebView2 rendering and intercepts the browser opener to verify external-link handoff without opening an external page. See [QA_RESULTS.md](QA_RESULTS.md) for validation details.

## Supported platforms and current scope

This release supports Windows desktop and a local browser interface. An Android release is not included. Loaded episodes and journal edits (including notes on completed series) remain available offline. First-time season loads, changing to Completed, people profiles and remote posters need internet. No automatic sync, notification scheduler, individual-season bulk actions, rewatch history, recommendations or manual series creation yet. Completed reflects the user's current viewing progress; it does not mean the series has ended. Unmarking an episode on a completed series returns it to Watching. New releases are never silently marked watched. Next-episode actions load missing seasons as needed; refresh previously loaded seasons to pick up new episodes. Undo restores the last removed series in the current session.

The provider client is adapted from MyMovieList. The applications share a hosted discovery gateway, while their local libraries and Python runtimes remain independent. Keep catalog data separate from personal progress when integrating them later; use provider + media type + provider ID as catalog identity.

This product uses the TMDB API but is not endorsed or certified by TMDB.


## Name and existing libraries

MySeriesList was previously called Series Watchlist. Existing Windows libraries continue using `%APPDATA%\SeriesWatchlist` so upgrading does not create an empty library or require a manual transfer. Existing data-directory and gateway environment variable names remain supported. The repository and source folder names may still use the original name.
