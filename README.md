<p align="center">
  <img src="docs/assets/banner.png" alt="Notisbook — Spark it up locally. Iceberg, Delta, Hudi &amp; Parquet — on your laptop." width="100%">
</p>

# Notisbook

Interface local de notebooks com gerenciador de ambientes Apache Spark — para escrever e executar notebooks Python, Spark SQL e DuckDB SQL no próprio computador, com tabelas Iceberg, Delta, Hudi e Parquet, sem cluster e sem serviço na nuvem.

## Problema que Resolve

Experimentar Spark e formatos de lakehouse localmente costuma exigir montar à mão uma versão de PySpark, um JDK compatível, os jars de Delta/Iceberg/Hudi, um metastore e um servidor de notebooks. O Notisbook reúne isso numa única aplicação: ele instala ambientes Spark versionados, escolhe o JDK certo para cada linha do Spark, configura os formatos de tabela e mantém um catálogo persistente das tabelas criadas.

## Como Funciona

- Um servidor local (FastAPI) serve a interface web e fala com kernels Jupyter, um por notebook aberto.
- Cada versão do Spark instalada vira um **ambiente** isolado (venv criado com `uv`), com PySpark do PyPI, os jars de lakehouse baixados do Maven Central (sha256 conferido) e um kernel próprio.
- As células podem ser **Python**, **Spark SQL** (executado na SparkSession ativa) ou **DuckDB SQL** (banco em memória por kernel).
- O catálogo de tabelas fica num SQLite (`catalog.db`), lido pelo painel Data sem precisar abrir uma SparkSession.
- Tudo roda em `127.0.0.1`, protegido por um token gerado a cada inicialização.

## Benefícios

- Ambientes Spark 3.x e 4.x lado a lado, instalados e removidos pela própria interface.
- Iceberg, Delta, Hudi e Parquet prontos para uso em cada ambiente.
- Catálogo de tabelas que sobrevive ao fim da sessão Spark.
- Notebooks no formato `.ipynb` padrão, com export para `.ipynb`, `.py` (formato Databricks) e `.html` autocontido.

Ganhos de desempenho ou produtividade não foram medidos: `Não identificado no código analisado`.

## Casos de Uso

- Estudar e prototipar transformações PySpark e Spark SQL antes de levá-las a um cluster.
- Testar tabelas Delta, Iceberg e Hudi localmente.
- Comparar o comportamento de versões diferentes do Spark.
- Consultas rápidas em DuckDB ao lado de código Spark.

## Para Quem é

Engenharia e análise de dados que trabalham com Spark e querem um ambiente local completo. Os recursos dependem de macOS (Homebrew, `/usr/libexec/java_home`, seletor de pasta nativo).

## Instalação

A forma correta de instalar é pelo **Homebrew**, a partir do tap do projeto [`ROM-mm/homebrew-tap`](https://github.com/ROM-mm/homebrew-tap):

```bash
brew tap rom-mm/tap
brew trust rom-mm/tap
brew install notisbook
```

- **`brew trust` é obrigatório.** O Homebrew recusa fórmula de tap de terceiros sem confiança explícita e falha com `Refusing to load formula rom-mm/tap/notisbook from untrusted tap rom-mm/tap`. Para confiar só nesta fórmula, em vez do tap inteiro: `brew trust --formula rom-mm/tap/notisbook`.
- A instalação compila dependências nativas (como `pyzmq`) e leva alguns minutos.
- O Homebrew instala junto `python@3.12`, `openjdk@17`, `uv`, `zeromq` e `libyaml`. O JDK 17 atende Spark 3.x e 4.x; o Notisbook o encontra sozinho, sem configurar `JAVA_HOME`.

Conferir a instalação:

```bash
notisbook --version
```

Atualizar e remover:

```bash
brew upgrade notisbook
brew uninstall notisbook
brew untap rom-mm/tap
```

Desinstalar não apaga os dados em `~/.notisbook` (ambientes, catálogo, warehouse) nem os notebooks.

## Começo Rápido

```bash
notisbook
```

O comando inicia o servidor em `http://127.0.0.1:8765` e abre o navegador com a URL que contém o token da sessão. Opções:

| opção | efeito |
|---|---|
| `--port N` | usa outra porta |
| `--root DIR` | fixa a pasta dos notebooks |
| `--no-browser` | não abre o navegador |
| `--version` | mostra a versão |

Depois de abrir:

1. Em **Settings**, na seção de ambientes Spark, instale uma versão do Spark.
2. Crie um notebook (**New notebook**) e escolha o ambiente no seletor de kernel.
3. Execute uma célula, por exemplo `spark.range(3).show()`.

Problemas comuns:

- **`address already in use`** — outra instância já usa a porta 8765. Encerre-a ou use `notisbook --port 8766`.
- **Outro `notisbook` no PATH** — um virtualenv ativo com o Notisbook instalado esconde o do Homebrew. Rode `$(brew --prefix)/bin/notisbook` ou desative o venv.

## Exemplos de Uso

Célula Python:

```python
df = spark.range(5)
display(df)            # grade HTML, 50 linhas por padrão
display(df, n=200)     # até 1000 linhas
```

Célula Spark SQL (usa a SparkSession já ativa):

```sql
SELECT id, id * 2 AS dobro FROM range(5)
```

Célula DuckDB SQL (banco em memória do kernel):

```sql
SELECT 42 AS resposta
```

## Desenvolvimento

Requisitos: Python 3.12+, `uv`, Node.js e npm, JDK 17 (ou 21 para Spark 4.x).

```bash
./start.sh                      # instala deps do frontend, compila se preciso e sobe o backend
cd frontend && npm run dev      # Vite em :5173 com proxy para o backend em :8765
```

Gerar os artefatos de release (sdist e wheel com o frontend embutido, mais o sha256):

```bash
uv run --project backend python scripts/build_release.py
```

Variáveis de ambiente: `NOTISBOOK_HOME` (pasta de dados, padrão `~/.notisbook`), `NOTISBOOK_FRONTEND_DIST`, `NOTISBOOK_PYPI_URL`, `NOTISBOOK_MAVEN_URL`.

## Onde Encontrar Mais Detalhes

- [Arquitetura](docs/ARCHITECTURE.md)
- [Diagramas C4](docs/arch/)
- [Decisões arquiteturais (ADRs)](docs/adr/)
- [Especificação da API](docs/api/swagger.yaml)

## Licença

Apache-2.0 — ver [LICENSE](LICENSE).

---

**Autor:** Romerito Morais

**Versão:** 20261111125851

**Data:** 2026-11-11 12:58:51

**SKILL:** Document
