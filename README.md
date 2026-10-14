# MarketAI Community

![MarketAI CI](https://github.com/NyxPjct/MarketAI/actions/workflows/ci.yml/badge.svg)
![Windows Build & Release](https://github.com/NyxPjct/MarketAI/actions/workflows/windows-release.yml/badge.svg)

> **Free and open-source market intelligence for pricing, margins, competition, monitoring and better product decisions.**

**MarketAI Community** is a free and open-source market intelligence platform designed for sellers, buyers, small businesses, analysts, students and teams that need better product decisions without a paywall.

Each person uses an individual account, with separate analyses, monitored products, history, snapshots and alerts.

**No paid plans. No trial limits. No monthly analysis quota. No Premium tier.**

> **Core rule:** MarketAI does not fabricate market prices, stock, sales or trends. If the available evidence is not strong enough, the app says so instead of inventing an answer.

## Download for Windows

Current version: **v1.0.5**

```text
MarketAI-Setup-v1.0.5.exe
```

Direct download:

- [MarketAI-Setup-v1.0.5.exe](https://github.com/NyxPjct/MarketAI/releases/download/v1.0.5/MarketAI-Setup-v1.0.5.exe)
- [SHA-256 file](https://github.com/NyxPjct/MarketAI/releases/download/v1.0.5/MarketAI-Setup-v1.0.5.sha256)
- [GitHub Release v1.0.5](https://github.com/NyxPjct/MarketAI/releases/tag/v1.0.5)

SHA-256:

```text
5a731338f2418146d022ae3bf2664f0dcb6d94b9e14b321459f774f837c149ac
```

All releases:

https://github.com/NyxPjct/MarketAI/releases

## Languages

**English is the default language.**

The entire Desktop interface can be switched instantly between:

- English
- Português (Brasil)
- Deutsch
- Español
- Français

The selected language is saved on the device and reused the next time MarketAI starts.

The language switch is available on the login screen and inside **Settings**.

Language changes also update interface labels, forms, account screens, Intelligence Core messages, dynamic UI states, date formatting and currency formatting.

## Login first

MarketAI starts on the **Sign in / Create account** screen.

Accounts are used to keep each user's data separated, including:

- analyses;
- history;
- monitored products;
- snapshots;
- alerts;
- devices;
- Intelligence Core context.

After authentication, the user enters the main workspace.

## 100% free

MarketAI Community unlocks:

- unlimited product analyses inside MarketAI;
- MarketAI Intelligence Core;
- Market Score 0–100;
- Data Quality Score A–E;
- Profit Engine;
- Sentinel;
- Radar;
- Forecast;
- Autopilot;
- Copilot;
- alerts;
- local history;
- multiple devices per account.

There is no active checkout in the Community edition.

Some legacy billing code remains in the repository for historical compatibility, but it does not control access to Community features.

## Open source

MarketAI is distributed under the **Apache License 2.0**.

You can study, use, modify and redistribute the software according to the license terms.

Important files:

- [LICENSE](LICENSE)
- [NOTICE](NOTICE)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)

## Screenshots — MarketAI v1.0.5

The screenshots below are generated automatically from the current Desktop interface in **English** at **1600×900**.

Demo values are used only to present the UI. They are not presented as real market evidence.

### Login / account creation

![MarketAI v1.0.5 — Login](docs/screenshots/01-login-community-v1.0.5.png)

### Dashboard / New analysis

![MarketAI v1.0.5 — Dashboard](docs/screenshots/02-dashboard-v1.0.5.png)

### Intelligence Core

![MarketAI v1.0.5 — Intelligence Core](docs/screenshots/03-intelligence-core-v1.0.5.png)

### My account

![MarketAI v1.0.5 — My account](docs/screenshots/04-my-account-v1.0.5.png)

### Settings

The Settings screen includes the interface language selector.

![MarketAI v1.0.5 — Settings](docs/screenshots/05-settings-v1.0.5.png)

### Account-created confirmation

![MarketAI v1.0.5 — Account created](docs/screenshots/06-account-created-modal-v1.0.5.png)

## Intelligence Core

### Market Score

A 0–100 score that combines data quality, expected margin, price headroom and market depth.

### Data Quality Score

An A–E quality grade that shows how strongly the analysis is supported by compatible market evidence.

### Profit Engine

Calculates:

```text
Selling price
- unit cost
- fixed cost per unit
- marketplace fee
- taxes
- advertising
- payment fee
- estimated losses
= net profit
```

It also reports net margin, ROI and break-even price.

### Sentinel

Tracks monitored products and stores real market snapshots.

When the worker is running, monitoring can continue even while the Desktop app is closed.

### Radar

Ranks opportunities from real snapshots collected by Sentinel.

### Forecast

Builds projections from historical snapshots.

If there is not enough history, MarketAI does not create a fake trend.

### Autopilot

Suggests prices while respecting strategy and minimum margin constraints.

### Copilot

Answers questions using the real context available to the user's account.

When an external AI provider is not configured, MarketAI can fall back to deterministic logic instead of inventing facts.

## Product and market analysis

MarketAI supports:

- product name and variant matching;
- image-assisted identification;
- optional GTIN / EAN / UPC;
- brand and model comparison;
- perfume concentration and volume;
- storage capacity;
- power / wattage;
- kit, sample, decant, tester and replica rejection;
- Match Score;
- compatible vs discarded listing separation;
- outlier handling;
- ambiguous-variant blocking;
- insufficient-sample blocking;
- currency conversion;
- landed unit cost;
- pricing strategies;
- margin simulation;
- local history;
- CSV and PDF-oriented exports.

## External data sources

The project contains support for integrations such as:

- Mercado Livre / Mercado Libre;
- eBay;
- Google Shopping through SerpApi;
- AI-assisted product identification and Copilot features.

**MarketAI itself is free**, but external services can have their own credentials, quotas, pricing or terms.

Open-source software cannot make a paid third-party API free.

Sensitive credentials should remain on the Cloud or in a self-hosted environment and must never be committed to the repository.

## Architecture

```text
┌──────────────────────────────┐
│     MarketAI Desktop         │
│ Windows · Account login      │
│ EN / PT-BR / DE / ES / FR    │
└──────────────┬───────────────┘
               │ HTTPS / JWT
               ▼
┌──────────────────────────────┐
│       MarketAI Cloud         │
│ FastAPI + authentication     │
├──────────────────────────────┤
│ Market Engine                │
│ Intelligence Core            │
│ Sentinel Worker              │
│ Accounts / devices           │
│ Admin / audit                │
└──────────────┬───────────────┘
               │
        ┌──────┴──────┐
        ▼             ▼
   PostgreSQL     External APIs
```

## Security and account isolation

- Argon2 password hashing;
- short-lived JWT access tokens;
- rotated refresh tokens stored as hashes;
- Windows DPAPI protection for local session data;
- random installation UUID instead of invasive hardware fingerprinting;
- Intelligence Core data scoped by authenticated user;
- local history and watchlist scoped by account;
- secrets excluded from the repository;
- HTTPS required for official release builds.

## Community Cloud

Current hosted Cloud instance:

```text
https://marketai-cloud-production.up.railway.app
```

Health endpoint:

```text
https://marketai-cloud-production.up.railway.app/health
```

The hosted environment uses:

- MarketAI Cloud;
- PostgreSQL;
- MarketAI Sentinel Worker.

The project can also be self-hosted.

## Local development

### Cloud

```bat
cd cloud
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 9000
```

### Sentinel Worker

```bat
cd cloud
.venv\Scripts\activate
python -m app.sentinel_worker
```

### Desktop

```bat
cd desktop
set MARKETAI_CLOUD_URL=http://127.0.0.1:9000
run_desktop_dev.bat
```

## Windows builds

Installer filenames follow the application version automatically.

```text
v1.0.5 -> MarketAI-Setup-v1.0.5.exe
v1.1.0 -> MarketAI-Setup-v1.1.0.exe
v2.0.0 -> MarketAI-Setup-v2.0.0.exe
```

Local build:

```bat
cd desktop
build_installer.bat
```

## CI/CD

Pushes and Pull Requests run:

- Cloud tests;
- Desktop tests;
- Python compilation checks;
- JavaScript syntax validation.

Updating `.release/windows.json` can trigger the Windows release pipeline and publish:

```text
MarketAI-Setup-vX.Y.Z.exe
MarketAI-Setup-vX.Y.Z.sha256
RELEASE-NOTES.txt
```

The pipeline also supports:

- SHA-256 verification;
- build provenance attestation;
- optional Windows Code Signing;
- automatic GitHub Releases;
- auto-update manifest publishing.

The screenshot workflow opens the current MarketAI Desktop UI with Playwright, forces **English**, validates all five supported languages, captures the current interface and commits the resulting images to `docs/screenshots/`.

See [RELEASE-PIPELINE.md](RELEASE-PIPELINE.md).

## Project structure

```text
MarketAI/
├── cloud/
│   ├── app/
│   ├── admin/
│   ├── tests/
│   └── docker-compose.yml
├── desktop/
│   ├── backend/
│   ├── frontend/
│   │   ├── app.js
│   │   ├── i18n.js
│   │   ├── index.html
│   │   └── style.css
│   ├── installer/
│   ├── tests/
│   └── docs/
├── docs/screenshots/
├── tools/
├── LICENSE
├── NOTICE
├── CONTRIBUTING.md
└── SECURITY.md
```

## Project philosophy

The goal is straightforward:

> build useful market intelligence software for people who work with products, without locking the core experience behind a paywall.

Contributions are welcome.

---

### MarketAI Community

**Find. Understand. Price. Monitor. Decide.**
