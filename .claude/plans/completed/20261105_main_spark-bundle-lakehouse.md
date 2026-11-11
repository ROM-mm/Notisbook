# Bundle Delta/Iceberg/Hudi no ambiente Spark

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-05 14:06:15 -0300
Modificação: 2026-11-06 14:45:21 -0300
Finalização: 2026-11-06 14:45:21 -0300

## Objetivo

Ao instalar uma versão do Spark em Settings, o ambiente já sai com Delta Lake, Apache Iceberg e Apache Hudi compatíveis (bundle sempre completo, um env por versão), jars baixados na instalação para o kernel subir offline, e `SparkSession.builder.getOrCreate()` no notebook já configurado com os três formatos. Versão sem entrada na matriz instala só o Spark e avisa que as libs não existem para ela. O plano cobre backend (T1–T5) e tela (T6). **T6 está BLOQUEADA**: a política da organização (CSED) restringe código a Java, Angular, Flutter e Python, e o frontend é React/TypeScript — T6 só é delegada após exceção formal da governança para este projeto; sem ela, o plano encerra no T5 com a API já expondo os campos da tela.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | Matriz de compatibilidade por linha major.minor (3.5, 4.1) com sha256, `bundle_for`, URL Maven, `render_spark_defaults` | python-engineer | — | 1 | escrita |
| T2 | Remover `PYSPARK_SUBMIT_ARGS` e `SPARK_CONF_DIR` do host nas duas `SCRUBBED_ENV` | python-engineer | — | 1 | escrita |
| T3 | Fase `bundle` no instalador: pip conjunto, download verificado, `spark-defaults.conf`, aviso sem matriz, `_validate` ampliado com smoke offline | python-engineer | T1 | 2 | escrita |
| T4 | Kernelspec grava `SPARK_CONF_DIR` e `metadata.notisbook.bundle`; `discover` expõe `formats`/`bundle_status` | python-engineer | T1,T3 | 3 | escrita |
| T5 | API: `formats` no `/catalog`, `formats`/`bundle_status` em `/versions`, 409 no POST com sessão ativa | python-engineer | T1,T4 | 3 | escrita |
| T6 | Tela: tipos com `formats`/`bundle_status`; aviso no seletor quando `formats` é `null`; selo de formatos e botão Reinstalar (confirmação, bloqueado com sessão ativa/instalação em curso) na lista — **BLOQUEADA até exceção CSED para React/TS** | python-engineer | T5 + exceção CSED | 4 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1, T2
- Wave 2 (serial, escrita): T3
- Wave 3 (serial, escrita): T4, T5
- Wave 4 (serial, escrita): T6 — só com a exceção da governança registrada

