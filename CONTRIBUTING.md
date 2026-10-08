# Contribuindo com o MarketAI

Obrigado por ajudar o MarketAI Community.

## Princípios

- o projeto deve continuar útil sem paywall;
- dados simulados nunca devem ser apresentados como mercado real;
- mudanças que envolvam preço, margem ou recomendação precisam preservar transparência;
- secrets e credenciais reais nunca devem entrar em commits;
- cada conta deve acessar apenas os próprios dados.

## Fluxo sugerido

1. Faça um fork do repositório.
2. Crie uma branch para a mudança.
3. Adicione ou atualize testes quando necessário.
4. Rode os testes Cloud e Desktop.
5. Abra um Pull Request explicando o problema e a solução.

## Validação local

Cloud:

```bash
cd cloud
python -m pytest -q
```

Desktop:

```bash
cd desktop
python -m pytest -q
node --check frontend/app.js
```

## Código de terceiros

Só adicione dependências compatíveis com a licença do projeto e registre atribuições quando necessário.

## Licença das contribuições

Ao enviar uma contribuição, você concorda que ela será distribuída sob a Apache License 2.0 do projeto.
