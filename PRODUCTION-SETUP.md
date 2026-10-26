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

### Atualizar o serviço no Railway para v1.4.0

Publicar o instalador no GitHub não atualiza automaticamente um serviço Railway
que esteja desconectado do repositório ou com deploy automático desativado.

1. No serviço da API, confira a origem `NyxPjct/MarketAI`, branch `main`, e o
   diretório raiz `/cloud`. O Dockerfile e o `railway.toml` usam essa pasta como
   contexto. Preserve o domínio público, as variáveis e o banco existentes.
2. Faça um backup do PostgreSQL e publique o commit atual. Não recrie o banco.
   O startup adiciona as tabelas de Histórico, lotes, catálogo, restaurações e
   regras de alerta, sem alterar as tabelas anteriores. Mantenha a API ativa para
   os lotes; não inicie uma segunda
   cópia do processador de lotes. `BATCH_WORKER_ENABLED=0` desliga esse processador.
3. Atualize o worker Sentinel com a mesma origem e o mesmo `DATABASE_URL`, usando
   `python -m app.sentinel_worker`. Ele é necessário para coletas recorrentes.
4. Confira por HTTPS o `/health`: deve informar `version: 1.4.0` e
   `batch_processing: true` na API. O `/openapi.json` precisa incluir `/v1/catalog`,
   `/v1/batches`, `/v1/history`, `/v1/catalog/backup` e
   `/v1/intelligence/watches/{watch_id}/alert-rules`. As consultas privadas sem sessão devem continuar
   rejeitadas; não desative a autenticação para validar o serviço.
5. Com uma conta autorizada, confirme login, catálogo, lote e coleta real usando
   as integrações configuradas. Dados sintéticos dos testes não comprovam acesso
   aos provedores no ambiente hospedado.

Verificação em 26/10/2026: o domínio hospedado configurado respondeu aos endpoints
públicos como v1.0.5, sem as rotas acima. O ambiente de desenvolvimento não dispõe
de credencial ou projeto Railway vinculado para executar esse deploy. Essa
observação registra o estado encontrado; repita as verificações após publicar.

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
MarketAI-Setup-v1.4.0.exe
```

## 5. Release

Atualize .release/windows.json com:

```json
{
  "cloud_url": "https://api.seudominio.com",
  "release_tag": "v1.4.0",
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
