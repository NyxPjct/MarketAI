# Checklist de lançamento MarketAI v0.0

- [ ] Domínio HTTPS para API
- [ ] Railway/servidor publicado
- [ ] PostgreSQL com backup automático
- [ ] JWT_SECRET aleatório (64+ caracteres)
- [ ] ADMIN_API_KEY aleatória
- [ ] Mercado Livre token de produção
- [ ] eBay Client ID/Secret de produção
- [ ] SerpApi de produção
- [ ] OpenAI API key do servidor
- [ ] Mercado Pago em produção e webhook configurado
- [ ] Planos/preços confirmados
- [ ] E-mail de suporte e política de reembolso definidos
- [ ] Termos/Privacidade revisados juridicamente
- [ ] Certificado Code Signing
- [ ] `MARKETAI_CLOUD_URL` apontando para a API final durante o build
- [ ] manifesto de atualização com URL e SHA-256 do novo instalador
- [ ] teste de compra, renovação, cancelamento e cota
- [ ] teste em uma máquina Windows limpa

## Pagamentos multi-gateway

- [ ] Stripe conta comercial ativada e `STRIPE_SECRET_KEY` configurada
- [ ] Stripe webhook criado e segredo `STRIPE_WEBHOOK_SECRET` configurado
- [ ] PayPal Business em produção com Client ID/Secret
- [ ] PayPal webhook criado e `PAYPAL_WEBHOOK_ID` configurado
- [ ] Mercado Pago produção com Pix habilitado
- [ ] `MERCADOPAGO_WEBHOOK_SECRET` configurado
- [ ] `ALLOW_UNVERIFIED_WEBHOOKS=false`
- [ ] Testar Pix aprovado e webhook duplicado
- [ ] Testar cartão de crédito internacional
- [ ] Testar cartão de débito elegível
- [ ] Testar assinatura PayPal
- [ ] Testar cancelamento Stripe/Mercado Pago/PayPal
- [ ] Validar preços de cada plano em BRL/USD/EUR/GBP

## Admin Console

- [ ] `ADMIN_PANEL_ENABLED=true`
- [ ] `ADMIN_EMAIL` definido para uma conta exclusiva de administração
- [ ] `ADMIN_PASSWORD` com senha longa, única e armazenada como secret
- [ ] Login em `/admin` validado em HTTPS
- [ ] Testar bloqueio e liberação de uma conta de teste
- [ ] Testar ativação/desativação de dispositivo
- [ ] Gerar e resgatar uma licença B2B de teste
- [ ] Confirmar que alterações de plano persistem após reiniciar o Cloud
- [ ] Revisar eventos na aba Auditoria
- [ ] Configurar rate limit/proteção adicional para o login administrativo
