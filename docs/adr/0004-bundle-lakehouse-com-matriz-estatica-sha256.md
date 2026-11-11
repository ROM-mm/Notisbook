# ADR-0004: Bundle de lakehouse por matriz estática com sha256

**Status:** Proposto
**Data:** 2026-11-11 (geração do registro; data da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Cada versão do Spark precisa de versões compatíveis de Delta, Iceberg, Hudi e do driver SQLite JDBC.

## Decisão
Uma matriz estática por linha do Spark fixa coordenadas Maven e sha256 de cada jar. Os jars são baixados na instalação do ambiente e verificados; o `spark-defaults.conf` só é re-renderizado ao iniciar o kernel se todos os jars existem. Cada entrada tem `revision`/`key`, que marcam ambientes desatualizados.

Motivação declarada em comentário: o kernel é offline — nada é baixado na execução. Outras razões não foram recuperadas do código.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências

### Positivas
- Downloads verificados por hash.
- Execução sem rede.

### Negativas
- Versões novas de Spark/formatos exigem editar a matriz e publicar nova versão do Notisbook.

### Riscos
- Jar indisponível no Maven Central. Mitigação: URL configurável por `NOTISBOOK_MAVEN_URL`.

## Validação
- **Evidência no código:** `backend/src/notisbook/spark/bundles.py:1-154`, `backend/src/notisbook/kernels/service.py:566-592`
- **Como confirmar:** `grep -n sha256 backend/src/notisbook/spark/bundles.py`

---

**Autor:** Romerito Morais

**Versão:** 20261111125851

**Data:** 2026-11-11 12:58:51

**SKILL:** Document