## Decisões
| # | decisão | racional | evidência | alternativas consideradas |
|---|---------|----------|-----------|---------------------------|
| D1 | Formatos = Delta, Iceberg, Hudi; bundle sempre completo, um env por versão | o "Rust" citado era o Hudi; mantém identidade de kernel e simplicidade | operador (respostas 1 e opção A); labs `setup/catalog/conf/spark-defaults.conf:17-28` | checkboxes por formato (descartado: variantes colidem em `kernel_name`) |
| D2 | Matriz estática em `spark/bundles.py`, chave major.minor, sha256 fixado, `revision`; só 3.5 e 4.1 | integridade e revisão via git; 4.3 sem Delta/Hudi confirmados | parecer software-architect (Context7: Delta sem Spark 4.2/4.3) | JSON (sem ganho); checksum lido do repositório Maven (não garante integridade) |
| D3 | Jars baixados na instalação para `<env>/notisbook/jars` + smoke offline obrigatório | kernel funciona sem rede; smoke prova classloading | operador (resposta 3) | `spark.jars.packages`/Ivy (exige rede no boot) |
| D4 | Config via `<env>/spark-conf/spark-defaults.conf` + `SPARK_CONF_DIR` no kernelspec, sempre | env do kernelspec vence o do host; fora do pacote, auditável | `jupyter_client/provisioning/provisioner_base.py:156-157`; `load-spark-env.sh:33` | `pyspark/conf` no site-packages; `PYSPARK_SUBMIT_ARGS` (quoting frágil) |
| D5 | Iceberg em catálogo nomeado `iceberg`, `type=hadoop`, warehouse `<SPARK_LABS_HOME>/warehouse/iceberg` | `SparkSessionCatalog` conflita com `DeltaCatalog` | operador (resposta 2); labs `spark-defaults.conf:20` | `SparkSessionCatalog` |
| D6 | Versão sem matriz: instala só Spark, `formats: null`, linha de aviso no job; falha de bundle com matriz = falha da instalação (sem rebaixar) | evita estado oculto | operador (resposta 4) | rebaixar silenciosamente para "só Spark" |
| D7 | POST `/versions` devolve 409 com sessão ativa do kernel | `_cleanup` apagaria o env em uso na reinstalação | `api/spark.py` (DELETE já faz 409) | só bloquear na UI |
| D8 | T6 no plano, porém bloqueada até exceção CSED | operador quer back+front num plano; política da organização restringe stacks a Java/Angular/Flutter/Python | operador ("preciso que esse plano cubra back e front"); instrução organizacional CSED | migrar frontend para Angular (escopo grande, plano próprio); T6 fora do plano |
| D9 | Spark 3.5.0–3.5.2 também recebem o bundle, com Delta 3.2.x; a matriz passa a distinguir faixas de patch dentro da linha 3.5 | `delta-spark 3.3.3` exige `pyspark>=3.5.3` e quebrava a instalação dessas versões (regressão apontada no code review, rodada 1) | operador (opção 2 no human gate do loop); PyPI `requires_dist` do delta-spark | cortar 3.5.0–3.5.2 para "só Spark" com aviso (descartado pelo operador) |

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | `bundle_for` resolve 3.5.x e devolve `None` para 4.3.0 | `backend/.venv/bin/python -c "from notisbook.spark.bundles import bundle_for; print(bundle_for('3.5.9').line, bundle_for('4.1.3').line, bundle_for('4.3.0'))"` → `3.5 4.1 None` | feature |
| T1 | Todo artefato da matriz tem sha256 de 64 hex | `backend/.venv/bin/python -c "from notisbook.spark.bundles import MATRIX; import re; print(all(re.fullmatch('[0-9a-f]{64}', a.sha256) for b in MATRIX.values() for a in b.artifacts))"` → `True` | feature |
| T1 | `render_spark_defaults` emite extensões Iceberg,Delta,Hudi, `spark_catalog`=DeltaCatalog e catálogo `iceberg` | `grep -nE "IcebergSparkSessionExtensions|DeltaCatalog|spark.sql.catalog.iceberg" backend/src/notisbook/spark/bundles.py` → 3+ ocorrências | feature |
| T2 | Variáveis do host removidas nas duas listas | `grep -nE "PYSPARK_SUBMIT_ARGS|SPARK_CONF_DIR" backend/src/notisbook/spark/installer.py backend/src/notisbook/kernels/service.py` → ocorrência em cada `SCRUBBED_ENV` | constraint |
| T3 | Fase `bundle` entre `install` e `validate` | `grep -n "^PHASES" backend/src/notisbook/spark/installer.py` → `... "install", "bundle", "validate" ...` | feature |
| T3 | Instalar 3.5.9 grava jars com sha256 da matriz | após instalar: `shasum -a 256 <env>/notisbook/jars/*.jar` confere com `MATRIX['3.5']` | feature |
| T3 | Jar adulterado falha a instalação e descarta o env novo | `NOTISBOOK_MAVEN_URL` → servidor local com jar alterado: job `failed` citando sha256; env novo ausente em `<base>/envs`; `kernel.json` anterior inalterado (`shasum` antes/depois) | feature |
| T3 | Versão sem matriz instala só Spark com aviso | instalar 4.3.0: job `succeeded`, linha de aviso na fase `bundle`, `test -d <env>/notisbook/jars` → falso | feature |
| T4 | Kernelspec expõe `SPARK_CONF_DIR` e bundle | `jq '.env.SPARK_CONF_DIR, .metadata.notisbook.bundle' ~/Library/Jupyter/kernels/spark359/kernel.json` → caminho do env + objeto `{line, revision, formats}` | feature |
| T5 | `/catalog` traz `formats` por versão | `curl .../api/spark/catalog \| jq '.versions[] \| {version, formats}'` → não nulo em 3.5.x/4.1.x, `null` em 4.3.0 | feature |
| T5 | `/versions` traz `formats` e `bundle_status` | `curl .../api/spark/versions \| jq '.installed[] \| {version, formats, bundle_status}'` → env antigo `missing`/`unsupported`, reinstalado `installed` | feature |
| T5 | POST com sessão ativa → 409 | notebook aberto no kernel spark359: `curl -X POST .../api/spark/versions -d '{"version":"3.5.9"}'` → HTTP 409 | constraint |
| T6 | Front compila com os novos tipos | `cd frontend && npm run build` → sem erros | feature |
| T6 | Aviso aparece para versão sem matriz | `/settings`, selecionar 4.3.0 em `data-testid="spark-version-select"` → aviso "Delta, Iceberg e Hudi não estão disponíveis" visível | feature |
| T6 | Env sem bundle mostra Reinstalar | `grep -n "bundle_status" frontend/src/components/spark/InstalledList.tsx` → condição `missing`/`outdated`; na tela, env antigo exibe o botão | feature |
| T5 | Sessão sobe offline com os três formatos (E2E, operador) | rede desligada, notebook spark359: `SparkSession.builder.getOrCreate().conf.get("spark.sql.extensions")` → contém Iceberg, Delta e Hudi | feature |
| R1 | Reinstalação não apaga o env antigo se uma sessão do kernel abriu durante a instalação (TOCTOU do 409 — review `api/spark.py:84` / `installer.py:275`) | `grep -nE "has_active_session|active_session" backend/src/notisbook/spark/installer.py` → checagem antes de `_cleanup` remover o env anterior | constraint |
| R2 | Smoke aceita o marcador em qualquer linha da saída (review `installer.py:272`) | `grep -n "bundle-smoke-ok" backend/src/notisbook/spark/installer.py` → teste de pertinência (`in lines`), sem `lines[-1]` | feature |
| R3 | Download de jar é interrompível no cancelamento do job (review `installer.py:227`) | `grep -nE "threading.Event|is_set\(\)" backend/src/notisbook/spark/installer.py` → evento checado no laço de chunks e sinalizado no `CancelledError` | constraint |
| R4 | Spark 3.5.0–3.5.2 resolvem um bundle com Delta 3.2.x; 3.5.3+ seguem com Delta 3.3.3 | `backend/.venv/bin/python -c "from notisbook.spark.bundles import bundle_for; [print(v, bundle_for(v).pip) for v in ('3.5.0','3.5.2','3.5.3','3.5.9')]"` → 3.5.0/3.5.2 com `delta-spark==3.2.x`, 3.5.3/3.5.9 com `delta-spark==3.3.3` | feature |
| R5 | Instalação real de 3.5.1 sobe com os três formatos (smoke offline) | instalar 3.5.1 em base_dir isolado: job `succeeded`, `bundle-smoke-ok`, `shasum -a 256 <env>/notisbook/jars/*.jar` confere com a matriz | feature |
| R6 | Sessão em arranque conta como ativa no cleanup e no 409 (review `installer.py:291`, `kernels/service.py:474`) | `grep -nE "starting|_starting" backend/src/notisbook/kernels/service.py` → kernel_name registrado antes do `start` e retirado no `finally`; predicado usado pelo installer e pela API | constraint |
| R7 | Cancelamento espera a thread de download antes de `_discard` (review `installer.py:160`) | `grep -nE "asyncio.wait|wait_for" backend/src/notisbook/spark/installer.py` → espera limitada do future do download no `CancelledError` | constraint |
| R8 | Sessão é registrada como em arranque antes da lookup do kernelspec (review `kernels/service.py:462`) | `grep -nE "_starting\[|get_kernel_spec" backend/src/notisbook/kernels/service.py` → registro em `_starting` aparece antes de `get_kernel_spec` em `create`, com o `pop` no mesmo `finally` | constraint |
| R9 | Cada entrada da matriz tem identidade própria no kernelspec; env 3.5.0–3.5.2 instalado com Delta 3.3.3 sai `outdated` (review `bundles.py:56-85`, `kernelspec.py:122`) | `backend/.venv/bin/python -c "from notisbook.spark.bundles import bundle_for as b; x,y=b('3.5.1'),b('3.5.9'); print((x.line,x.revision)!=(y.line,y.revision) or getattr(x,'key',None)!=getattr(y,'key',None))"` → `True`; `grep -n "key\|revision" backend/src/notisbook/spark/kernelspec.py` → comparação pela identidade da entrada | constraint |
| R10 | O changeset não introduz regressão de lint (review `installer.py:9`, `installer.py:264`, `bundles.py:160`) | `cd backend && ruff check src/notisbook/spark/bundles.py src/notisbook/spark/installer.py src/notisbook/spark/kernelspec.py src/notisbook/kernels/service.py src/notisbook/api/spark.py src/notisbook/app.py` → `All checks passed!` (corrigido: o baseline NÃO passa limpo — 1 I001 pré-existente em `api/sessions.py`, fora do escopo) | constraint |

