# MarketAI v0.0 — Commercial Cloud Edition

Este pacote transforma o MarketAI em um software comercial por assinatura. Ele é dividido em dois componentes:

- `desktop/` — aplicativo Windows distribuído aos clientes;
- `cloud/` — API central que guarda as credenciais de marketplaces, autentica usuários, aplica licenças/cotas, recebe webhooks e executa as análises.

## O que mudou

O cliente não precisa mais possuir OpenAI, Mercado Livre, eBay ou SerpApi. Essas credenciais existem apenas no servidor. O desktop guarda somente a sessão da conta protegida com Windows DPAPI.

A edição inclui: cadastro/login, teste grátis de 7 dias/10 análises, três planos, limite de dispositivos, cota mensal, assinaturas Mercado Pago, licenças manuais B2B, rotação de refresh token, atualização via manifesto, API administrativa e MarketAI LIVE MARKET no servidor.

## Desenvolvimento local

### Cloud

```bat
cd cloud
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 9000
```

### Desktop

Em outro terminal:

```bat
cd desktop
set MARKETAI_CLOUD_URL=http://127.0.0.1:9000
run_desktop_dev.bat
```

## Produção

1. Crie um PostgreSQL.
2. Publique `cloud/` no Railway usando o `Dockerfile` e `railway.toml` incluídos.
3. Configure `DATABASE_URL`, `JWT_SECRET`, `ADMIN_API_KEY` e as chaves reais de mercado no servidor.
4. Configure `MERCADOPAGO_ACCESS_TOKEN`.
5. Aponte `PUBLIC_API_URL`, `PUBLIC_APP_URL` e o webhook para seu domínio HTTPS.
6. Antes do build, execute `set MARKETAI_CLOUD_URL=https://api.seudominio.com`. O `build_installer.bat` grava essa URL dentro do executável; o cliente final não precisa configurar nada.
7. Execute `desktop/build_installer.bat`. O nome continua `MarketAI-Setup-v0.0.exe`.

## Planos padrão

- Essencial: R$ 49,90/mês — 100 análises — 1 dispositivo
- Pro: R$ 99,90/mês — 500 análises — 2 dispositivos
- Business: R$ 199,90/mês — 2000 análises — 5 dispositivos

Os preços podem ser alterados por variáveis de ambiente antes do lançamento.

## Licenças B2B

Crie uma licença manual pela API administrativa:

```bash
curl -X POST https://api.seudominio.com/v1/admin/licenses \
  -H "x-admin-key: SUA_CHAVE_ADMIN" \
  -H "content-type: application/json" \
  -d '{"plan_code":"pro","duration_days":365,"max_redemptions":1}'
```

A chave em texto puro é mostrada apenas no momento da criação.

## Segurança

- senhas: Argon2;
- access token JWT curto;
- refresh token aleatório, persistido no servidor somente como SHA-256 e rotacionado;
- refresh/access token local protegido por DPAPI no Windows;
- credenciais de marketplaces nunca são entregues ao cliente;
- webhook Mercado Pago é sempre confirmado buscando a assinatura novamente na API do provedor;
- dispositivo usa UUID local aleatório, não fingerprint invasivo de hardware.

## Antes de vender publicamente

Ainda são dependências operacionais externas: domínio HTTPS, conta Mercado Pago produtiva, banco PostgreSQL, credenciais produtivas dos marketplaces, política comercial definitiva, e certificado de assinatura de código para reduzir alertas do SmartScreen.

---

## Pagamentos Multi-Gateway — atualização comercial

Esta edição adiciona uma camada de cobrança por país:

- **Pix (Brasil / Mercado Pago):** pagamento avulso que libera 30 dias do plano. Renovação manual.
- **Cartão internacional (Stripe):** crédito ou débito via Stripe Checkout, assinatura mensal recorrente.
- **PayPal:** assinatura mensal recorrente nos mercados/moedas suportados pela conta PayPal.
- **Mercado Pago:** assinatura recorrente brasileira preservada como opção local.

O cliente escolhe o país de cobrança e o MarketAI exibe somente os métodos configurados/adequados. As chaves ficam exclusivamente no Cloud.

Veja `PAYMENTS-SETUP.md` para configuração dos gateways e webhooks.

---

## Admin Console — operação comercial

Esta edição inclui o painel administrativo completo em `/admin`.

O painel centraliza clientes, assinaturas, pagamentos, licenças, dispositivos, consumo, planos e auditoria. O acesso usa uma conta administrativa própria; a antiga `ADMIN_API_KEY` continua disponível apenas para automações/API legada e não é exposta no navegador.

Configuração mínima:

```env
ADMIN_PANEL_ENABLED=true
ADMIN_EMAIL=admin@seudominio.com
ADMIN_PASSWORD=<senha longa e exclusiva>
ADMIN_NAME=Administrador MarketAI
```

Após publicar o Cloud:

`https://api.seudominio.com/admin`

Consulte `ADMIN-PANEL.md` para o guia completo.
