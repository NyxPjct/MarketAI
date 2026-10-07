# MarketAI Desktop v0.0 — Commercial Cloud Client

O desktop agora é cliente do MarketAI Cloud. Ele não exige que cada comprador possua chaves de marketplace/IA.

## Desenvolvimento
Defina `MARKETAI_CLOUD_URL=http://127.0.0.1:9000` e execute `run_desktop_dev.bat`.

## Build comercial
Antes do build final, defina a URL HTTPS da API:

```bat
set MARKETAI_CLOUD_URL=https://api.seudominio.com
build_installer.bat
```

O instalador gerado continua se chamando `MarketAI-Setup-v0.0.exe`.

A sessão é protegida com Windows DPAPI. Histórico e monitorados permanecem no computador; conta, plano, licença, cota e dispositivos são controlados pelo servidor.