## Arquivos previstos
- `backend/src/notisbook/spark/bundles.py` — T1
- `backend/src/notisbook/spark/installer.py` — T2, T3
- `backend/src/notisbook/kernels/service.py` — T2, R6
- `backend/src/notisbook/spark/kernelspec.py` — T4
- `backend/src/notisbook/api/spark.py` — T5
- `backend/src/notisbook/app.py` — R1 (wiring do callback de sessão ativa no `SparkInstaller`)
- `frontend/src/api/types.ts` — T6
- `frontend/src/components/spark/InstallPanel.tsx` — T6
- `frontend/src/components/spark/InstalledList.tsx` — T6
- `frontend/src/components/spark/useSparkData.ts` — T6

## Fora de escopo
- Linha 4.3 (e 4.2) na matriz — Delta/Hudi sem compatibilidade confirmada; cai no aviso.
- Testes automatizados — não pedidos.
- **Documentação de produto** — nenhuma identificada; se README/ARCHITECTURE descreverem o instalador, ficam desatualizados e serão reportados no fim.

## Não mexer
- `POST /versions` continua recebendo só `{version}`.
- `kernel_name` e identidade do kernel (spark + versão sem pontos).
- Catálogo dinâmico do PyPI em `spark/catalog.py` (filtro, cache, `SUGGESTED_VERSIONS`).
- Comportamento atômico em falha: `_discard` do env novo, kernelspec anterior intacto.
- `frontend/` fora dos quatro arquivos de T6 (e eles próprios até a exceção CSED).

