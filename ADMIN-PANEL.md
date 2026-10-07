# MarketAI Admin Console

O MarketAI Cloud agora possui um painel administrativo web próprio, servido pelo mesmo backend em:

`https://api.seudominio.com/admin`

## Primeiro acesso

No ambiente do Cloud configure:

```env
ADMIN_PANEL_ENABLED=true
ADMIN_EMAIL=admin@seudominio.com
ADMIN_PASSWORD=<senha longa e exclusiva>
ADMIN_NAME=Administrador MarketAI
```

Na inicialização, o Cloud cria ou sincroniza essa conta como `role=admin`. A senha administrativa é controlada pelo ambiente do servidor e nunca precisa ser incluída no desktop distribuído aos clientes.

Use HTTPS em produção e não reutilize a senha do e-mail, Stripe, PayPal, Mercado Pago ou Railway.

## O que o painel permite

### Visão geral

- total de clientes;
- clientes ativos/bloqueados;
- novos cadastros dos últimos 30 dias;
- assinaturas ativas, trials e contas `past_due`;
- dispositivos ativos;
- análises consumidas no mês;
- receita confirmada registrada nos últimos 30 dias, separada por moeda;
- distribuição por plano e gateway;
- clientes e transações recentes.

`Receita confirmada registrada` significa somente transações que o Cloud marcou como efetivamente creditadas. O painel não soma checkouts pendentes como faturamento.

### Clientes

É possível buscar por nome, e-mail ou ID e:

- abrir o perfil completo;
- bloquear, suspender ou liberar uma conta;
- ver assinatura atual;
- ver consumo de análises;
- zerar a cota consumida no mês;
- conceder um plano manual por determinado período;
- visualizar e ativar/desativar dispositivos;
- visualizar pagamentos recentes.

Uma assinatura recorrente ativa em Mercado Pago, Stripe ou PayPal não pode ser sobrescrita manualmente pelo painel. Primeiro cancele a recorrência no fluxo apropriado para evitar cobrança duplicada.

### Assinaturas

Lista plano, status, gateway, vencimento e identificador externo da assinatura.

### Pagamentos

Lista transações registradas por:

- Mercado Pago;
- Pix;
- Stripe;
- PayPal.

Inclui valor, moeda, status e indicação de crédito confirmado.

### Licenças

O painel gera chaves `MAI-...` para vendas B2B, cortesia ou contrato anual. A chave completa aparece somente no momento da criação; o banco mantém apenas seu hash e um pequeno sufixo para identificação.

Também é possível ativar ou desativar licenças já emitidas.

### Dispositivos

Exibe computadores registrados por cliente e permite desativar/reativar um dispositivo individualmente.

### Planos

Permite alterar:

- preço base em BRL;
- cota mensal de análises;
- limite de dispositivos;
- disponibilidade do plano.

Por padrão essas mudanças persistem após reiniciar o servidor. Se `SYNC_PLAN_DEFAULTS_ON_STARTUP=true`, os valores padrão/variáveis de ambiente voltam a sobrescrever os planos a cada boot.

Preços internacionais específicos continuam configuráveis por variáveis como `PLAN_PRO_PRICE_USD` e `PLAN_PRO_PRICE_EUR`.

### Auditoria

Toda ação administrativa importante gera evento `admin.*`, incluindo:

- login administrativo;
- bloqueio/liberação de conta;
- alteração manual de assinatura;
- reset de uso;
- criação/desativação de licença;
- ativação/desativação de dispositivo;
- alteração de plano.

## Segurança

O navegador não recebe `ADMIN_API_KEY`. O painel usa login administrativo e JWT de curta duração.

Recomendações adicionais de produção:

- publicar somente por HTTPS;
- usar senha administrativa longa e exclusiva;
- aplicar rate limit no proxy/Railway/Cloudflare para `/v1/admin/auth/login`;
- restringir `/admin` por VPN/IP allowlist quando possível;
- manter backups automáticos do PostgreSQL;
- revisar o log de auditoria periodicamente;
- nunca compartilhar a conta administrativa.

## Desenvolvimento local

No `.env` de `cloud/`:

```env
ADMIN_EMAIL=owner@marketai.local
ADMIN_PASSWORD=UmaSenhaDeTesteMuitoForte123!
ADMIN_PANEL_ENABLED=true
```

Inicie:

```bat
start_cloud_dev.bat
```

Abra:

`http://127.0.0.1:9000/admin`
