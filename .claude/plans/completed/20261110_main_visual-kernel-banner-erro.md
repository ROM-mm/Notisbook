# Visual em cartão — banner do kernel e botões da tela de erro

Branch: main   Fluxo: CODE-CHANGE   Peso: completo

Criação:     2026-11-10 14:01:07 -0300
Modificação: 2026-11-10 14:13:56 -0300
Finalização: 2026-11-10 14:13:56 -0300

## Objetivo

Levar ao banner do kernel (sessão encerrada sem volta) e à tela "Could not open the notebook" o padrão de cartão, conforme o mockup aprovado kernel-banner-v1: o `.banner` vira cartão branco com borda de 2px em `--color-danger`, raio 12px, sombra sólida `4px 4px 0` em `--color-danger-subtle` e ícone "!" contornado; o botão "Reopen kernel" segue o estilo `.neo` (texto na cor normal); na tela de erro "Try again" ganha borda e mini-sombra e "Close tab" fica ghost, via `.neo` em `.errorActions`. Só CSS — textos e a lógica de reabrir o kernel, recarregar e fechar a aba ficam iguais.

## Sub-tarefas
| id | intenção | especialista | depende de | wave | tipo |
|----|----------|--------------|-----------|------|------|
| T1 | `.banner` como cartão de alerta com ícone "!" via `::before` e escopo `.neo` para o botão | python-engineer | — | 1 | escrita |
| T2 | `.errorActions` compõe `.neo` | python-engineer | — | 1 | escrita |

## Ordem de execução (waves)
- Wave 1 (serial, escrita): T1 → T2

## Critérios de aceite
| id | critério | verificação | tipo |
|----|----------|-------------|------|
| T1 | Banner como cartão de alerta | `grep -A16 "^\.banner {" frontend/src/components/kernel/Kernel.module.css \| grep -E "2px solid var\(--color-danger\)\|4px 4px 0 var\(--color-danger-subtle\)\|composes: neo from"` encontra as três | feature |
| T1 | Ícone "!" no banner | `grep -A8 "^\.banner::before" frontend/src/components/kernel/Kernel.module.css \| grep "content:"` encontra | feature |
| T1 | Mensagem longa fica ao lado do ícone (não quebra sozinha para a linha seguinte) | `grep -A4 "^\.banner > span" frontend/src/components/kernel/Kernel.module.css \| grep -E "flex: 1\|min-width: 0"` encontra | bugfix |
| T2 | Botões da tela de erro no estilo novo | `grep -A4 "^\.errorActions {" frontend/src/components/notebook/Notebook.module.css \| grep "composes: neo from"` encontra | feature |
| T1 | Markup e lógica intocados | `git diff <baseline> -- frontend/src/components/kernel/KernelBanner.tsx frontend/src/components/notebook/NotebookView.tsx frontend/src/styles/global.css` vazio | constraint |
| T1 | Build do frontend passa | `npm --prefix frontend run build` exit 0 | constraint |

## Arquivos previstos
- `frontend/src/components/kernel/Kernel.module.css` — T1
- `frontend/src/components/notebook/Notebook.module.css` — T2

## Fora de escopo
- Promoção do `.neo` para a `.btn` global e os nits pendentes das rodadas anteriores.
- **Documentação de produto** — nenhuma.

## Não mexer
- `frontend/src/components/kernel/KernelBanner.tsx`, `frontend/src/components/notebook/NotebookView.tsx`, `frontend/src/styles/global.css`, `frontend/src/state/**`.
- Textos e a lógica de reabrir o kernel, recarregar e fechar a aba.

## Status
- [x] T1  - [x] T2

<!-- effort-ledger:start -->
| wave | agente | status | duration_ms | tokens |
|------|--------|--------|-------------|--------|
| 1 | python-engineer | OK | 18453 | 28363 |
| 1 | python-engineer | OK | 22677 | 28195 |
<!-- effort-ledger:end -->
