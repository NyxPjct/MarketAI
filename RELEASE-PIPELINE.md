# MarketAI — Pipeline de Release Windows

O pipeline gera builds públicos do MarketAI Community.

## CI

Pushes e Pull Requests para main executam:

- testes Cloud;
- testes Desktop;
- compilação Python;
- validação do JavaScript.

## Release automático

Edite .release/windows.json:

```json
{
  "cloud_url": "https://api.seudominio.com",
  "release_tag": "v1.0.2",
  "create_release": true
}
```

O workflow usa a tag para definir o nome dos artefatos.

Exemplo:

```text
v1.0.2
MarketAI-Setup-v1.0.2.exe
MarketAI-Setup-v1.0.2.sha256
```

Não existe mais um nome fixo de instalador v0.0.

## Build manual

Actions → Windows Build & Release → Run workflow.

Informe:

- cloud_url: URL HTTPS do MarketAI Cloud;
- create_release: true para publicar GitHub Release;
- release_tag: por exemplo v1.0.2.

## Segurança

O build oficial:

- exige HTTPS;
- gera SHA-256;
- publica build provenance attestation;
- pode aplicar Code Signing;
- não inclui secrets do Cloud no executável.

## Code Signing

Secrets opcionais:

```text
MARKETAI_SIGN_PFX_BASE64
MARKETAI_SIGN_PASSWORD
```

Se configurados, MarketAI.exe e o instalador versionado são assinados e validados antes da publicação.

## Auto-update

Depois do release, o workflow atualiza cloud/releases/windows-stable.json com:

- versão;
- URL do instalador versionado;
- SHA-256;
- URL da release;
- data de publicação.

O Desktop só inicia uma atualização após validar o hash.
