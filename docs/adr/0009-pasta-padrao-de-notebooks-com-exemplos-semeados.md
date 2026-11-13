# ADR-0009: Pasta padrão de notebooks com exemplos semeados na primeira execução

**Status:** Proposto
**Data:** 2026-11-13 (geração do registro; data histórica da decisão não comprovada)
**Decisores:** Não identificados no material analisado

## Contexto
Na primeira execução o app precisa de uma pasta de notebooks para abrir. O usuário pode ter notebooks em uma pasta anterior, informar uma pasta pela CLI ou escolher uma pela interface.

## Decisão
- A pasta padrão é `<NOTISBOOK_HOME>/notebooks` (`default_root`).
- A raiz inicial é resolvida em ordem: `--root` da CLI (trava a troca pela UI) → preferência salva em `preferences.json` (validada; se inválida, cai no padrão com aviso) → pasta padrão.
- Primeira execução = `preferences.json` ausente e sem `--root` (`run_onboarding`). Nesse caso, se `~/notebooks` tiver notebooks e a pasta de dados for a padrão, ela é adotada; senão os notebooks de exemplo empacotados (`samples/delta.ipynb`, `hudi.ipynb`, `iceberg.ipynb`) são copiados para a pasta padrão.
- A cópia não sobrescreve arquivos existentes (temporário oculto + `os.link`) e grava o marcador `samples_seeded`, que impede recriar exemplos apagados pelo usuário. Falhas viram aviso no stderr, sem marcador, e o app sobe normalmente.

Motivação histórica não recuperada do código. A docstring de `onboarding.py` descreve a finalidade do marcador.

## Alternativas Consideradas
Não identificadas no material analisado. A adoção de `~/notebooks` indica compatibilidade com um local usado anteriormente, mas o código não registra o motivo.

## Consequências
*Análise feita a partir do código atual, não registro histórico.*

### Positivas
- O primeiro uso já traz exemplos de Delta, Iceberg e Hudi.
- Notebooks existentes do usuário não são sobrescritos nem recriados após exclusão.
- Validação única da raiz para API e CLI (`validate_notebooks_root`).

### Negativas
- A pasta padrão fica dentro da pasta de dados; a validação abre exceção explícita para `<dados>/notebooks` e seus descendentes.
- Os exemplos ficam no pacote Python (`samples/`) e precisam ser atualizados a cada release.

### Riscos
- Uma falha de E/S na primeira execução repete a tentativa a cada partida até ter sucesso. Esse é o comportamento previsto pelo código.

## Validação
- **Evidência no código:** `backend/src/notisbook/onboarding.py` (`run_onboarding`, `_seed_samples`, `_publish_sample`, `_adopt_legacy_root`), `backend/src/notisbook/config.py` (`default_root`), `backend/src/notisbook/__main__.py` (`_resolve_root`), `backend/src/notisbook/preferences.py` (`mark_samples_seeded`, `validate_notebooks_root`), `backend/src/notisbook/samples/*.ipynb`, `backend/src/notisbook/api/notebooks_root.py`.
- **Como confirmar:** `ls backend/src/notisbook/samples`; ler `run_onboarding` em `onboarding.py`.

## Notas de Implementação
- A troca de raiz em tempo de execução usa um contador de geração (`root_generation`, cabeçalho `X-Notisbook-Root-Generation`) para recusar operações iniciadas sob a raiz anterior.
- Notebooks semeados recebem modo `0o600`, igual aos criados pelo app.

---

**Autor:** Romerito Morais

**Versão:** 20261113022607

**Data:** 2026-11-13 02:26:07

**SKILL:** Document
