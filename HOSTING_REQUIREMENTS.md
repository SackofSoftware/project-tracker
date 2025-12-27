# Project Tracker – Hosting Requirements

This document covers what a host needs to run and share the Project Tracker reliably, including Dropbox access for source files.

## Platform & Hardware
- OS: Linux or macOS recommended; Raspberry Pi 4/5 works on 64-bit Raspberry Pi OS.
- Python: 3.10+ with `python3-venv` and `pip`.
- Resources: 2+ CPU cores, 4GB+ RAM (more for Selenium scraping), and fast storage for the `BIDDING_FOLDER` plus the SQLite DB (`data/project_tracker.db`).

## External Dependencies
- Dropbox: the host must be signed into Dropbox and keep the `BIDDING_FOLDER` path fully synced; choose a local path in `.env` that matches the synced folder.
- Optional scraping: Chrome/Chromium + matching ChromeDriver for Selenium-based PlanHub/ProjectDog modules.
- Network egress: required for PlanHub/ProjectDog scraping and any external API calls you enable.

## Environment & Configuration
- Create `.env` with at least:
  - `BIDDING_FOLDER=/path/to/Dropbox/Bidding` (must exist and stay synced)
  - `PROJECTDOG_EMAIL`, `PROJECTDOG_PASSWORD` (if used)
  - `SYNC_INTERVAL_HOURS` and other feature flags as needed
- Install dependencies: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
- Run locally: `python app.py` (default port 5003).

## Network & Access
- Default port: 5003; expose via reverse proxy (Caddy/NGINX) for HTTPS and optional basic auth while app-level auth is added.
- Tunneling option: Cloudflare Tunnel or Tailscale for secure access without router port forwards.
- Ensure the host can reach Dropbox and any scraping targets; lock down inbound access to trusted users.

## Running as a Service
- Use a process manager (systemd/supervisor/pm2) to keep the app alive and restart on failure.
- Point working directory to the repo root; load the virtualenv and `.env` before starting.
- Rotate logs and monitor disk usage in `data/` and the `BIDDING_FOLDER`.

## Updates & Maintenance
- Pull changes, reinstall requirements if they change, and restart the service.
- Back up `data/project_tracker.db` and critical config; if you migrate to Postgres for multi-user writes, update configs accordingly.
- Periodically verify Dropbox sync health; if files appear missing in the app, resync the `BIDDING_FOLDER` and restart.
