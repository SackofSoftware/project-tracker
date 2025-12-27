# Repository Guidelines

## Project Structure & Module Organization
- `app.py` is the Flask entrypoint; it reads `.env` settings and wires modules.
- `modules/` holds feature logic: bidding folder handling, scope takeoff, file routing/splitting, briefs and classification, external scraping (PlanHub/ProjectDog), syncing, vendors, quotes, and tracking.
- Views live in `templates/`; assets and generated thumbnails in `static/`. Cached or sample data sits under `data/`, `projectdog/`, and `planhub/`.
- Reference docs: `*_SUMMARY.md`, `FILE_ORGANIZATION*.md`, and quickstart guides at the repo root. Test/utility scripts include `test_async_endpoints.py`, `test_brief_endpoint.py`, `test_file_organization.py`, and `verify_implementation.py`.

## Build, Test, and Development Commands
- Create env & install deps: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
- Run the dashboard: `python app.py` (default port 5003; needs `.env` with `BIDDING_FOLDER`, `PROJECTDOG_EMAIL`, `PROJECTDOG_PASSWORD`, `SYNC_INTERVAL_HOURS`).
- Quick wiring check: `python verify_implementation.py`.
- File organization test: `python test_file_organization.py "Bidding/Project-Name" organizer|full`.
- Async/brief smoke tests (server running): `python test_async_endpoints.py` and `python test_brief_endpoint.py`. Hybrid ID: `python test_hybrid_identification.py`.

## Coding Style & Naming Conventions
- Python 3, 4-space indentation; snake_case for vars/functions, PascalCase classes, UPPER_SNAKE constants.
- Prefer f-strings and small helpers; add short docstrings describing behavior/inputs. Keep paths configurable (env-driven) rather than hardcoded user roots.
- Preserve existing Jinja syntax when editing templates/static assets.

## Testing Guidelines
- Add runnable `test_<feature>.py` scripts. Avoid long external calls unless guarded by explicit flags.
- Use local sample projects for endpoint tests to prevent hitting live services. Keep artifacts in `static/data` or `Extracted-Data` small and logged.

## Commit & Pull Request Guidelines
- Commit messages: imperative and concise (e.g., `Add async drawings status polling`). Group related changes.
- PRs should state purpose, touched modules/templates, env prerequisites, and manual test commands/results; include screenshots for UI/data diffs when helpful.
- Do not commit secrets or customer data. Scrub `.env`, cached JSON, and generated docs before sharing.

## Security & Configuration Tips
- Keep `.env` local; rotate ProjectDog credentials if scraping fails. Validate external URLs and file paths before writing; prefer `Path` utilities to avoid clobbering user directories.
- Selenium scraping may require non-headless Chrome; document driver changes when altering automation.
