# Project Tracker – User Support Guide

Use this guide to help end users access the Project Tracker, understand the basics of navigation, and resolve common issues before escalating.

## What You Need
- Access to the host’s URL/port (default `https://<host>:5003` behind a proxy, otherwise `http://<host>:5003`).
- A browser (desktop or tablet; Safari/Chrome on iPad works best).
- An account/token if the host has enabled authentication or proxy-level basic auth.
- The host must already be signed into Dropbox on the machine that runs the app so the `BIDDING_FOLDER` path stays in sync.

## Core Views
- Dashboard: project list, statuses, and quick stats.
- Project detail: per-project files, notes, tags, bid dates, and classifications.
- Vendors: vendor list and quotes.
- Settings/admin pages: theme, intervals, and data refresh (availability depends on host configuration).

## Everyday Tasks
- Refresh your page if data looks stale; most data comes from the host’s local filesystem/database and may update between visits.
- Use search/filter controls in tables to narrow results; wide tables support horizontal scroll.
- File access and thumbnails come from the `BIDDING_FOLDER`; if a file is missing, confirm it exists in Dropbox and has fully synced on the host.

## Troubleshooting
- Page will not load: confirm the URL, ensure the host is running `python app.py`, and that any reverse proxy is up.
- “Missing BIDDING_FOLDER” or empty lists: host must set `BIDDING_FOLDER` in `.env` and keep Dropbox signed in/synced.
- Database locked or stale data: ask the host to restart the service; SQLite can temporarily lock under concurrent writes.
- Selenium/PlanHub/ProjectDog features failing: host must provide valid credentials and ensure Chrome/driver is installed if those features are enabled.
- UI clipped on tablets: rotate to landscape and/or reduce zoom; report persistent layout issues to the host for CSS tuning.

## Reporting an Issue
Provide: timestamp/timezone, page/URL, what you were doing, expected vs. actual result, screenshot if possible, and whether others see the same issue. Include the project slug/title if the problem is project-specific.

## Data Notes
- Project data, tags, and notes live in the host’s SQLite database (`data/project_tracker.db`); file operations touch the host’s `BIDDING_FOLDER`.
- Do not share public URLs without authentication; the app can expose local file names and bid data.
