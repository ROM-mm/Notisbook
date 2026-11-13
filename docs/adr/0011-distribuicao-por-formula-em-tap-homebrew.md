# ADR-0011: Distribuição por fórmula em tap Homebrew próprio

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
O Notisbook é um app local, com lógica específica de macOS (por exemplo, a busca de JDK via `/usr/libexec/java_home` e kegs do Homebrew). É preciso publicar versões instaláveis para usuários finais.

## Decisão
A publicação é automatizada por `scripts/release.sh`, que:
- ajusta a versão, cria a tag e gera o sdist com o frontend embutido;
- cria a release no GitHub com o sdist como asset;
- calcula o sha256 do asset publicado e atualiza `url`/`sha256` na fórmula `Formula/notisbook.rb` de um tap Homebrew próprio (definido em `TAP_NAME`);
- regenera os blocos `resource` da fórmula (`brew update-python-resources`) apenas quando `backend/uv.lock` mudou desde a tag anterior;
- valida com `brew reinstall --build-from-source`, `brew test` e `brew audit --strict` (opcionalmente pulados com `--skip-brew-test`) antes de publicar o tap.

A fórmula fica em um repositório separado (o tap), fora deste repositório.

Motivação histórica não recuperada do código.

## Alternativas Consideradas
Não identificadas no material analisado. Não foi observada publicação no PyPI no código analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Instalação e atualização pelo fluxo padrão do Homebrew.
- Integridade do asset referenciada por sha256 na fórmula.
- Modo `--dry-run` para conferir o processo sem publicar.

### Negativas
- Distribuição concentrada em macOS/Homebrew.
- A fórmula não é versionada junto com o código; mudanças nela não aparecem neste repositório.

### Riscos
- Falha no meio do processo (ex.: release criada, tap não publicado). Mitigação observada: o script registra a etapa atual e imprime instruções para concluir manualmente.

## Validação
- **Evidência no código:** `scripts/release.sh` (variáveis `TAP_NAME`, `FORMULA_REL`; etapas `sha256`, `resources`, `validação brew`), `scripts/build_release.py` (sha256 do sdist), `backend/uv.lock`.
- **Como confirmar:** `./scripts/release.sh --help`, sem executar a publicação; ou ler o script.

## Notas de Implementação
- Ferramentas exigidas pelo script: `git`, `gh`, `uv`, `npm`, `brew`, `curl` e `shasum`.
- O conteúdo da fórmula não foi analisado, pois está fora do repositório.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
