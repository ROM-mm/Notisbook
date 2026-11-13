# ADR-0001: Kernels via jupyter_client com protocolo WebSocket próprio

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
O Notisbook precisa executar células de notebooks (Python, Spark SQL e DuckDB SQL) em kernels locais e transmitir saídas em tempo real para a interface React. O backend é uma aplicação FastAPI que se comunica com o frontend via REST e WebSocket.

## Decisão
O backend gerencia os kernels diretamente com a biblioteca `jupyter_client` (`AsyncKernelManager`, `AsyncKernelClient`, `KernelSpecManager`), sem `jupyter_server`. O módulo `kernels/service.py` declara ser o único que importa `jupyter_client`, "para que o backend possa ser trocado por `jupyter_server` sem tocar na API nem no protocolo WS".

Entre a interface e cada sessão de kernel existe um protocolo WebSocket próprio, versionado (`v: 1`), definido com modelos Pydantic em `kernels/protocol.py` e espelhado em TypeScript em `frontend/src/ws/protocol.ts`:
- Cliente → servidor: `execute` (com `cell_id`, `code` e `language` ∈ `python | sql | duckdb`), `interrupt`, `restart`.
- Servidor → cliente: `status`, `execute_input`, `output`, `clear_output`, `execute_reply`, `error`.

O canal fica em `/api/sessions/{id}/channel` (`api/sessions.py`), com códigos de fechamento próprios (`4409` para sessão assumida por outra conexão, `4404` para sessão desconhecida).

Motivação histórica não recuperada do código, exceto a intenção de isolamento declarada na docstring de `kernels/service.py`.

## Alternativas Consideradas
O próprio código cita `jupyter_server` como substituto possível no futuro (docstring de `kernels/service.py`). Não há evidência de que tenha sido avaliado e rejeitado na decisão original.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- Contrato de mensagens enxuto e tipado nas duas pontas, com validação por discriminador (`client_message_adapter`).
- Acoplamento a `jupyter_client` concentrado em um único módulo.
- Controle direto sobre limites de saída (ex.: `STREAM_LIMIT_BYTES` de 1 MB por célula) e sobre o ciclo de vida das sessões.

### Negativas
- Clientes Jupyter padrão (JupyterLab, extensões) não conseguem falar com o backend; o protocolo é exclusivo do Notisbook.
- A sincronia entre `protocol.py` e `protocol.ts` é manual.

### Riscos
- Divergência entre os tipos Python e TypeScript ao evoluir o protocolo. Mitigação possível: manter o campo `v` e incrementar a versão em mudanças incompatíveis.

## Validação
- **Evidência no código:** `backend/src/notisbook/kernels/service.py` (imports de `jupyter_client` e docstring), `backend/src/notisbook/kernels/protocol.py`, `backend/src/notisbook/api/sessions.py` (`ws_router`, `WS_REPLACED`, `WS_UNKNOWN_SESSION`), `frontend/src/ws/protocol.ts` (`PROTOCOL_VERSION = 1`), dependência `jupyter-client>=8.6` em `backend/pyproject.toml`.
- **Como confirmar:** `grep -rn "jupyter_client" backend/src/notisbook` deve listar apenas `kernels/service.py` (e `jupyter_core` em módulos de Spark); comparar os tipos de `kernels/protocol.py` com `frontend/src/ws/protocol.ts`.

## Notas de Implementação
- Variáveis de ambiente que mudariam o Spark resolvido pelo kernel (`SPARK_HOME`, `PYTHONPATH`, `PYSPARK_*`, `SPARK_CONF_DIR`) são removidas antes de iniciar o kernel (`SCRUBBED_ENV` em `kernels/service.py`).
- Os jobs de instalação usam um WebSocket separado (`/api/jobs/{id}/events`, em `backend/src/notisbook/api/jobs.py` e `frontend/src/ws/jobs.ts`), cujos eventos têm formato próprio e estão fora desta decisão.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
