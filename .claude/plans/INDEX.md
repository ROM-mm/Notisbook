## 20261112_main_limpeza-pendencias-terminal.md
Criação: 2026-11-12 13:50:19 -0300   Finalização: —
Problema: os reviews do estilo terminal deixaram nits, comentários desatualizados e alguns problemas visuais pendentes.
Resolução: — em andamento

## 20261112_main_ui-estilo-terminal.md
Criação: 2026-11-12 11:12:44 -0300   Finalização: 2026-11-12 13:45:12 -0300
Problema: o visual atual não tem a cara de terminal limpo (estilo Cursor/Claude Code CLI) que o operador quer em toda a UI.
Resolução: UI inteira restilizada em terminal claro (fundo branco, faixas cinza sem borda, Roboto na UI/saídas/markdown, Hack no código, ícones P&B, prompt › na célula, output alinhado, títulos markdown com hierarquia) — commits 6c5627e..8bad903

## 20261111_main_redesign-visual-limpo.md
Criação: 2026-11-11 16:45:58 -0300   Finalização: 2026-11-12 10:43:32 -0300
Problema: o visual neo-brutalista do Notisbook (bordas pretas, sombras duras, Topbar própria) não agrada e desperdiça altura.
Resolução: visual limpo (bordas finas, sem sombra dura, acento azul), Topbar extinta com menus no header e kernel na barra de abas, laterais divididas (Catalog à esquerda; Notebooks/Connections/Variables à direita), ▶ ■ na célula e ícones Spark/Iceberg oficiais — commits 2db2482, 8d9b0ec, 61bcdd6, 7decece, 2d57a76.

## 20261111_main_painel-unico-explorer.md
Criação: 2026-11-11 15:05:04 -0300   Finalização: 2026-11-11 15:36:03 -0300
Problema: a lateral usa um rail de ícones para alternar entre os painéis Data e Notebooks — feio e desperdiça tela.
Resolução: rail removido; painel único Explorer (⌘B, começa fechado) com cartões Notebooks/Files/Catalog recolhíveis e redimensionáveis, scroll próprio e corpo desmontado quando recolhido — commit b7c701c.

## 20261111_main_script-de-release.md
Criação: 2026-11-11 13:17:25 -0300   Finalização: 2026-11-11 14:42:26 -0300
Problema: publicar uma versão nova do Notisbook (release no GitHub + fórmula do tap) exigia passos manuais e propensos a erro.
Resolução: scripts/release.sh <versão> com --dry-run/--skip-brew-test — versão/tag, build, push atômico, release, sha256 do asset baixado, fórmula validada no brew e push do tap, com orientação de retomada por etapa — commits c3869ba, 78a241a.

## 20261111_main_publicar-release-e-tap.md
Criação: 2026-11-11 11:48:28 -0300   Finalização: 2026-11-11 13:05:27 -0300
Problema: o Notisbook não tem release publicada nem tap Homebrew — ninguém consegue instalar por brew.
Resolução: release v0.1.0 (sdist com frontend, sha256 do asset) e tap ROM-mm/homebrew-tap com Formula/notisbook.rb (python@3.12, openjdk@17, uv, zeromq, libyaml); install do remoto validado, exige brew trust — tap e1fd0e1.

## 20261111_main_botao-run-sem-sombra.md
Criação: 2026-11-11 02:14:21 -0300   Finalização: 2026-11-11 02:21:02 -0300
Problema: o botão ▶ da célula tem sombra e fica colado no seletor de linguagem.
Resolução: .runBtn sem sombra/deslocamento (▶ e Render do markdown) e gap de 8px em .headerLeft — commit d97106f.

## 20261111_main_codigo-mais-vivo.md
Criação: 2026-11-11 01:52:23 -0300   Finalização: 2026-11-11 02:10:09 -0300
Problema: o código das células code parece apagado — fonte fina, paleta pastel e Python/SQL sem o destaque do padrão Databricks.
Resolução: Fira Code só no editor (--font-code, 500/keywords 700, ligaduras), paleta saturada estilo Databricks claro/escuro e prefixos SQL dourados (dialeto com crase) — commit f3253d1.

## 20261111_main_distribuicao-homebrew.md
Criação: 2026-11-11 01:00:47 -0300   Finalização: 2026-11-11 01:36:01 -0300
Problema: o Notisbook não pode ser instalado via Homebrew — o pacote sai sem frontend, não acha o JDK do Homebrew e não tem licença nem release limpa.
Resolução: frontend embutido no pacote, JDK via JAVA_HOME/java_home/keg do Homebrew (prefixo em cache), Apache-2.0, --version, sdist limpo e scripts/build_release.py com sha256 — commits 194307b..bf46ffd.

