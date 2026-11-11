# ADR-0001: Kernels via jupyter_client com protocolo WebSocket próprio

**Status:** Proposto
**Data:** 2026-11-11 (geração do registro; data da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
O Notisbook precisa iniciar, interromper e reiniciar kernels e transmitir a saída de cada célula para a interface web.

## Decisão
O backend controla os kernels diretamente com `jupyter_client` (`AsyncKernelManager`), isolado em `kernels/service.py`, e expõe ao frontend um protocolo WebSocket próprio (v1), orientado a célula: `execute`, `interrupt`, `restart` do cliente; `status`, `execute_input`, `output`, `clear_output`, `execute_reply`, `error` do servidor.

Motivação declarada em comentário de código: `service.py` é o único módulo que importa `jupyter_client`, para que o backend possa ser trocado por `jupyter_server` sem mexer na API nem no protocolo WS. Outras motivações históricas não foram recuperadas do código.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências

### Positivas
- Protocolo pequeno e tipado (pydantic) sob controle do projeto.
- Troca do motor de kernels concentrada num único módulo.

### Negativas
- O projeto mantém por conta própria gestão de sessões, connection files e limites de saída (1 MB por célula).
- Clientes Jupyter padrão não falam com este protocolo.

### Riscos
- Divergência com mudanças do `jupyter_client`. Mitigação: dependência isolada em um módulo.

## Validação
- **Evidência no código:** `backend/src/notisbook/kernels/service.py:1-4`, `backend/src/notisbook/kernels/protocol.py`
- **Como confirmar:** `grep -rl jupyter_client backend/src/notisbook`

---

**Autor:** Romerito Morais

**Versão:** 20261111125851

**Data:** 2026-11-11 12:58:51

**SKILL:** Document
