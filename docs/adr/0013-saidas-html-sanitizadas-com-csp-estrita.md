# ADR-0013: Saídas HTML sanitizadas e isoladas, com CSP estrita

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Células produzem saídas `text/html` e Markdown arbitrários (ex.: tabelas de DataFrames, HTML de bibliotecas). Essas saídas são exibidas na mesma origem que tem acesso autenticado ao backend e também são exportadas como relatório HTML.

## Decisão
- **Interface:** saídas HTML e Markdown são sanitizadas com DOMPurify por configurações centralizadas em `frontend/src/components/outputs/purify.ts`, que proíbem tags de execução, navegação ou captura de dados (`script`, `iframe`, `form`, `input`, `base`, `link`, `meta` etc.). Uma regra do projeto, registrada no arquivo, exige que cada componente chame o sanitize junto da injeção. O `<style>` é permitido porque fica no Shadow DOM.
- **Página da SPA:** CSP com `script-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'` e `base-uri 'none'` (`static.py`); `style-src 'unsafe-inline'` é aceito, com justificativa no código (CodeMirror e `<style>` no Shadow DOM).
- **Exportação HTML:** relatório autocontido, sem JavaScript, com CSP `default-src 'none'`, Markdown renderizado por `markdown-it-py` e sanitizado com `nh3`, e imagens limitadas a 10 MB.

Motivação histórica não recuperada do código além das justificativas pontuais citadas.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Defesa em camadas contra XSS: sanitização mais CSP.
- Relatórios exportados podem ser abertos sem executar código.

### Negativas
- Saídas interativas que dependem de JavaScript (widgets, gráficos JS) não funcionam.
- `style-src 'unsafe-inline'` amplia a superfície de CSS injetado.

### Riscos
- Novos componentes que injetem HTML sem sanitizar. Mitigação observada: regra registrada em `purify.ts` de manter o sanitize junto da injeção.

## Validação
- **Evidência no código:** `frontend/src/components/outputs/purify.ts`, `frontend/src/components/outputs/HtmlOutput.tsx`, `frontend/src/components/outputs/Markdown.tsx`, `backend/src/notisbook/static.py` (`CSP`), `backend/src/notisbook/export/html_report.py` (`CSP`, `nh3.clean`, `MAX_IMAGE_BYTES`), dependências `dompurify` em `frontend/package.json` e `nh3` em `backend/pyproject.toml`.
- **Como confirmar:** `grep -rn "DOMPurify\|sanitize" frontend/src/components/outputs`; `grep -n "CSP" backend/src/notisbook/static.py backend/src/notisbook/export/html_report.py`.

## Notas de Implementação
- A exportação também gera código-fonte Python (`export/py_source.py`), fora do escopo desta decisão.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
