# Notisbook

![Notisbook](assets/banner.png)

## Título & Visão Geral do Negócio

O Notisbook é uma aplicação local de notebooks que roda na própria máquina da pessoa usuária e reúne, em uma interface web, a edição e execução de notebooks Jupyter (`.ipynb`) e o gerenciamento de ambientes Apache Spark com formatos de lakehouse (Delta Lake, Apache Iceberg e Apache Hudi). O pacote se descreve como "Local notebook UI and Spark environment manager" (`backend/pyproject.toml`).

Versão do pacote no código analisado: `0.4.1` (`backend/pyproject.toml`, `frontend/package.json`).

## Problema que Resolve

Montar um ambiente local de Spark com lakehouse exige combinar versão do Spark, JDK compatível, bibliotecas Python e jars de Delta/Iceberg/Hudi, além de um catálogo de tabelas que sobreviva entre sessões. O Notisbook automatiza essa montagem e oferece uma interface única para:

- instalar e remover versões do Spark em ambientes isolados, com os jars de lakehouse verificados por sha256 (`backend/src/notisbook/spark/installer.py`, `backend/src/notisbook/spark/bundles.py`);
- escolher automaticamente o JDK adequado à linha do Spark (`backend/src/notisbook/spark/prereqs.py`);
- manter um catálogo persistente de bancos e tabelas em SQLite, compartilhado entre kernels (`backend/src/notisbook/catalog/`);
- editar, executar e exportar notebooks sem depender de um servidor Jupyter completo (`backend/src/notisbook/kernels/service.py`).

Impacto de negócio quantificado (tempo economizado, adoção, custo): Não identificado no código analisado.

## Como Funciona (conceito)

1. O comando `notisbook` prepara a pasta de dados local, cria o catálogo SQLite e, na primeira execução, cria a pasta padrão de notebooks com exemplos (`backend/src/notisbook/__main__.py`, `backend/src/notisbook/onboarding.py`).
2. Um servidor local (FastAPI/Uvicorn) sobe apenas em `127.0.0.1`, gera um token de sessão aleatório e abre o navegador com esse token (`backend/src/notisbook/config.py`, `backend/src/notisbook/__main__.py`).
3. A interface web (React) é servida pelo próprio servidor e conversa com ele por REST e WebSocket (`backend/src/notisbook/static.py`, `frontend/src/api/`, `frontend/src/ws/`).
4. Cada notebook aberto pode iniciar um kernel IPython; ambientes Spark gerenciados ganham um kernelspec próprio com `JAVA_HOME` definido (`backend/src/notisbook/spark/kernelspec.py`).
5. Dentro do kernel, módulos ocultos renderizam resultados de células SQL (Spark SQL ou DuckDB) e mantêm a `SparkSession` sincronizada com o catálogo (`backend/src/notisbook/kernels/sql_cell.py`, `backend/src/notisbook/kernels/catalog_hook.py`).

## Benefícios

Benefícios observáveis no código (não são métricas medidas):

- **Ambientes reprodutíveis e reversíveis:** cada instalação do Spark cria um diretório novo, valida e só então troca o kernelspec; em falha, o ambiente anterior permanece intacto (`backend/src/notisbook/spark/installer.py`).
- **Downloads verificados:** jars de lakehouse têm sha256 fixado e são conferidos antes de entrar no ambiente (`backend/src/notisbook/spark/bundles.py`, `backend/src/notisbook/spark/installer.py`).
- **Catálogo persistente sem Hive:** bancos e tabelas ficam em `catalog.db` (SQLite) e podem ser consultados e alterados pela interface sem iniciar uma `SparkSession` (`backend/src/notisbook/api/catalog.py`, `backend/src/notisbook/catalog/`).
- **Acesso restrito à máquina local:** escuta somente em loopback e exige token em todas as rotas de API (`backend/src/notisbook/config.py`, `backend/src/notisbook/security.py`).
- **Exportação de notebooks:** `.py` no formato "notebook source" do Databricks, `.ipynb` e relatório HTML autocontido (`backend/src/notisbook/api/export.py`, `backend/src/notisbook/export/`).

