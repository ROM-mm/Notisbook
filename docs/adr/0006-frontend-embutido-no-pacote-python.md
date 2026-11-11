# ADR-0006: Frontend compilado embutido no pacote Python

**Status:** Proposto
**Data:** 2026-11-11 (geração do registro; data da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
O pacote instalado (Homebrew, pip) não tem o diretório `frontend/` do repositório.

## Decisão
O build do frontend é copiado para `notisbook/_frontend` e incluído no sdist e no wheel (`artifacts` do hatchling). Em runtime o servidor procura o build em `NOTISBOOK_FRONTEND_DIST`, depois `frontend/dist` do repositório, depois o embutido.

Motivação histórica não recuperada do código.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências

### Positivas
- Pacote autossuficiente, sem Node no usuário final.
- Desenvolvimento continua usando `frontend/dist`.

### Negativas
- Releases dependem de `scripts/build_release.py` para não sair sem frontend.
- Um `_frontend` antigo no checkout pode ser servido se `frontend/dist` não existir.

### Riscos
- Pacote sem `index.html`. Mitigação: o script confere o arquivo nos dois artefatos; sem ele o servidor responde 503.

## Validação
- **Evidência no código:** `backend/pyproject.toml:28-35`, `backend/src/notisbook/config.py:36-44`, `scripts/build_release.py`
- **Como confirmar:** `tar -tzf backend/dist/notisbook-*.tar.gz | grep _frontend/index.html`

---

**Autor:** Romerito Morais

**Versão:** 20261111125851

**Data:** 2026-11-11 12:58:51

**SKILL:** Document
