# MarketAI Desktop — Community Cloud Client

The Desktop is a free client of MarketAI Cloud. Marketplace and AI credentials for the hosted workflow stay on the Cloud.

## Development

Start the Cloud API first (see the root README). On Windows, set `MARKETAI_CLOUD_URL=http://127.0.0.1:9000` and run `run_desktop_dev.bat`.

For browser development on Linux:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
MARKETAI_CLOUD_URL=http://127.0.0.1:9000 MARKETAI_DATA_DIR=/tmp/marketai-desktop \
  .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The native window, installer and Windows DPAPI protection require Windows validation.

## Account data

Analyses are saved to account-scoped Cloud history. The interface displays the latest 80 records and can reopen full analyses. Earlier local history is imported once as labeled summaries. Sentinel is the shared source of monitored products; local caches preserve the last successful synchronization. Manual refresh retrieves changes from other devices. A failed save never reports monitoring as active.

Deleting history applies across devices after synchronization. Stopping monitoring preserves earlier snapshots and alerts. Backup imports merge summaries and monitored products into the same account; a backup from another account is rejected. See `docs/PRIVACIDADE.txt` for data handling.

## Windows builds

Set `MARKETAI_CLOUD_URL` to the HTTPS Cloud deployment before running `build_installer.bat`. Installer filenames use the application version automatically. Update Cloud and Desktop together when using the new history endpoints.
