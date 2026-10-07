# MarketAI v0.0 — Pagamentos Multi-Gateway

A edição comercial usa quatro experiências de pagamento:

1. **Pix (Mercado Pago / Brasil)** — pagamento avulso. Cada confirmação libera 30 dias do plano. Não existe renovação Pix automática nesta implementação.
2. **Cartão de crédito/débito internacional (Stripe Checkout)** — assinatura mensal recorrente. O cliente informa o cartão somente na página hospedada pelo Stripe; o MarketAI não recebe nem armazena número do cartão/CVV.
3. **PayPal** — assinatura mensal recorrente via PayPal. Os planos PayPal são provisionados automaticamente por plano/moeda na primeira utilização e armazenados em `provider_plans`.
4. **Mercado Pago** — assinatura recorrente brasileira usando `preapproval`, preservada da arquitetura anterior.

## Limites reais de alcance

“Global” não significa que um gateway consegue aprovar literalmente todo cartão de todo país. A aceitação depende do país da conta do comerciante, moeda, bandeira, banco emissor, sanções/regras locais, análise antifraude e disponibilidade do próprio provedor. O MarketAI oferece roteamento internacional, mas não promete aprovação universal.

Pix é um arranjo de pagamentos brasileiro. Por isso, ele aparece somente quando o país de cobrança é Brasil.

## Stripe

Configure no Cloud:

```env
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

Webhook:

```text
POST https://api.seudominio.com/v1/webhooks/stripe
```

Eventos recomendados:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`

O webhook é verificado por HMAC usando `STRIPE_WEBHOOK_SECRET` e tolerância de 5 minutos.

## PayPal

Configure:

```env
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_WEBHOOK_ID=...
PAYPAL_MODE=live
```

Durante desenvolvimento use `PAYPAL_MODE=sandbox`.

Webhook:

```text
POST https://api.seudominio.com/v1/webhooks/paypal
```

O MarketAI usa a API oficial de verificação de assinatura de webhook do PayPal antes de sincronizar a assinatura.

## Mercado Pago + Pix

Configure:

```env
MERCADOPAGO_ACCESS_TOKEN=APP_USR-...
MERCADOPAGO_WEBHOOK_URL=https://api.seudominio.com/v1/webhooks/mercadopago
MERCADOPAGO_WEBHOOK_SECRET=...
```

O mesmo webhook recebe eventos de assinatura e pagamentos Pix. A origem é validada com a assinatura HMAC `x-signature` quando o segredo estiver configurado.

## Segurança

- O desktop nunca recebe as chaves secretas dos gateways.
- Checkout de cartão ocorre no Stripe-hosted Checkout.
- PayPal ocorre no ambiente do PayPal.
- Pix é criado pelo servidor; o desktop recebe apenas QR/copia-e-cola e/ou URL de pagamento.
- Webhooks são reconsultados no provedor antes de conceder assinatura sempre que aplicável.
- `ALLOW_UNVERIFIED_WEBHOOKS=false` deve permanecer em produção.
- Nenhum CVV ou PAN de cartão é armazenado pelo MarketAI.

## Preços por moeda

O servidor possui preços padrão BRL/USD/EUR/GBP/CAD/MXN/JPY e alguns outros. Você pode sobrescrever qualquer valor usando:

```text
PLAN_<PLANO>_PRICE_<MOEDA>
```

Exemplo:

```env
PLAN_PRO_PRICE_USD=19.99
PLAN_PRO_PRICE_EUR=18.99
```

## Pix e renovação

Pix é tratado como compra de 30 dias. Depois de aprovado:

- plano fica `active`;
- `current_period_end` recebe +30 dias;
- pagamentos Pix adicionais acumulam a validade;
- não existe cancelamento de renovação porque não há débito automático.