## Status
- [x] T1  - [x] T2  - [x] T3  - [x] T4  - [x] T5  - [ ] T6 (bloqueada: exceção CSED)

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 0 | knowledge-engineer | OK | 90770 | 61197 |
| 0 | knowledge-engineer | OK | 111070 | 63960 |
| 0 | software-architect | OK | 253781 | 87381 |
| 1-3 | python-engineer | OK | 554218 | 74883 |
| review | code-review (subagente) | ajustes necessários | 72102 | 70908 |
| loop-1 | python-engineer | OK | 23914 | 37148 |
| review-1 | code-review (subagente) | ajustes necessários | 89897 | 74237 |
| loop-2 | python-engineer | OK | 384933 | 63136 |
| review-2 | code-review (subagente) | ajustes necessários | 94709 | 76579 |
| loop-3 | python-engineer | OK | 27906 | 36588 |
| review-3 | code-review (subagente) | ajustes necessários | 95741 | 76672 |
| loop-4 | python-engineer | OK | 26926 | 30624 |
| review-4 | code-review (subagente) | aprovar | 68814 | 72891 |
| audit | plan-auditor | OK (PARCIALMENTE AUDITÁVEL) | 56103 | 38239 |
| memoria | memory-manager | OK | 16758 | 39118 |
<!-- effort-ledger:end -->