## 20261110_main_about-link-github.md
Criação: 2026-11-10 23:42:49 -0300   Finalização: 2026-11-10 23:50:12 -0300
Problema: o diálogo About mostra o nome do autor sem o link do GitHub.
Resolução: link github.com/ROM-mm abaixo do autor no About (nova aba, noopener noreferrer), com foco inicial mantido no botão Close — commit 25b76b4.

## 20261110_main_inicio-limpo-modo-foco-boas-vindas.md
Criação: 2026-11-10 23:27:54 -0300   Finalização: 2026-11-10 23:38:33 -0300
Problema: ao entrar, o painel Notebooks e o rail já aparecem; falta um modo só-células; o estado vazio não comunica o propósito do Notisbook.
Resolução: app abre sem rail nem painel (rail surge ao abrir o 1º painel; New notebook também abre o painel); modo foco por Cmd/Ctrl+., View e botão na topbar, e abrir painel sai do foco; boas-vindas "Spark it up locally." em Pacifico com marca-texto e ícones próprios de Iceberg/Delta/Hudi/Parquet — commit 1f5725c.

## 20261110_main_tabela-dataframe-neo-brutalism.md
Criação: 2026-11-10 23:04:48 -0300   Finalização: 2026-11-10 23:09:24 -0300
Problema: a tabela de resultado do DataFrame (HtmlOutput.tsx) ficou no visual antigo depois do redesign Neo-Brutalism pastel.
Resolução: tabela do DataFrame no Shadow DOM com moldura sólida, cabeçalho azul pastel sticky, divisórias suaves e zebra (claro/escuro); cabeçalho da grade SQL com seletor (0,1,3) para vencer o style do kernel — commit 429114a.

## 20261110_main_redesign-neo-brutalism-pastel.md
Criação: 2026-11-10 21:34:46 -0300   Finalização: 2026-11-10 22:51:56 -0300
Problema: o visual neo-brutalista suave (borda quase preta, sombra creme, cantos arredondados) não é fiel ao estilo e o operador quer o app inteiro em Neo-Brutalism pastel com cantos retos, claro e escuro.
Resolução: frontend inteiro em Neo-Brutalism pastel com cantos retos (tokens claro/escuro, fontes @fontsource offline, moldura, células com faixa por tipo, painéis, saídas, sintaxe, ícones Tabler retos) e logo N-Block (P13.3); export HTML mantém a paleta antiga (D4=b), HtmlOutput adiado — commits 0ef4ee7..fe1af5b.

## 20261110_main_ajustes-cosmeticos-catalogo.md
Criação: 2026-11-10 19:14:32 -0300   Finalização: 2026-11-10 19:35:59 -0300
Problema: nits do code review do catálogo e dos menus ficaram pendentes.
Resolução: 8 nits aplicados (rename só com RENAME, Kernels em api/deps, template em inglês, 404 sem criar catalog.db, prefixo Iceberg com caixa, symlink quebrado removível, erro no diálogo do Delete Folder, reserva protegida por shield) — commits 45df827..89ce03b.

## 20261110_main_menus-schema-e-pasta.md
Criação: 2026-11-10 16:57:40 -0300   Finalização: 2026-11-10 19:09:12 -0300
Problema: não dá para criar ou excluir schema pelo painel sem abrir SparkSession, nem excluir pasta pelo Files.
Resolução: Create/Delete Schema (spark e iceberg) e Delete Folder no painel Data, sem SparkSession — backend escreve no catalog.db, apaga só pastas MANAGED, reserva os kernels e usa allowlist no Files; hook sem DROP DATABASE destrutivo — commits 493be2f..12eab55.

## 20261110_main_catalogo-sqlite-persistente.md
Criação: 2026-11-10 14:48:30 -0300   Finalização: 2026-11-10 16:39:10 -0300
Problema: o catálogo do Notisbook só existe enquanto há SparkSession ativa e as tabelas Spark/Delta perdem o registro ao fim da sessão.
Resolução: catálogo persistente em ~/.notisbook/catalog.db (Iceberg JdbcCatalog + registro nb_* para Delta/Parquet), painel sem SparkSession com rótulo spark, hook no kernel que re-hidrata no getOrCreate e reconcilia por célula, Derby desligado — commits b7e5481..469de01.

