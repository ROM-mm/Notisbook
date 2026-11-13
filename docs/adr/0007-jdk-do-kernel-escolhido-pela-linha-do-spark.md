# ADR-0007: JDK do kernel escolhido pela linha do Spark

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Linhas diferentes do Spark aceitam versões diferentes do JDK. O host (macOS) pode ter vários JDKs instalados, inclusive kegs do Homebrew que o utilitário `java_home` não enxerga.

## Decisão
O JDK é escolhido por versão do Spark na instalação do ambiente e gravado como `JAVA_HOME` no `kernel.json`:
- Spark 3.x → JDK 17; qualquer outra linha segue a regra do 4.x → JDK 21, depois 17 (`jdk_candidates`).
- Ordem de busca (`jdk_for_spark`): `$JAVA_HOME`, se apontar para um major aceito; depois, por major, `/usr/libexec/java_home -v <major>`; por fim o keg `openjdk@<major>` do Homebrew.
- Sem JDK compatível, a instalação falha com mensagem indicando os majors aceitos.

Motivação histórica não recuperada do código.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Cada kernel usa um JDK compatível com sua linha do Spark, independentemente do `JAVA_HOME` do shell.
- Suporte a JDKs do Homebrew sem configuração manual.

### Negativas
- Lógica específica de macOS (`/usr/libexec/java_home`, prefixos do Homebrew).
- Novas linhas do Spark herdam a regra do 4.x até que a função seja ajustada.

### Riscos
- Atualizar ou remover o JDK do host invalida o `JAVA_HOME` gravado. Mitigação possível: reinstalar o ambiente pelo painel do Spark.

## Validação
- **Evidência no código:** `backend/src/notisbook/spark/prereqs.py` (`jdk_candidates`, `jdk_for_spark`, `brew_jdk_home`, `JAVA_HOME_TOOL`), `backend/src/notisbook/spark/installer.py` (`_check_prereqs`), `backend/src/notisbook/spark/kernelspec.py` (`JAVA_HOME` em `write_kernelspec`).
- **Como confirmar:** `grep -n "def jdk_candidates" -A3 backend/src/notisbook/spark/prereqs.py`.

## Notas de Implementação
- O utilitário `java_home` pode ser substituído em testes por `NOTISBOOK_JAVA_HOME_TOOL`.
- O major do JDK é lido do arquivo `release` ou, na falta dele, de `bin/java -version`.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
