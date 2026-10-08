# MarketAI Community — publicação e self-hosting

## 1. Cloud

A pasta cloud/ contém Dockerfile e railway.toml.

Configure pelo menos:

```env
DATABASE_URL=postgresql+psycopg://...
JWT_SECRET=<segredo aleatório longo>
PUBLIC_API_URL=https://api.seudominio.com
PUBLIC_APP_URL=https://api.seudominio.com
```

As integrações de mercado são opcionais:

```env
OPENAI_API_KEY=
MERCADOLIVRE_ACCESS_TOKEN=
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=
SERPAPI_KEY=
```

O MarketAI Community não depende de gateway de pagamento.

## 2. Banco

Use PostgreSQL em produção. Cada usuário possui sua própria conta e os dados persistentes do Intelligence Core são relacionados ao user_id.

## 3. Sentinel

Execute em um worker separado:

```bash
python -m app.sentinel_worker
```

## 4. Desktop

No Windows:

```bat
cd desktop
set MARKETAI_CLOUD_URL=https://api.seudominio.com
build_installer.bat
```

O nome do instalador acompanha a versão definida em desktop/installer/MarketAI.iss.

Exemplo:

```text
MarketAI-Setup-v1.0.2.exe
```

## 5. Release

Atualize .release/windows.json com:

```json
{
  "cloud_url": "https://api.seudominio.com",
  "release_tag": "v1.0.2",
  "create_release": true
}
```

O GitHub Actions gera o EXE, SHA-256, attestation e GitHub Release.

## 6. Code Signing

Opcional, mas recomendado para releases públicos no Windows:

```text
MARKETAI_SIGN_PFX_BASE64
MARKETAI_SIGN_PASSWORD
```

## 7. Segurança

- nunca publique .env;
- mantenha JWT_SECRET forte;
- use HTTPS;
- proteja o painel administrativo;
- mantenha PostgreSQL com backup;
- aplique rate limiting se hospedar uma instância pública;
- lembre que APIs externas podem possuir suas próprias cotas ou custos.

## 8. Administração

O Admin Console pode ser habilitado com ADMIN_PANEL_ENABLED=true. Na edição Community ele deve ser usado para administração de usuários, segurança, auditoria e operação da instância — não para vender planos.

## 9. Licença

O projeto é distribuído sob Apache License 2.0. Consulte [LICENSE](LICENSE).
