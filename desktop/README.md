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

## Saved SKU catalog

Product catalog stores SKU, supplier, variant, stock and validated pricing inputs
on the Cloud account. Create products manually or save reviewed CSV rows. SKUs
are unique within the account and imports never overwrite different existing data.
Edits require the current revision and retain a change history. Comparison results
come only from server-side analyses; changed pricing inputs flag them as outdated.
Search, filters and sorting apply across the catalog, with 50 products per page.
Analyze selection starts a durable batch with the saved inputs. Monitor selection
reuses one Sentinel watch per SKU; the separate Sentinel worker must run for
recurring collections. Editing costs updates that monitor while preserving its
active/paused state. Stock is manual; no marketplace inventory sync is implied.
The Settings backup covers History/watchlist. Product catalog now has a separate
full backup for catalog inputs, revisions and linked alert rules. Review before
restoring; existing SKUs require explicit replacement selection and restored
monitors remain paused. Only archives from the same account can be restored.
No market evidence or credentials are imported. Limits are 10 MB, 5,000 products
and 50,000 revisions; exports reject oversized catalogs rather than truncating.
Keep Cloud database backups for the complete service. Deploy Cloud/Desktop v1.4.0.

## Alert rules

Open Alert rules from a monitored product or its catalog row. Set price-change
threshold/direction, minimum net margin, stale-collection hours and a cooldown.
Rules are revision checked and shared by manual checks and the Sentinel worker.
Alerts appear in Intelligence in the selected interface language. Invalid or
missing prices cannot trigger price/margin alerts; unsuccessful collections do
not reset the last valid timestamp. Cooldowns also bound collection-error alerts.
Stale checks run on Sentinel cycles, including watches beyond the current
collection batch. API and Sentinel must be updated together to v1.4.0.

## CSV batches

Use CSV batches to review UTF-8 files of up to 50 products (2 MB), select valid
rows and submit a durable Cloud batch. SKU, variants, costs, currencies, countries
and fee assumptions are shown before processing. Jobs continue after closing the
Desktop while the Cloud API is running. Failed products can be retried, results
can be exported, and completed batches can be deleted independently of History.
Both Cloud and Desktop require v1.2.0 for this workflow. See the root README for
supported headers and defaults.
