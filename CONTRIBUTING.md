# Contribuindo com o Notisbook

Obrigado pelo interesse em contribuir! Este guia explica como preparar o ambiente, como organizar branches e
commits e como funciona o processo de revisão até a publicação de uma versão.

## Pré-requisitos

- Mac com **Apple silicon** (arm64). Desde a versão 0.9.0, o Notisbook não oferece suporte a Macs Intel.
- [Git](https://git-scm.com/) e uma conta no GitHub.
- [`uv`](https://docs.astral.sh/uv/) para o backend (Python 3.12, conforme `backend/.python-version`).
- [Node.js](https://nodejs.org/) e `npm` para o frontend.
- Opcional, apenas para trabalhar com runtimes Spark: JDK 17 (Spark 3.x) ou JDK 21/17 (Spark 4.x).
- Opcional, apenas para o runtime AWS Glue: Docker (por exemplo, via Colima). Veja os detalhes no [README](README.md#requirements).

## Como contribuir

- **Bugs e sugestões de funcionalidade:** abra uma [Issue](https://github.com/ROM-mm/Notisbook/issues) descrevendo
  o problema ou a proposta, com passos para reproduzir quando for um bug.
- **Dúvidas e ideias em aberto:** use as [Discussions](https://github.com/ROM-mm/Notisbook/discussions).
- **Mudanças grandes** (nova funcionalidade, alteração de arquitetura, mudança de comportamento): abra uma Issue ou
  Discussion **antes** de começar a implementar, para alinhar a abordagem com o mantenedor e evitar retrabalho.
- Correções pequenas (erros de digitação, ajustes pontuais) podem ir direto para um Pull Request.

Todas as contribuições são feitas por **fork** do repositório.

## Preparando o ambiente

1. Faça um fork de [ROM-mm/Notisbook](https://github.com/ROM-mm/Notisbook) pela interface do GitHub.
2. Clone o seu fork e adicione o repositório original como `upstream`:

   ```bash
   git clone https://github.com/<seu-usuario>/Notisbook.git
   cd Notisbook
   git remote add upstream https://github.com/ROM-mm/Notisbook.git
   ```

3. Trabalhe sempre a partir da `develop` atualizada:

   ```bash
   git fetch upstream
   git checkout develop
   git merge --ff-only upstream/develop
   ```

4. Rode o Notisbook a partir do código-fonte:

   ```bash
   ./start.sh                  # sobe em http://127.0.0.1:8765
   ./start.sh --port 8766      # usa outra porta
   ./start.sh --replace        # encerra a instância em execução e sobe a versão de desenvolvimento
   ```

   O `start.sh` verifica se `uv`, `node` e `npm` estão instalados, roda `npm ci` no frontend quando
   `node_modules` não existe, refaz o build do frontend quando o código mudou e inicia o backend com
   `uv run --project backend notisbook`. Os demais argumentos (`--root`, `--no-browser`) são repassados ao
   `notisbook`.

5. Comandos úteis do frontend (definidos em `frontend/package.json`):

   ```bash
   npm --prefix frontend run typecheck   # checagem de tipos TypeScript
   npm --prefix frontend run build       # typecheck + build de produção (Vite)
   npm --prefix frontend run dev         # servidor de desenvolvimento do Vite
   ```

> O repositório ainda não tem uma suíte de testes automatizados nem um linter configurado. Até que existam, valide
> suas mudanças rodando o app com `./start.sh` e, no frontend, com `npm --prefix frontend run build`.

## Fluxo de branches

A branch padrão é a `develop`. A `main` recebe apenas as versões publicadas.

```text
 fork: feat/<descricao>  ─┐
 fork: fix/<descricao>   ─┼──(PR, squash)──▶ develop ──(PR de release, mantenedor)──▶ main ──▶ tag/release
 fork: docs/<descricao>  ─┘                     ▲                                       │
                                                └──────────── merge de volta ───────────┘
```

Crie sua branch a partir da `develop` atualizada, usando o prefixo correspondente ao tipo de mudança:

| Prefixo | Quando usar | Exemplo |
|---|---|---|
| `feat/` | Nova funcionalidade | `feat/exportar-csv` |
| `fix/` | Correção de bug | `fix/kernel-duckdb-timeout` |
| `docs/` | Somente documentação | `docs/guia-glue` |
| `chore/` | Manutenção, dependências, build | `chore/atualizar-vite` |
| `refactor/` | Refatoração sem mudança de comportamento | `refactor/catalogo-sqlite` |

```bash
git checkout -b feat/<descricao> upstream/develop
```

Use nomes curtos, em minúsculas e com hífens.

## Commits

Os commits seguem o padrão [Conventional Commits](https://www.conventionalcommits.org/pt-br/v1.0.0/):

```text
<tipo>(<escopo opcional>): <descrição curta no imperativo>
```

Tipos aceitos: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `build`, `ci`.

Exemplos:

```text
feat(export): add CSV export from the File menu
fix(duckdb): keep the iceberg extension pinned on kernel restart
docs(readme): document the --root option
```

Uma mudança incompatível deve ser indicada com `!` após o tipo (por exemplo, `feat!: ...`) ou com um rodapé
`BREAKING CHANGE:`.

## Abrindo um Pull Request

1. **O PR deve sempre apontar para a `develop`.** PRs abertos contra a `main` terão a base alterada para a `develop`
   pelo mantenedor.
2. **O título do PR deve seguir Conventional Commits.** Como o merge é feito com *Squash and merge*, o título vira a
   mensagem do commit final na `develop`.
3. Mantenha a branch atualizada com a `develop` do repositório original, por rebase:

   ```bash
   git fetch upstream
   git rebase upstream/develop
   git push --force-with-lease
   ```

   ou pelo botão **Update branch** na página do PR.
4. Preencha o template do Pull Request (resumo, tipo de mudança, Issue relacionada, como testar e checklist).
5. Prefira PRs **pequenos e focados**: um assunto por PR facilita a revisão e acelera o merge.
6. Não inclua segredos, tokens, credenciais ou dados pessoais no código, nos commits ou nas capturas de tela.

> Os workflows do GitHub Actions em PRs vindos de forks só executam depois da aprovação do mantenedor.

## Revisão e aprovação

- O mantenedor, @ROM-mm, revisa todos os PRs para a `develop`.
- Para o merge, são exigidos **1 aprovação** do mantenedor e **todas as conversas de revisão resolvidas**.
- Se forem solicitadas mudanças (*Request changes*), ajuste a branch e responda ou resolva os comentários.
- Um novo push depois da aprovação **descarta a aprovação anterior**: o PR precisará ser aprovado novamente.
- O merge é feito exclusivamente por **Squash and merge**, e a branch de origem é apagada automaticamente após o
  merge.
- Force push e exclusão das branches `main` e `develop` são bloqueados.

## Releases

- As releases são feitas **somente pelo mantenedor** @ROM-mm.
- O mantenedor abre um PR de release da `develop` para a `main`, integrado com *merge commit*. A tag e a release são
  publicadas a partir da `main` e, em seguida, a `main` é integrada de volta na `develop`.
- Contribuidores **nunca** abrem PRs para a `main`.
- O [`CHANGELOG.md`](CHANGELOG.md) segue o padrão [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), em
  inglês. Não crie nem altere seções de versão (por exemplo, `## [0.10.0]`) a menos que o mantenedor peça.

## Reportando vulnerabilidades

**Não abra uma Issue pública** para relatar uma vulnerabilidade de segurança.

Use o recurso de relato privado do GitHub: na aba **Security** do repositório, clique em
**Report a vulnerability** e descreva o problema, o impacto e os passos para reproduzir. O mantenedor responderá
pelo próprio canal privado.

## Licença

O Notisbook é distribuído sob a licença [Apache-2.0](LICENSE). Ao enviar uma contribuição, você concorda que ela
será licenciada nos mesmos termos.
