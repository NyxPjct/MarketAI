# Checklist de lançamento — MarketAI Community

- [ ] Cloud publicado em HTTPS
- [ ] PostgreSQL com backup
- [ ] JWT_SECRET forte e exclusivo
- [ ] nenhuma credencial real no repositório
- [ ] login e criação de conta testados
- [ ] isolamento entre contas testado
- [ ] análise gratuita sem paywall validada
- [ ] todos os módulos do Intelligence Core acessíveis
- [ ] Sentinel Worker ativo
- [ ] integrações externas desejadas configuradas
- [ ] falha de fonte externa não gera dados fictícios
- [ ] README e LICENSE revisados
- [ ] versão atualizada em Desktop/installer
- [ ] instalador com nome MarketAI-Setup-vX.Y.Z.exe
- [ ] SHA-256 validado
- [ ] auto-update aponta para o instalador da versão correta
- [ ] CI verde
- [ ] teste em Windows limpo quando possível
- [ ] Code Signing configurado, se disponível

## Instância pública

Se você operar um MarketAI Cloud público, considere também rate limiting,
observabilidade, backups, política de privacidade, canal de suporte e capacidade
de infraestrutura.

## Custos externos

O MarketAI não cobra assinatura. Hospedagem e APIs de terceiros podem ter
custos próprios para quem opera uma instância pública ou configura integrações.
