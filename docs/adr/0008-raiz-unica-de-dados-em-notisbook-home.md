# ADR-0008: Raiz única de dados em NOTISBOOK_HOME

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
O app mantém ambientes Spark, warehouse de tabelas, catálogo, preferências e a pasta padrão de notebooks. Esses dados precisam de um local previsível e configurável.

## Decisão
Todos os dados gerenciados ficam sob uma raiz única: `$NOTISBOOK_HOME`, ou `~/.notisbook` quando a variável não está definida (`default_home` em `config.py`). Estrutura observada:
- `envs/` — ambientes Spark;
- `warehouse/` — `spark/` (warehouse padrão do Spark) e `iceberg/`;
- `catalog.db` — catálogo SQLite;
- `preferences.json` — preferências do operador;
- `notebooks/` — pasta padrão de notebooks.

`ensure_home` cria a raiz e as subpastas de forma idempotente na partida; falha encerra o processo com mensagem.

Motivação histórica não recuperada do código.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Desinstalar ou isolar uma instância exige tratar apenas um diretório.
- `NOTISBOOK_HOME` permite instâncias separadas (ex.: testes).
- A raiz e seus ancestrais são protegidos contra exclusão e contra uso como pasta de notebooks (`protected_paths`).

### Negativas
- O caminho não pode conter `?`, pois é embutido na URL JDBC do catálogo (`UnsupportedHome`).
- Kernelspecs ficam fora desta raiz (diretório de dados do Jupyter).

### Riscos
- Um `NOTISBOOK_HOME` em volume lento ou de rede afeta o SQLite e o warehouse. Não há mitigação identificada no código.

## Validação
- **Evidência no código:** `backend/src/notisbook/config.py` (`default_home`, `ensure_home`, `default_root`), `backend/src/notisbook/spark/bundles.py` (`WAREHOUSE_DIR`, `SPARK_WAREHOUSE_SUBDIR`, `catalog_uri`), `backend/src/notisbook/catalog/store.py` (`CATALOG_DB`), `backend/src/notisbook/preferences.py` (`FILENAME`, `protected_paths`).
- **Como confirmar:** `grep -n "NOTISBOOK_HOME" -r backend/src/notisbook`.

## Notas de Implementação
- Outras variáveis de ambiente observadas: `NOTISBOOK_FRONTEND_DIST`, `NOTISBOOK_PYPI_URL` e `NOTISBOOK_MAVEN_URL`.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