## 20261110_main_visual-kernel-banner-erro.md
Criação: 2026-11-10 14:01:07 -0300   Finalização: 2026-11-10 14:13:56 -0300
Problema: o banner do kernel (faixa vermelho-clara) e os botões da tela de erro ao abrir o notebook ainda estão no visual antigo.
Resolução: banner do kernel como cartão de alerta (borda 2px danger, sombra sólida, ícone "!", mensagem quebrando ao lado do ícone, Reopen kernel no .neo) e Try again/Close tab da tela de erro no estilo novo — commit bc386af.

## 20261110_main_visual-painel-variables.md
Criação: 2026-11-10 13:45:40 -0300   Finalização: 2026-11-10 13:57:19 -0300
Problema: o painel Variables ainda é plano (sem cartão, sem pontilhado, linha fina) e destoa dos painéis Data/Notebooks já padronizados.
Resolução: painel Variables com cabeçalho de 2px e pílulas contornadas, corpo pontilhado com cartão que acompanha o conteúdo, selos de tipo contornados, linha em pílula no hover/foco e nome longo em reticências — commit 56bf0fa.

## 20261110_main_linha-codigo-saida.md
Criação: 2026-11-10 12:48:22 -0300   Finalização: 2026-11-10 13:40:51 -0300
Problema: na célula não há separação visual entre o código e a saída, que se misturam no mesmo cartão.
Resolução: saída da célula em .outputBox (só quando há saída) com linha de 1px de borda a borda do cartão; componentes de saída intocados — commit 2326f09.

## 20261110_main_visual-topbar-abas.md
Criação: 2026-11-10 12:20:58 -0300   Finalização: 2026-11-10 12:46:37 -0300
Problema: o topo da aplicação (banner, abas, topbar e a barra de execução) ainda usa linhas de 1px e controles planos, destoando das telas já padronizadas em cartão.
Resolução: banner, abas e topbar com linha de 2px; aba ativa em cartão encaixado; menu aberto, Variables e seletor com borda e mini-sombra; status em pílula; barra Run all em cartão alinhada ao painel; botões + Code/+ Markdown no estilo novo — commits 00aed07, 6299efc.

## 20261110_main_visual-paineis-data-notebooks.md
Criação: 2026-11-10 11:26:56 -0300   Finalização: 2026-11-10 11:58:41 -0300
Problema: o painel lateral (rail, Data, Notebooks) e os menus ainda usam o visual antigo e destoam das células, Settings e diálogos já padronizados.
Resolução: rail com item ativo em botão, painéis Data/Notebooks como cartões sobre pontilhado com seleção em pílula, menus (contexto e topbar) com borda 2px e sombra grafite, divisória CATALOG/FILES no vão entre cartões acompanhando o cursor, botões da home no estilo .neo — commits 7f0e397, 37be3b3.

## 20261110_main_visual-environments-dialogos.md
Criação: 2026-11-10 11:09:09 -0300   Finalização: 2026-11-10 11:21:04 -0300
Problema: a tela Spark environments, o modal Config e os diálogos ainda usam o visual antigo (cartão de borda fina, sem sombra) e o estilo de diálogo está duplicado em dois módulos.
Resolução: página Spark environments e os 4 diálogos no padrão de cartão (borda 2px, raio 16px, sombra sólida, cabeçalho com linha, fundo pontilhado, pílulas contornadas); botões novos escopados via .neo sem tocar global.css; .dialog unificado em styles/dialog.module.css — commit e818080.

## 20261110_main_visual-celulas-cartao.md
Criação: 2026-11-10 10:35:02 -0300   Finalização: 2026-11-10 10:57:11 -0300
Problema: as células do notebook têm visual genérico (cartão cinza de borda sutil) e o operador quer o estilo minimalista neo-brutalista do mockup aprovado.
Resolução: células viram cartão branco (borda 2px suavizada, raio 16px, sombra sólida creme, cabeçalho com linha inferior) sobre canvas pontilhado; seleção com sombra mais escura e edição só com borda accent; tokens --cell-*/--canvas-dot nos temas claro e escuro — commit 4b83ef0.

## 20261109_main_correcoes-pendencias-alta.md
Criação: 2026-11-09 17:18:21 -0300   Finalização: 2026-11-10 02:25:31 -0300
Problema: nits de review acumulados em pendencias/ escondem bugs reais e riscos de segurança ainda presentes no código.
Resolução: 19 correções pontuais (token fora do log, caixa no APFS, export .py, installer, 409 de libs, WS de jobs, picker, árvore/variáveis/download no front) sem regressão; T19 voltou às pendências.

