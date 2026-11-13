# ADR-0010: Frontend compilado embutido no pacote Python

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
A interface é uma SPA React/Vite (`frontend/`) e o backend é um pacote Python instalável (`notisbook`). O usuário final executa um único comando (`notisbook`).

## Decisão
- O próprio processo FastAPI serve o frontend compilado: `/assets` como estáticos e fallback de SPA para as demais rotas fora de `/api` (`static.py`), com `Content-Security-Policy` nas respostas HTML.
- No release, `scripts/build_release.py` compila o frontend, copia `frontend/dist` para `backend/src/notisbook/_frontend`, gera sdist e wheel com `uv build` e confere a presença de `notisbook/_frontend/index.html` nos dois artefatos. O `pyproject.toml` declara `_frontend` como `artifacts` do hatch, pois a pasta é ignorada pelo Git.
- Em tempo de execução, a origem do frontend segue a ordem `NOTISBOOK_FRONTEND_DIST` → `<repo>/frontend/dist` (desenvolvimento) → cópia embutida no pacote (`default_frontend_dist`).
- Sem build presente, o backend responde 503 com uma página explicativa.

Motivação histórica não recuperada do código.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Um único artefato instalável e uma única origem (`127.0.0.1:<porta>`), compatível com a validação de Origin/Host (ADR-0012).
- O usuário final não precisa de Node.js.

### Negativas
- O build de release exige Node.js e npm.
- A pasta `_frontend` é cópia gerada; a consistência depende do script de release.

### Riscos
- Publicar um pacote sem o frontend. Mitigação observada: `check_contains_index` falha o build se o `index.html` não estiver no sdist e no wheel.

## Validação
- **Evidência no código:** `backend/src/notisbook/static.py` (`mount_frontend`, `CSP`), `backend/src/notisbook/config.py` (`default_frontend_dist`), `backend/pyproject.toml` (`artifacts = ["src/notisbook/_frontend"]`), `scripts/build_release.py` (`embed_frontend`, `check_contains_index`), `backend/.gitignore`.
- **Como confirmar:** `grep -n "_frontend" backend/pyproject.toml scripts/build_release.py backend/src/notisbook/config.py`.

## Notas de Implementação
- Em desenvolvimento, o Vite (`frontend/vite.config.ts`) faz proxy de `/api` para `127.0.0.1:8765`, reescrevendo o Origin do upgrade WebSocket e recusando upgrades vindos de outras origens.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
