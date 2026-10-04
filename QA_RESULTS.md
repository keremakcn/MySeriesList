# MySeriesList 0.3 preview validation

- 29 automated tests passed using isolated temporary databases. Python fatal-error/undefined-name lint checks passed.
- Covered CSRF/host validation, escaped notes, concurrent duplicate additions, search deduplication, future-episode rejection, repeated next-episode submissions, metadata refresh, note/rating/favorite/progress preservation, delete/restore identity and v1 database migration with backup.
- Credential tests cover API key/Bearer formats, uncached verification, incorrect credentials, network failures, successful save, blank-field retesting and preserving the last saved credential after rejection.
- Read-only catalog browsing and season previews do not create library records. A later loaded season cannot be misrepresented as next while an earlier season is still unloaded.
- 50 responsive route checks passed at 360, 390, 768, 1440 and 1700 pixels: Library, Series, Search (initial/results/empty/error), Settings, Catalog and acting/directing profile filters. No horizontal overflow or JavaScript errors.
- Browser flows cover settings success/error/loading, blue external link, catalog-to-season exploration, search/catalog additions without navigation, duplicate results, failed additions, fixed-height cards, journal, episode progress, future-episode disabling, Undo and keyboard search focus.
- Season opening triggers automatic in-place loading. Keyboard opening, failed-load retry, cached reopening and preserving unsaved notes passed browser checks. The server also validates season membership and avoids repeating a completed load.
- Completed loads all seasons and atomically marks aired episodes (including specials) watched. Tests cover timestamp preservation, future/undated exclusions, failed or malformed remote responses leaving all rows unchanged, concurrent-progress conflicts and offline note editing on already completed series. Unmarking an episode returns Completed to Watching.
- Library/detail cast and director links, series-to-person-to-series navigation, direct additions, role filtering and deduplication passed. Producers/creators are not mislabeled as directors. Profile pagination handles invalid/out-of-range pages.
- Desktop and narrow-screen screenshots were inspected. Narrow-screen filters were adjusted after inspection to avoid truncated labels.
- A hidden native Windows WebView2 window rendered Settings and handed the TMDB external link to the system browser opener while staying on Settings. The OS opener was intercepted; this test does not launch the user's browser.
- `SeriesWatchlist-0.3-Preview.exe` startup, packaged Settings and the empty library passed with a temporary data directory. Only the test process was closed; the user's personal library was not opened.
- Live TMDB credential validation, TV search, aggregate actor/director credits, both person filmographies and a nine-episode season succeeded with the already saved MySeriesList credential. No credential was printed, embedded or changed, and no personal library records were edited.
- Automated browser checks use controlled fixtures; they are not real-device Android tests. Android packaging is outside this standalone desktop preview.

## Shared discovery gateway — 2026-10-05
- Default discovery now uses https://api.myshelf.cloud/3/ with a SeriesWatchlist/0.3 User-Agent and no client credentials.
- Token form and validation routes removed; old credential settings are securely removed on startup while preserving journal and episode data.
- 29 automated tests and 50 responsive browser page checks passed, including additions, Undo, season loading, completion rollback, person navigation and keyboard flows.
- Live gateway TV search (20 results), Dark detail, season 1 (10 episodes) and person TV credits verified.
- Rebuilt dist/MySeriesList.exe passed isolated startup, token-free Settings and live TV search.
- Personal databases were not opened during QA; cleanup of existing local tokens occurs on next application startup.

MySeriesList rebrand (2026-10-05): 29 tests passed; packaged MySeriesList.exe verified with new branding and live TV search in an isolated data directory. Existing AppData/SeriesWatchlist data path retained.

MySeriesList 1.0.0 release: 29 automated tests passed; rebuilt MySeriesList.exe shows 1.0.0 without Preview and passes isolated startup and live TV search.