## 20261109_main_cores-sintaxe-export.md
Criação: 2026-11-09 16:31:04 -0300   Finalização: 2026-11-09 17:09:46 -0300
Problema: o código das células no export HTML sai sem cores de sintaxe, diferente do editor do notebook.
Resolução: código Python/SQL do export colorido no backend com Pygments (spans t-* sobre texto escapado) e a paleta --syntax-* do app copiada no _CSS, claro e escuro; realce linear — commit 3595377.

## 20261109_main_grade-rolagem-display-n.md
Criação: 2026-11-09 14:09:23 -0300   Finalização: 2026-11-09 15:53:36 -0300
Problema: colunas da grade de DataFrame parecem cortadas sem barra de rolagem visível, e display(df) não permite escolher quantas linhas mostrar.
Resolução: grade do app com caixa de 640px, rolagem nos dois eixos e cabeçalho/rodapé fixos; display(df) com 50 linhas e n=1..1000 via wrapper global do display; export HTML com uma linha por célula e rolagem horizontal só na grade — commits 97fc1a3, f68d02a, 79df25b.

## 20261109_main_libs-por-ambiente-spark.md
Criação: 2026-11-09 12:56:04 -0300   Finalização: 2026-11-09 13:37:55 -0300
Problema: não dá para adicionar/remover/atualizar libs Python de um ambiente Spark pela UI, e o Remove do ambiente deixa sobras em disco.
Resolução: botão Config por ambiente abre modal bloqueante (＋ − ↑, seleção múltipla, só PyPI via uv pip in-place sob lock por kernel); libs core ocultas, recusadas (422) e fixadas por pin; Remove apaga todas as pastas da versão via lixeira e reporta sobras — commits 8cada89..8576ee2.

## 20261109_main_arvore-painel-notebooks.md
Criação: 2026-11-09 11:52:55 -0300   Finalização: 2026-11-09 12:20:23 -0300
Problema: no painel Notebooks clicar numa pasta entra nela (lista de um nível + breadcrumb), sem a árvore expansível do FILES.
Resolução: árvore própria (NotebookTree + store notebookTree sobre /api/contents, lazy por pasta, só pastas e .ipynb, Rename/Delete e rename inline em qualquer nível); browseDir removido — criação na pasta selecionada → pasta do notebook selecionado → raiz; troca de raiz zera a árvore por geração; /tree/<dir> expande até a pasta; expansão só em memória — commits 27cf8a4..a58ec12.

## 20261109_main_ajustes-ui-paineis-topbar.md
Criação: 2026-11-09 11:21:46 -0300   Finalização: 2026-11-09 11:40:39 -0300
Problema: o FILES repete o caminho da pasta, Settings duplica o Manage environments, os painéis têm tamanho fixo e a topbar tem espaço vazio sem informação da máquina.
Resolução: caixa do caminho removida; item About no menu abrindo diálogo com a marca e o autor; bordas do painel lateral e do Variables e divisória Catalog/Files arrastáveis (estado só em memória, reset ao fechar); RAM/CPU/disco na topbar via GET /api/system/resources com psutil e polling de 5 s — commits c51b3cb..a636da3.

## 20261109_main_export-notebook.md
Criação: 2026-11-09 10:18:13 -0300   Finalização: 2026-11-09 11:03:53 -0300
Problema: o notebook não pode ser exportado — nem para .py com SQL em spark.sql(), nem para Databricks, nem como relatório HTML legível.
Resolução: File exporta o notebook em memória via POST /api/export/{py,ipynb,html} (sem disco, limite 50 MB): .py Databricks source com um spark.sql por instrução, magics %% como # MAGIC e DuckDB comentado; .ipynb no lugar do .dbc (não documentado); .html autocontido sanitizado (nh3, markdown-it-py, CSP sem script) com rodapé Notisbook e horário de Brasília; menu só com o formato — commits f11d327..286fc33.

## 20261107_main_spark-sql-e-duckdb.md
Criação: 2026-11-07 22:40:29 -0300   Finalização: 2026-11-08 01:24:50 -0300
Problema: a célula só oferece Python e "SQL" (Spark), sem um motor SQL leve para consultar arquivos sem subir job Spark.
Resolução: rótulo Spark SQL e célula DuckDB SQL (uma instrução, conexão in-memory lazy por kernel com STATE preservado, extensões sem autoinstall sob o home injetado, grade HTML reaproveitada, duckdb==2.0.0 no instalador base, marcas de troca por família) — commit 4db5af1.

