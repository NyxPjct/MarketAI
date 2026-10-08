# MarketAI — Pipeline de Release Windows

Este documento descreve o pipeline comercial de build e release do MarketAI.

## O que acontece automaticamente

- Push e Pull Request para `main`: executam testes Cloud/Desktop, compilação Python e validação do JavaScript.
- Execução manual de **Windows Build & Release**: gera o instalador Windows usando a URL HTTPS informada.
- Alteração em `.release/windows.json`: gera o instalador, SHA-256, provenance attestation e GitHub Release.
- Depois de um release, o workflow tenta atualizar `cloud/releases/windows-stable.json` para alimentar o atualizador do Desktop.

## Configuração do release automático

Edite `.release/windows.json` com uma URL HTTPS real, a nova tag e `create_release: true`.

O pipeline bloqueia builds comerciais que usem HTTP ou localhost.

## Code Signing opcional, mas recomendado

Adicione estes GitHub Actions Secrets:

```text
MARKETAI_SIGN_PFX_BASE64
MARKETAI_SIGN_PASSWORD
```

`MARKETAI_SIGN_PFX_BASE64` deve conter o certificado `.pfx` convertido para Base64. Se os dois secrets estiverem presentes, o pipeline assina `MarketAI.exe` e `MarketAI-Setup-v0.0.exe` e valida a assinatura antes de publicar.

## Build manual

No GitHub, abra **Actions → Windows Build & Release → Run workflow**. Informe:

- `cloud_url`: URL HTTPS real do MarketAI Cloud;
- `create_release`: `false` para apenas gerar um artifact ou `true` para criar release;
- `release_tag`: por exemplo `v1.0.1`.

## Release automático pelo repositório

Atualize `.release/windows.json` (por exemplo, de `v1.0.0` para `v1.0.1`) e faça push no `main`. O workflow gera o instalador e cria a tag/release correspondente.

## Artefatos

O workflow produz:

```text
MarketAI-Setup-v0.0.exe
MarketAI-Setup-v0.0.sha256
RELEASE-NOTES.txt
```

O nome do instalador permanece `MarketAI-Setup-v0.0.exe` por decisão de distribuição. A versão interna do produto é **MarketAI 1.0 SUPER FINAL**.

## Segurança

- nenhuma chave de marketplace ou IA entra no Desktop;
- URL de produção é validada como HTTPS;
- certificados de assinatura ficam apenas em GitHub Secrets;
- o `.pfx` é materializado apenas no runner temporário;
- cada instalador recebe SHA-256;
- o GitHub registra provenance attestation do binário produzido.
