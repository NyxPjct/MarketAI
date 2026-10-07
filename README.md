# MarketAI

> **MarketAI v0.0** — plataforma de inteligência comercial para análise de produtos, preços, margem, mercado e oportunidades de venda.

O MarketAI foi criado para ajudar vendedores a entenderem **quanto um produto custa no mercado, quanto vale a pena cobrar, qual a margem estimada e quais fontes sustentam a análise**.

Esta é a **base inicial do projeto**, publicada para continuidade do desenvolvimento.

## Preview

### Interface principal

![MarketAI Dashboard](docs/images/marketai-dashboard.svg)

### Nova análise

![MarketAI Nova Análise](docs/images/marketai-analysis.svg)

### Admin Console

![MarketAI Admin Console](docs/images/marketai-admin.svg)

> As imagens acima são previews da interface atual do projeto. O visual continuará evoluindo junto com as próximas versões.

## Principais recursos

- Pesquisa e comparação de preços por fonte de mercado
- Identificação de produto, variante, volume, capacidade e especificações
- Filtros para evitar comparar produtos incompatíveis
- Match Score para auditar anúncios utilizados
- Cálculo de custo real, break-even, margem, ROI e preço sugerido
- Simulador de preço
- Mercado por país e moeda
- Cotação cambial
- Mercado Livre, eBay e Google Shopping/SerpApi
- Reconhecimento assistido por IA
- Histórico e produtos monitorados
- MarketAI Desktop para Windows
- MarketAI Cloud
- Login, planos, cotas e dispositivos
- Licenças comerciais
- Pagamentos via Mercado Pago / Pix, Stripe e PayPal
- Painel administrativo
- Auditoria administrativa
- Atualização automática do aplicativo

## Estrutura

```text
MarketAI
├── desktop/              # Cliente desktop Windows
├── cloud/                # API, autenticação, assinaturas e serviços
├── docs/                 # Documentação e previews
├── installer/            # Build/instalador Windows
├── tests/                # Testes
├── build_installer.bat   # Gera MarketAI-Setup-v0.0.exe
└── README.md
```

## Arquitetura comercial

```text
MarketAI Desktop
       │
       ▼
MarketAI Cloud
       │
       ├── Mercado / IA / Câmbio
       ├── Contas e dispositivos
       ├── Planos e cotas
       ├── Licenças
       ├── Pagamentos
       └── Admin Console
```

As chaves das integrações comerciais ficam no **servidor**, e não devem ser distribuídas dentro do aplicativo do cliente.

## Desenvolvimento local

Consulte os arquivos de documentação do projeto antes de executar a stack:

- `PRODUCTION-SETUP.md`
- `PAYMENTS-SETUP.md`
- `ADMIN-PANEL.md`
- `LAUNCH-CHECKLIST.md`

O repositório inclui arquivos `.env.example` para referência. **Nunca publique credenciais reais, tokens, chaves privadas ou arquivos `.env`.**

## Desktop Windows

O projeto está configurado para gerar:

```text
MarketAI-Setup-v0.0.exe
```

O build final do executável/instalador deve ser realizado em um ambiente Windows.

## Status

🚧 **v0.0 — desenvolvimento ativo**

Esta versão representa a fundação inicial do produto. As próximas etapas serão implementadas e versionadas neste repositório.

## Segurança

O repositório não deve conter:

- `.env` com credenciais reais
- bancos locais de produção/desenvolvimento
- tokens de marketplaces
- chaves OpenAI/Stripe/PayPal/Mercado Pago
- certificados de assinatura
- arquivos temporários de build

## Projeto

Desenvolvido como parte do **MarketAI**.

---

**MarketAI v0.0**