## 20261107_main_menu-contexto-raiz-notebooks.md
Criação: 2026-11-07 01:31:10 -0300   Finalização: 2026-11-07 18:14:14 -0300
Problema: no painel Notebooks não dá para apagar nada, renomear só pelo lápis, e a pasta dos notebooks só muda reiniciando com --root.
Resolução: menu de botão direito (seleciona o item; Rename e Delete) e DELETE recursivo defensivo (symlink só o link, 409 com kernel ativo por caminho real, nunca home/~/.notisbook); pasta dos notebooks trocável pelo + (preferences.json, --root trava, validação com dry_run antes de fechar abas, recusa home e ancestrais) e token de geração contra aba antiga — commits d651c95, 6e17fbe.

## 20261107_main_painel-so-notebooks.md
Criação: 2026-11-07 01:05:50 -0300   Finalização: 2026-11-07 01:24:09 -0300
Problema: o painel Notebooks mostra derby.log, metastore_db e spark-warehouse, que o Spark cria na pasta do notebook, misturados aos .ipynb.
Resolução: painel mostra só pastas e .ipynb (filtro no frontend, listagem completa preservada para nomes livres); spark-defaults de todo ambiente fixa warehouse em <raiz>/warehouse/spark e Derby em <raiz>/metastore (caminho entre aspas), catálogo único entre pastas; revision dos bundles 1→2 — commit 3580e32.

## 20261107_main_pasta-notisbook-home.md
Criação: 2026-11-07 00:38:00 -0300   Finalização: 2026-11-07 01:02:25 -0300
Problema: os ambientes ficam em ~/spark-notebooks e o warehouse em ~/spark-labs, sob uma SPARK_LABS_HOME com dois padrões, em vez de uma pasta própria do Notisbook.
Resolução: raiz única NOTISBOOK_HOME ou ~/.notisbook com envs/ e warehouse/iceberg, criada no start (falha aborta com o caminho que falhou e o motivo); SPARK_LABS_HOME abandonada; ambientes antigos reinstalados pela UI, sem migração — commit 43c9589.

## 20261107_main_topbar-linha-unica.md
Criação: 2026-11-07 00:17:45 -0300   Finalização: 2026-11-07 00:29:18 -0300
Problema: a topbar do notebook repete o nome e o "Unsaved" que a aba já mostra e gasta duas linhas com título e menu.
Resolução: topbar em linha única (menu à esquerda; Idle, seletor de ambiente e Variables à direita), sem título, dirty dot nem Saved/Unsaved (só Saving…/Save failed); lista do seletor ancorada à direita e rótulo truncado em larguras médias — commit f822b39.

## 20261106_main_painel-variaveis-kernel.md
Criação: 2026-11-06 23:47:42 -0300   Finalização: 2026-11-07 00:13:18 -0300
Problema: não dá pra ver as variáveis da sessão (Spark incluso) depois de executar células, como no painel Variables do IntelliJ.
Resolução: painel Variables à direita (toggle no header) com árvore de variáveis, Special Variables e detalhes de Spark, lido por sonda silenciosa com fila/cache próprios via REST, sem job Spark nem execução de property — commit f27ada7.

## 20261106_main_barra-execucao-kernel.md
Criação: 2026-11-06 23:02:44 -0300   Finalização: 2026-11-06 23:36:40 -0300
Problema: Run all, Interrupt e Restart só existem no menu Run (e o Run all no header) — não há controles de execução à mão junto das células.
Resolução: barra sticky de 44px (Run all / Interrupt / Restart) no topo das células, alinhada ao cabeçalho do painel lateral; Run all saiu do header; regras de habilitação compartilhadas com o menu Run via kernelReady/kernelHasWork — commit 8c32284.

## 20261106_main_banner-marca-notisbook.md
Criação: 2026-11-06 22:39:29 -0300   Finalização: 2026-11-06 22:52:39 -0300
Problema: o app não tem identidade visual — sem banner de marca, com um logo "N" genérico na barra lateral e sem favicon.
Resolução: banner de 56px acima das abas com o monograma Grid-N, "notisbook" e "Explore. Code. Transform.", cores por tokens que seguem o tema, favicon claro/escuro trocado pelo tema do app e marca sem repetição (sem logo no rail nem título na topbar da home) — commit 860374a.

