# ADR-0012: Acesso local por loopback e token por inicialização

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
O backend executa código arbitrário em kernels e manipula arquivos locais. Ele é acessado por um navegador na mesma máquina, onde outras páginas web também podem tentar requisições para `localhost`.

## Decisão
- O servidor escuta sempre em `127.0.0.1` (`HOST`), sem opção de configuração ("intentionally no way to configure it", em `config.py`). A porta padrão é 8765 e pode ser alterada por `--port`.
- Um token aleatório (`secrets.token_urlsafe(32)`) é gerado a cada inicialização e impresso na URL de abertura (`/?token=...`).
- Rotas REST exigem o token por cabeçalho `Authorization: Bearer`, cookie `notisbook_token` (`HttpOnly`, `SameSite=Strict`) ou `?token=` (que grava o cookie). A comparação usa `secrets.compare_digest`.
- O WebSocket valida token, `Origin` e `Host` antes do `accept()`; `require_trusted_host` recusa `Host` fora de `127.0.0.1:<porta>`/`localhost:<porta>`, como proteção contra DNS rebinding.
- O log de acesso do uvicorn é desligado porque o token trafega em `?token=`.
- Documentação OpenAPI (`/docs`, `/redoc`, `/openapi.json`) é desativada.

A motivação para desligar o access log e para a validação de `Host` está registrada em comentários do código; a motivação histórica das demais escolhas não foi recuperada.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Sem exposição em rede por configuração.
- Proteção contra CSRF/DNS rebinding em REST e WS.
- Tokens não persistem entre execuções.

### Negativas
- Abas abertas perdem acesso após reiniciar o processo (novo token).
- Sem acesso remoto ou multiusuário por design.

### Riscos
- O token aparece na URL impressa no stdout e no histórico do navegador. Mitigação observada: troca por cookie `HttpOnly` e access log desligado.

## Validação
- **Evidência no código:** `backend/src/notisbook/config.py` (`HOST`, `token`, `allowed_origins`, `allowed_hosts`), `backend/src/notisbook/security.py` (`require_token`, `require_trusted_host`, `guard_websocket`), `backend/src/notisbook/__main__.py` (`access_log=False`), `backend/src/notisbook/app.py` (`docs_url=None`).
- **Como confirmar:** `grep -n "HOST\|access_log" backend/src/notisbook/config.py backend/src/notisbook/__main__.py`.

## Notas de Implementação
- As páginas da SPA são públicas de propósito; a autenticação acontece via `?token=` → cookie (comentário em `static.py`).
- O cabeçalho `X-Notisbook: 1` é adicionado sem autenticação para que `start.sh` identifique uma instância em execução.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
