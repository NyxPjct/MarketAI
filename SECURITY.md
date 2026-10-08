# Segurança do MarketAI

## Relatando uma vulnerabilidade

Evite publicar detalhes de uma vulnerabilidade explorável em uma issue pública antes de existir uma correção.

Use os canais privados disponibilizados pelo mantenedor do repositório ou o recurso de Security Advisories do GitHub quando disponível.

Inclua:

- versão afetada;
- componente afetado;
- passos mínimos para reproduzir;
- impacto esperado;
- sugestão de correção, se houver.

## Secrets

Nunca envie:

- senhas;
- JWT secrets;
- tokens de Mercado Livre/eBay;
- chaves OpenAI;
- chaves SerpApi;
- certificados de Code Signing;
- arquivos .env reais;
- dumps de banco com dados pessoais.

## Contas

O MarketAI usa autenticação por conta e associa dados persistentes ao usuário autenticado. Mudanças que possam quebrar isolamento entre usuários devem ser tratadas como críticas.

## Dependências externas

APIs externas podem ficar indisponíveis, mudar contratos ou possuir limites próprios. Falhas dessas fontes não devem levar o MarketAI a fabricar dados.
