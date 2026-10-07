# MarketAI v0.0 — publicação comercial

## 1. Publicar o Cloud

A pasta `cloud/` já contém `Dockerfile` e `railway.toml`.

Crie um PostgreSQL e configure no serviço Cloud:

```env
DATABASE_URL=postgresql+psycopg://...
JWT_SECRET=<segredo aleatório longo>
ADMIN_API_KEY=<chave admin aleatória>
PUBLIC_API_URL=https://api.seudominio.com
PUBLIC_APP_URL=https://seudominio.com

OPENAI_API_KEY=...
MERCADOLIVRE_ACCESS_TOKEN=...
EBAY_CLIENT_ID=...
EBAY_CLIENT_SECRET=...
SERPAPI_KEY=...

MERCADOPAGO_ACCESS_TOKEN=...
MERCADOPAGO_WEBHOOK_URL=https://api.seudominio.com/v1/webhooks/mercadopago
```

Nunca coloque essas chaves no computador dos clientes.

## 2. Mercado Pago

O backend cria assinaturas recorrentes e guarda o identificador retornado pelo Mercado Pago. Configure notificações de Assinaturas/Pagamentos para:

`https://api.seudominio.com/v1/webhooks/mercadopago`

O MarketAI não usa o conteúdo do webhook como prova de pagamento: ao recebê-lo, consulta novamente a assinatura na API do Mercado Pago antes de alterar o direito de uso.

## 3. Teste ponta a ponta

Antes de vender:

1. criar uma conta nova no desktop;
2. confirmar o trial;
3. fazer uma análise;
4. assinar Essencial/Pro/Business em ambiente de teste;
5. sincronizar a assinatura no desktop;
6. testar cota mensal;
7. tentar um segundo dispositivo acima do limite;
8. cancelar a assinatura;
9. ativar uma licença manual;
10. verificar que nenhuma chave de marketplace aparece no cliente.

## 4. Gerar o instalador comercial

No Prompt de Comando do Windows:

```bat
cd desktop
set MARKETAI_CLOUD_URL=https://api.seudominio.com
build_installer.bat
```

Resultado:

`desktop\dist-installer\MarketAI-Setup-v0.0.exe`

Também será gerado:

`desktop\dist-installer\MarketAI-Setup-v0.0.sha256`

## 5. Publicar atualização

Hospede o novo instalador em HTTPS e execute no servidor/repositório:

```bash
cd cloud
python tools/publish_release.py ../desktop/dist-installer/MarketAI-Setup-v0.0.exe \
  --version 0.0.1 \
  --url https://downloads.seudominio.com/MarketAI-Setup-v0.0.1.exe \
  --notes "Correções e melhorias"
```

Publique o `releases/windows-stable.json` atualizado junto ao Cloud. O desktop verifica a versão, baixa o instalador, confirma o SHA-256 e só então inicia a atualização.

## 6. Licença B2B sem assinatura recorrente

```bash
curl -X POST https://api.seudominio.com/v1/admin/licenses \
  -H "x-admin-key: SUA_CHAVE_ADMIN" \
  -H "content-type: application/json" \
  -d '{"plan_code":"pro","duration_days":365,"max_redemptions":1}'
```

A chave `MAI-...` retornada pode ser entregue ao cliente. O servidor armazena apenas o hash da chave.

## 7. Antes do lançamento público

Use um certificado de Code Signing para assinar `MarketAI.exe` e `MarketAI-Setup-v0.0.exe`, revise juridicamente Termos/Privacidade, defina suporte/reembolso e habilite backups do PostgreSQL.

## 8. Configurar pagamentos internacionais

Além do Mercado Pago, configure Stripe e PayPal no ambiente do Cloud.

### Stripe — cartão crédito/débito internacional

```env
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

Cadastre o webhook:

```text
https://api.seudominio.com/v1/webhooks/stripe
```

Eventos: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`.

### PayPal

```env
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_WEBHOOK_ID=...
PAYPAL_MODE=live
```

Webhook:

```text
https://api.seudominio.com/v1/webhooks/paypal
```

### Mercado Pago + Pix

```env
MERCADOPAGO_ACCESS_TOKEN=...
MERCADOPAGO_WEBHOOK_URL=https://api.seudominio.com/v1/webhooks/mercadopago
MERCADOPAGO_WEBHOOK_SECRET=...
```

Pix é exibido somente para cobrança no Brasil e libera 30 dias por pagamento aprovado. Não é tratado como débito recorrente.

Mantenha obrigatoriamente:

```env
ALLOW_UNVERIFIED_WEBHOOKS=false
```

Consulte também `PAYMENTS-SETUP.md`.

## 9. Painel administrativo

Adicione ao ambiente do Cloud:

```env
ADMIN_PANEL_ENABLED=true
ADMIN_EMAIL=admin@seudominio.com
ADMIN_PASSWORD=<senha forte e exclusiva>
ADMIN_NAME=Administrador MarketAI
SYNC_PLAN_DEFAULTS_ON_STARTUP=false
```

Depois do deploy, acesse:

`https://api.seudominio.com/admin`

A senha definida em `ADMIN_PASSWORD` é a credencial de login do dono/administrador. O Cloud sincroniza essa senha no boot; portanto alterações futuras devem ser feitas no secret do servidor, não no desktop.

Em produção, proteja `/admin` com HTTPS e, se possível, uma camada adicional como Cloudflare Access, VPN ou allowlist de IP.
