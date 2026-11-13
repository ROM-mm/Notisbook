# ADR-0005: Bundle de lakehouse por matriz estática com sha256

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Cada versão do Spark exige versões específicas de Delta, Iceberg e Hudi (linha Scala, compatibilidade de patch). Os jars são baixados de um repositório Maven no momento da instalação do ambiente.

## Decisão
A compatibilidade é codificada em uma matriz estática (`MATRIX` em `spark/bundles.py`), com entradas por linha `major.minor`, opcionalmente restritas a faixas de patch (`min_patch`/`max_patch`). Cada entrada (`Bundle`) define:
- `key` (identidade única gravada no kernelspec) e `revision` (incrementada a cada mudança, para marcar ambientes instalados como `outdated`);
- formatos suportados, pacotes pip (`delta-spark`) e artefatos Maven;
- um sha256 fixado para cada jar.

O instalador baixa cada jar para um arquivo temporário, calcula o sha256, rejeita divergências e só então renomeia para o destino. A URL base do Maven pode ser trocada por `NOTISBOOK_MAVEN_URL`. Versões sem entrada na matriz não recebem bundle.

Motivação histórica não recuperada do código. A docstring do módulo descreve o propósito do sha256: permitir que o instalador verifique os downloads.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Instalações reprodutíveis e com integridade verificada dos jars.
- Comentários da matriz registram restrições de compatibilidade (ex.: Delta 3.2.0 para Spark 3.5.0–3.5.2).
- Ambientes defasados são detectados por `key`/`revision`.

### Negativas
- Suportar uma nova linha do Spark exige alterar o código e publicar nova versão do app.
- Hashes precisam ser atualizados manualmente a cada troca de versão de artefato.

### Riscos
- Erro de digitação em um hash bloqueia a instalação daquela linha. Mitigação observada: a mensagem de erro informa o hash esperado e o obtido.

## Validação
- **Evidência no código:** `backend/src/notisbook/spark/bundles.py` (`Artifact`, `Bundle`, `MATRIX`, `bundle_for`, `maven_url`), `backend/src/notisbook/spark/installer.py` (`_fetch_jar` com `hashlib.sha256`), `backend/src/notisbook/spark/kernelspec.py` (metadados `bundle` em `write_kernelspec`).
- **Como confirmar:** `grep -n "sha256" backend/src/notisbook/spark/installer.py backend/src/notisbook/spark/bundles.py`.

## Notas de Implementação
- Linhas cobertas no código analisado: 3.5 (duas faixas de patch) e 4.1.
- Após a instalação, um smoke test (`SMOKE_SCRIPT`) carrega uma classe de cada extensão/catálogo antes de trocar o kernelspec.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
