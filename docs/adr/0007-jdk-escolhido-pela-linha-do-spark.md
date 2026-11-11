# ADR-0007: JDK do kernel escolhido pela linha do Spark

**Status:** Proposto
**Data:** 2026-11-11 (geração do registro; data da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Spark 3.x e 4.x exigem majors de Java diferentes; o JDK do sistema pode não servir.

## Decisão
O `JAVA_HOME` gravado no kernelspec é escolhido pela linha do Spark: 3.x → 17; demais → 21, senão 17. Busca: `$JAVA_HOME` (só se o major servir) → `/usr/libexec/java_home -v N` → keg `openjdk@N` do Homebrew.

Motivação histórica não recuperada do código.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências

### Positivas
- Kernels não herdam um JDK incompatível.
- Funciona com o `openjdk@17` keg-only instalado pela fórmula.

### Negativas
- Depende de ferramentas do macOS e do Homebrew.

### Riscos
- O painel de pré-requisitos usa outra resolução e pode não enxergar o keg do Homebrew. Mitigação: não identificada no código analisado.

## Validação
- **Evidência no código:** `backend/src/notisbook/spark/prereqs.py:132-203`
- **Como confirmar:** `grep -n jdk_for_spark backend/src/notisbook/spark/prereqs.py`

---

**Autor:** Romerito Morais

**Versão:** 20261111125851

**Data:** 2026-11-11 12:58:51

**SKILL:** Document