## Casos de Uso

- Estudar ou prototipar pipelines PySpark localmente com Delta Lake, Iceberg ou Hudi; o pacote traz notebooks de exemplo para os três formatos (`backend/src/notisbook/samples/delta.ipynb`, `iceberg.ipynb`, `hudi.ipynb`).
- Consultar dados com células SQL em Spark SQL ou DuckDB no mesmo notebook (`backend/src/notisbook/kernels/sql_cell.py`).
- Manter várias versões do Spark instaladas e adicionar ou remover bibliotecas PyPI em cada ambiente (`backend/src/notisbook/api/spark.py`, `backend/src/notisbook/spark/packages.py`).
- Navegar pelo catálogo (bancos, tabelas e colunas), criar e excluir schemas (`backend/src/notisbook/api/catalog.py`).
- Exportar um notebook para levar o código a outra plataforma, como Databricks (`backend/src/notisbook/export/py_source.py`).

## Para Quem é

- Pessoas engenheiras e analistas de dados que querem um ambiente Spark/lakehouse local sem configurar Jupyter, JDK e jars manualmente.
- Uso individual em estação de trabalho macOS: a detecção de JDK usa `/usr/libexec/java_home` e o seletor de pastas nativo usa `osascript` (`backend/src/notisbook/spark/prereqs.py`, `backend/src/notisbook/files/native_picker.py`). Suporte a outros sistemas operacionais: Não identificado no código analisado.

## Começo Rápido (básico)

### Pré-requisitos

- Para usar ambientes Spark: `uv` e um JDK compatível (17 para Spark 3.x; 21 ou 17 para as demais linhas) (`backend/src/notisbook/spark/prereqs.py`, `backend/src/notisbook/spark/installer.py`).
- Para rodar a partir do código-fonte: `uv`, `node` e `npm` (`start.sh`) e Python `>=3.12` (`backend/pyproject.toml`).

### Instalação via Homebrew

A distribuição é feita pela fórmula `notisbook` do tap `rom-mm/tap` (`scripts/release.sh`, variáveis `TAP_NAME` e `FORMULA_REF`):

```bash
brew install rom-mm/tap/notisbook
```

Atualização, conforme a mensagem final de `scripts/release.sh`:

```bash
brew update && brew upgrade notisbook
```

O conteúdo da fórmula (dependências declaradas, caveats) não está neste repositório: Não identificado no código analisado.

### Executar

```bash
notisbook
```

O comando imprime a URL `http://127.0.0.1:<porta>/?token=<token>` e abre o navegador (`backend/src/notisbook/__main__.py`).

### A partir do código-fonte

```bash
./start.sh
```

O script instala as dependências do frontend se necessário, recompila o frontend quando há mudanças e executa `uv run --project backend notisbook`, repassando os argumentos (`start.sh`).

## Exemplos de Uso

Opções da CLI (`backend/src/notisbook/__main__.py`):

```bash
# Porta diferente da padrão (8765)
notisbook --port 9000

# Pasta de notebooks fixa (trava a troca de pasta pela interface)
notisbook --root ~/meus-notebooks

# Não abrir o navegador automaticamente
notisbook --no-browser

# Exibir a versão
notisbook --version
```

Pasta de dados alternativa, pela variável de ambiente lida em `backend/src/notisbook/config.py`:

```bash
NOTISBOOK_HOME=/caminho/para/dados notisbook
```

Na primeira execução (sem `--root` e sem `preferences.json`), os notebooks de exemplo de Delta, Iceberg e Hudi são copiados para `<pasta de dados>/notebooks` (`backend/src/notisbook/onboarding.py`).

## Onde Encontrar Mais Detalhes

- Backend (servidor, kernels, catálogo e ambientes Spark): [backend/src/notisbook/](backend/src/notisbook/)
- Frontend (interface web): [frontend/src/](frontend/src/)
- Build e release: [scripts/](scripts/)

## Licença

Apache License 2.0, declarada em `backend/pyproject.toml` (`license = "Apache-2.0"`) e confirmada pelo texto em `LICENSE` e `backend/LICENSE`.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
