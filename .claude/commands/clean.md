---
description: Lista e, com confirmação, apaga os resíduos de build e release (use "--deep" para incluir o regenerável caro)
argument-hint: "[--deep]"
allowed-tools: Bash(python3 scripts/clean.py:*), Bash(git status:*)
---

# /clean — limpeza de resíduos de build do Notisbook

## Pré-requisitos

- Rodar na raiz do repositório `Notisbook-app`.
- `python3` e `git`. `uv` é opcional (sem `uv`, a etapa `uv cache clean` é pulada com um aviso).
- Argumento opcional em `$ARGUMENTS`: `--deep` inclui o regenerável caro (`frontend/node_modules`, `backend/.venv`) e o `uv cache clean` (apaga o cache inteiro do uv).

## Regras gerais

- Responda em português.
- **Nada é apagado sem confirmação.** O primeiro comando é sempre `--dry-run`, que só lista.
- Cada confirmação vai **sozinha** na mensagem. Só `sim` (ou variação clara: "s", "pode", "yes") autoriza; qualquer outra resposta encerra o comando sem apagar nada.
- Nunca use `git clean`, `rm -rf` ou `uv cache clean` direto; toda remoção passa por `scripts/clean.py`, que preserva arquivos rastreados pelo git e os artefatos da versão atual.

## Passo 1 — lista

Se `$ARGUMENTS` contém `--deep`, rode:

```bash
python3 scripts/clean.py --dry-run --deep
```

Senão:

```bash
python3 scripts/clean.py --dry-run
```

Mostre a lista ao usuário (itens, tamanhos e total) e os avisos que o script imprimir. Se o script disser `Nada a limpar.`, informe e **pare**. Se o script falhar, mostre o erro e **pare**.

## Passo 2 — confirmação

Pergunte, sozinho na mensagem: **"Apago os itens acima? A lista é recalculada ao apagar; se mudar, aviso antes de concluir."**.

Com `--deep`, se a lista mostrou a etapa `uv cache clean` e o usuário respondeu `sim`, faça uma **segunda pergunta, sozinha na mensagem**: **"Rodo também o `uv cache clean`?"** Avise que apaga o cache **inteiro** do uv, é **global** (afeta outros projetos) e o próximo `uv run`/`./start.sh` fica mais lento por baixar tudo de novo. Avise também para **parar o app** (`./start.sh`/`uv run`) antes de responder `sim`: com o cache em uso, o uv espera o lock e o comando fica parado.

## Passo 3 — limpeza

Com `sim` na primeira pergunta, rode `--yes`: ele **recalcula** os alvos no momento de apagar, então a lista pode diferir da confirmada no dry-run. Escolha o comando pelo modo e pela resposta do uv.

Sem `--deep`:

```bash
python3 scripts/clean.py --yes
```

Com `--deep` e uv aceito:

```bash
python3 scripts/clean.py --yes --deep
```

Com `--deep` e uv recusado, ou a lista sem a etapa do uv (acrescente `--skip-uv`):

```bash
python3 scripts/clean.py --yes --deep --skip-uv
```

Compare o que foi removido com a lista do Passo 1 e avise o usuário se houver diferença. Mostre o que o script removeu e toda linha `erro:` ou `aviso:` impressa. Depois confira que a árvore git não mudou:

```bash
git status --short
```

Com qualquer outra resposta na primeira pergunta, diga que nada foi apagado e não faça a segunda.
