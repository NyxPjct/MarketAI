# MarketAI Community — Admin Console

O MarketAI Cloud possui um painel administrativo para operação da instância em:

```text
https://api.seudominio.com/admin
```

## Primeiro acesso

Configure no ambiente do Cloud:

```env
ADMIN_PANEL_ENABLED=true
ADMIN_EMAIL=admin@seudominio.com
ADMIN_PASSWORD=<senha longa e exclusiva>
ADMIN_NAME=Administrador MarketAI
```

A conta administrativa serve para segurança e operação do serviço. Ela não é
necessária para cobrar usuários: a edição Community é gratuita.

## Uso recomendado

O painel pode ser usado para acompanhar usuários, bloquear ou liberar contas em
casos de segurança/abuso, revisar dispositivos, consumo técnico e auditoria.

Algumas tabelas e telas de assinatura, pagamentos, planos e licenças podem
continuar presentes por compatibilidade com versões anteriores. **Esses registros
não controlam o direito de uso na edição Community**: contas autenticadas recebem
o entitlement Community gratuito.

## Segurança

- use HTTPS;
- use uma senha administrativa exclusiva;
- proteja /admin com uma camada adicional quando possível;
- aplique rate limit no login administrativo;
- mantenha backups do PostgreSQL;
- revise a auditoria periodicamente;
- nunca compartilhe a conta administrativa;
- não publique ADMIN_PASSWORD, JWT_SECRET ou ADMIN_API_KEY.

## Desenvolvimento local

```env
ADMIN_EMAIL=owner@marketai.local
ADMIN_PASSWORD=UmaSenhaDeTesteMuitoForte123!
ADMIN_PANEL_ENABLED=true
```

Inicie o Cloud e abra:

```text
http://127.0.0.1:9000/admin
```
