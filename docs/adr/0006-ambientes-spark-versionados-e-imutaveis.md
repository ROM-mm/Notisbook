# ADR-0006: Ambientes Spark versionados e imutáveis, com troca atômica do kernelspec

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
O Notisbook instala e reinstala versões do Spark (PySpark, ipykernel, DuckDB, bundle de lakehouse) sob demanda pela interface. Uma instalação com falha não pode deixar o usuário sem um kernel funcional.

## Decisão
Cada instalação cria um diretório novo `<home>/envs/spark-<versão>-<id aleatório>/` com um venv criado por `uv` (Python 3.12), instala os pacotes, baixa o bundle, valida o ambiente (smoke test) e somente então troca o `kernel.json` de forma atômica (arquivo temporário + `os.replace`). Os ambientes anteriores da mesma versão são removidos depois. Qualquer falha descarta o diretório novo e mantém o kernelspec anterior.

O `kernel.json` é escrito diretamente (não por `ipykernel install`) com `env` explícito: `JAVA_HOME`, `PYSPARK_PYTHON`, `PYSPARK_DRIVER_PYTHON` e `SPARK_CONF_DIR`, nunca `SPARK_HOME`/`PYTHONPATH`. Remoções movem o ambiente para `envs/.trash-*` antes de apagar, e sobras são varridas na partida (`sweep_trash`). Subprocessos são sempre executados com lista de argumentos, sem shell.

A docstring de `spark/installer.py` descreve o comportamento; a motivação histórica não foi recuperada do código além do comentário de que variáveis vazadas fariam a validação importar outro PySpark.

## Alternativas Consideradas
`spark/kernelspec.py` registra que o `kernel.json` não é gerado por `ipykernel install`, para garantir um `env` explícito. Outras alternativas não foram identificadas no material analisado.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Instalações com falha ou canceladas não afetam o ambiente em uso.
- Isolamento entre versões do Spark e em relação a variáveis do shell do usuário.
- Bloqueio por nome de kernel impede jobs concorrentes de mutação (`InstallInProgress`).

### Negativas
- Requer `uv` e um JDK compatível no host (pré-requisitos verificados em `spark/prereqs.py`).
- Espaço em disco duplicado durante a reinstalação.

### Riscos
- Remoção parcial de diretórios. Mitigação observada: renomeação para `.trash-*` e varredura posterior, com `RemoveFailed` listando o que restou.

## Validação
- **Evidência no código:** `backend/src/notisbook/spark/installer.py` (docstring, `_run`, `_validate`, `_cleanup`, `sweep_trash`), `backend/src/notisbook/spark/kernelspec.py` (`write_kernelspec`, `ENVS_DIR`), `backend/src/notisbook/spark/packages.py`.
- **Como confirmar:** ler `_run` em `spark/installer.py` e verificar a ordem das fases em `PHASES`.

## Notas de Implementação
- Fases: `prereqs`, `python`, `venv`, `install`, `bundle`, `validate`, `kernelspec`, `cleanup`.
- Kernelspecs ficam no diretório de kernels do usuário (`jupyter_data_dir()/kernels`), que respeita `JUPYTER_DATA_DIR`.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
