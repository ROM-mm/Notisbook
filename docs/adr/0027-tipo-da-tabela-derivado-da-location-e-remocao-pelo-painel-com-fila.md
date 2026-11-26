# ADR-0027: Tipo da tabela derivado da location e remoção pelo painel com fila de exclusão

**Status:** Aceito (validado pelo operador em 2026-11-26, após teste manual)
**Data:** 2026-11-26 (geração do registro)
**Decisores:** Operador (responsável pelo produto); tech-lead (orquestração)

## Contexto

O catálogo persistente `spark_catalog` (`nb_tables` no `catalog.db`) classifica cada tabela como `MANAGED` ou `EXTERNAL`. Tabela gerenciada vive em `s3a://notisbook-managed/<schema>/<tabela>` e, no DROP, tem a pasta enfileirada em `nb_pending_deletions`, drenada apenas pelo kernel; o backend nunca apaga arquivos.

Problemas observados no código antes desta decisão (registrados pelo operador e confirmados por diagnóstico):

- O tipo vinha do `tableType` informado pelo Spark. A reidratação de uma sessão recria tabelas com `createTable(path=…)`, que o Spark lista como `EXTERNAL`; uma gerenciada legítima podia ser regravada como `EXTERNAL` e o DROP deixava os arquivos órfãos no bucket reservado.
- A validação pós-escrita (`table_destination`) aceita a location gerenciada exata sem conhecer o tipo, o que permitia uma `EXTERNAL` dentro do bucket reservado.
- Linhas `MANAGED` cuja pasta não existe nunca entravam na sessão (o `hydrate` as pula), não eram alcançadas pelo DROP e não tinham caminho de remoção no painel.
- O cálculo de "pasta em uso" divergia entre o DROP (`apply_plan`) e o drain do kernel (`used_folders`), e o DROP ignorava tabelas do catálogo Glue.

### Critérios
- O backend continua sem apagar arquivos.
- Uma tabela é uma referência: precisa poder sair do catálogo mesmo que os arquivos não existam mais (critério declarado pelo operador).
- Nenhum caminho de remoção pode apagar arquivos que a prévia mostrada ao operador disse que ficariam.
- O contrato do `POST /api/runtime-catalog/plan` entre kernel e backend não muda.

## Decisão

1. **O tipo passa a ser função de (chave, location):** `MANAGED` se, e somente se, a location é exatamente `managed_location(schema, tabela)` da própria chave; qualquer outra location s3 é `EXTERNAL`. O predicado único é `is_own_managed`, aplicado no kernel (`describe_new`, espelho do rename) e no backend (`apply_plan` em created/updated/renamed). A migração 6 do `catalog.db` promove para `MANAGED` as linhas `EXTERNAL` já gravadas na própria pasta gerenciada.
2. **Remoção pelo painel ("Remove from catalog"), só no `spark_catalog`:** prévia + `DELETE` com etag. Remove sempre a linha; quando a tabela é `MANAGED` própria e a pasta está livre, enfileira a pasta na mesma transação (o kernel apaga se existir; pasta ausente conta como concluída). Sem reserva de kernel ocioso: sessões abertas convergem pela `generation`.
3. **Etag cobre o efeito:** no botão e na exclusão de schema, o etag inclui a decisão de enfileiramento; mudança entre prévia e confirmação responde `409 catalog_changed`.
4. **Regra única de pasta em uso** (`folder_key`, `folder_overlaps`, `folder_in_use`, `used_folders`, apenas stdlib e injetadas no kernel): DROP, drain, remoção pelo painel e exclusão de schema consideram tabelas spark, Iceberg e Glue, sem distinção de caixa. Na exclusão de schema, as linhas do próprio schema não seguram a pasta.
5. **`drop_behavior` com quatro códigos** (`deletes_files`, `registry_only`, `keeps_files_outside_managed`, `keeps_files_shared`), para que o painel descreva o que o DROP faz de fato.

A motivação acima foi fornecida pelo operador e pelo diagnóstico da sessão de 2026-11-26; não foi inferida apenas do código.

## Alternativas Consideradas

Atribuídas às decisões registradas no plano da sessão (fornecidas pelo chamador):

- **Recusar `EXTERNAL` na pasta gerenciada após a escrita:** descartada, porque recusaria uma `MANAGED` legítima reidratada e não corrigiria linhas já gravadas.
- **Derivar o tipo só na criação:** descartada, porque sessões abertas com estado antigo rebaixariam a linha de volta.
- **Remoção pelo painel recusando tabelas `MANAGED` próprias:** adotada inicialmente e revertida pelo operador, porque deixava presa a tabela cuja pasta sumiu.
- **Reservar kernels ociosos durante a remoção:** descartada, por recusar a operação com qualquer célula em execução sem ganho de segurança.

## Consequências

Análise atual, não histórico da decisão.

### Positivas
- Uma única definição de "gerenciada" e de "pasta em uso" no kernel, no backend e na migração.
- Tabelas órfãs saem do catálogo sem excluir o schema inteiro, em qualquer runtime.
- O texto do DROP e dos diálogos reflete o efeito real sobre os arquivos.

### Negativas
- Depois da migração 6, o DROP de uma tabela antes vista como `EXTERNAL` na própria pasta gerenciada passa a enfileirar os arquivos.
- Pasta mantida por estar em uso por uma tabela Glue fica órfã se essa tabela sair depois (trade-off aceito pelo operador).
- Cada DROP refaz a leitura das locations (`used_folders`); em lote grande o custo cresce.

### Riscos
- Linhas legadas com variações de location (`s3://`, barra final) não são promovidas pela migração 6; convergem no próximo update pelo hook.
- O catálogo Glue ainda não tem remoção pelo painel e aceita `EXTERNAL_TABLE` na location gerenciada (fora do escopo desta decisão).

## Validação
- **Evidência no código:** `backend/src/notisbook/notislake/locations.py` (`is_own_managed`); `backend/src/notisbook/catalog/registry.py` (`folder_overlaps`, `used_folders`, `folder_in_use`, `_drop_behavior`, `apply_plan`); `backend/src/notisbook/catalog/store.py` (migração 6); `backend/src/notisbook/catalog/tables.py` (prévia, `_etag`, remoção); `backend/src/notisbook/catalog/schemas.py` (`_managed_plan`, `_spark_etag`, `_keep_reason`); `backend/src/notisbook/kernels/catalog_hook.py` (`own_managed`, `describe_new`, lista do `_render`); `backend/src/notisbook/api/catalog.py` (rotas `/api/catalog/tables/preview` e `/api/catalog/tables`).
- **Como confirmar:** `git log --oneline 8d229f6^..650d8a9` na branch `aws/athena-glue`; `grep -n "def is_own_managed" backend/src/notisbook/notislake/locations.py`; `sqlite3 "file:$HOME/.notisbook/catalog.db?immutable=1" 'PRAGMA user_version'` → 6 após o boot.

## Notas de Implementação
- Fora de `docs/adr/`, cite esta decisão pelo assunto ("tipo da tabela derivado da location").
- Frontend: `frontend/src/components/data/TableInfoPanel.tsx` (botão e diálogo de remoção) e `frontend/src/components/data/CatalogSection.tsx` (motivos das pastas mantidas na exclusão de schema).

---

**Autor:** DataEduca Platform

**Versão:** 20261126142242

**Data:** 2026-11-26 14:22:42

**SKILL:** Document