## 20261106_main_ui-ingles-painel-dados.md
Criação: 2026-11-06 18:15:15 -0300   Finalização: 2026-11-06 21:57:37 -0300
Problema: painel Dados desperdiça espaço com botões em linhas próprias, FILES mostra "Unauthorized" após restart do servidor e a interface mistura pt-BR com inglês.
Resolução: ações do painel Data no cabeçalho com "+" no lugar de "Alterar diretório", root do Files carregado só após o auth (fim do 401) e toda a UI (frontend + mensagens de tela do backend) em inglês por troca direta de literais — commits 7372fd3, b64ab8f, f5c04c9, 7ad5d69, c2e2e15, 2d37cb9, ef1e477.

## 20261106_main_grid-html-celula-sql.md
Criação: 2026-11-06 17:16:05 -0300   Finalização: 2026-11-06 17:46:43 -0300
Problema: o resultado da célula SQL aparece como texto ASCII do show() e DDL sem colunas imprime "++ || ++", longe da grade legível do Databricks.
Resolução: grade HTML gerada no kernel por renderer em módulo oculto (instalado em silêncio no start/restart), usada pela célula SQL e por df/display(df) do PySpark; df.show() segue texto, DDL mostra "OK" — commits 9a07c2d, 851714f.

## 20261106_main_erros-e-avisos-spark-concisos.md
Criação: 2026-11-06 16:32:44 -0300   Finalização: 2026-11-06 17:06:27 -0300
Problema: avisos inofensivos do Spark (ex.: version-hint do Iceberg) aparecem com páginas de stack e erros reais do Spark vêm com o stack Java/py4j inteiro, ilegíveis.
Resolução: log4j2.properties por ambiente (RegexFilter no appender, garantido no start do kernel) suprime os avisos benignos curados; erros do Spark viram resumo com classe/SQLSTATE/posição e "ver detalhes" só na tela, .ipynb intacto — commits 801b8fc, 08c2ea1, fe783dc, ea2b8bf.

## 20261106_main_celula-spark-sql.md
Criação: 2026-11-06 15:26:15 -0300   Finalização: 2026-11-06 16:00:55 -0300
Problema: a célula só executa Python; para rodar SQL é preciso escrever spark.sql("...") à mão e não há como escolher a linguagem da célula.
Resolução: célula com seletor Python | SQL (à esquerda do ▶); em SQL o backend roda spark.sql(query).show() na SparkSession ativa, linguagem em metadata.notisbook.language e troca com comentário marcado — commits a584669, bddbe22, 2da4426.

## 20261105_main_spark-bundle-lakehouse.md
Criação: 2026-11-05 14:06:15 -0300   Finalização: 2026-11-06 14:45:21 -0300
Problema: ao instalar uma versão do Spark o ambiente sai sem Delta, Iceberg e Hudi, e não há como tê-los compatíveis sem configurar à mão.
Resolução: backend instala Delta/Iceberg/Hudi por matriz com sha256 fixo, kernel offline e pré-configurado, API com formats/bundle_status e 409 (commit 61e87ca); tela (T6) segue bloqueada por exceção CSED.

## 20261105_main_painel-dados-abaixo-do-menu.md
Criação: 2026-11-05 13:22:37 -0300   Finalização: 2026-11-05 13:44:12 -0300
Problema: o rail e o painel Dados ocupam a altura toda da janela, acima do nível do menu, diferente do Databricks.
Resolução: AppShell em coluna — abas e topbar/menu em largura total, rail + painel Dados + células abaixo, com a rolagem própria preservada — commit 0ae50ce.

## 20261105_main_painel-dados-funcional.md
Criação: 2026-11-05 11:28:53 -0300   Finalização: 2026-11-05 13:12:48 -0300
Problema: o painel Dados é só visual — não dá pra escolher diretório, copiar o path para o spark.read nem ver as tabelas Spark da sessão.
Resolução: painel Dados com Files (Finder nativo do macOS, árvore com rolagem própria, Copy Path absoluto/relativo) e Catalog (sondagem silenciosa da SparkSession ativa, com cache, limite e releitura) — commits 5e69c25, 02509b9, 0df9e58.

## 20261105_main_notisbook-mvp-react.md
Criação: 2026-11-05 02:40:09 -0300   Finalização: 2026-11-05 10:54:51 -0300
Problema: notebooks Spark dependem da UI padrão do Jupyter e de dois scripts shell divergentes para instalar e abrir os ambientes.
Resolução: app local Notisbook (FastAPI + React, visual Databricks) com kernels Spark por versão, gestão de ambientes via PyPI/uv e abertura em um comando (`./start.sh`); scripts antigos aposentados.
