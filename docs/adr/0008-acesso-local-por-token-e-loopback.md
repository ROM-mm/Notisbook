# ADR-0008: Acesso local por loopback e token por inicialização

**Status:** Proposto
**Data:** 2026-11-11 (geração do registro; data da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
O servidor executa código arbitrário no kernel; outro processo ou site não pode acioná-lo.

## Decisão
Bind fixo em `127.0.0.1`; token aleatório por start, aceito por header Bearer, cookie HttpOnly SameSite=Strict ou query; verificação de Host em rotas sensíveis e de Origin/Host no WebSocket; access log desligado porque o token viaja na query.

Motivação declarada em comentário: o host não é configurável de propósito, e o access log fica desligado para não registrar o token.

## Alternativas Consideradas
Não identificadas no material analisado.

## Consequências

### Positivas
- Sem exposição na rede.
- Token não persiste em disco nem no storage do navegador.

### Negativas
- Acesso remoto não é suportado.
- Sem log de acesso HTTP para diagnóstico.

### Riscos
- Rotas REST sem verificação de Host dependem só do token e do cookie. Mitigação: cookie SameSite=Strict.

## Validação
- **Evidência no código:** `backend/src/notisbook/security.py`, `backend/src/notisbook/config.py:11-12`, `backend/src/notisbook/__main__.py:66-67`
- **Como confirmar:** `grep -n HOST backend/src/notisbook/config.py`

---

**Autor:** Romerito Morais

**Versão:** 20261111125851

**Data:** 2026-11-11 12:58:51

**SKILL:** Document
