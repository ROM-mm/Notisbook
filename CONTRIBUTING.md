# Contributing to Notisbook

Thanks for your interest in contributing! This guide explains how to set up your environment, how to organize
branches and commits, and how the review process works all the way to a published release.

## Prerequisites

- Mac with **Apple silicon** (arm64). Since version 0.9.0, Notisbook does not support Intel Macs.
- [Git](https://git-scm.com/) and a GitHub account.
- [`uv`](https://docs.astral.sh/uv/) for the backend (Python 3.12, as set in `backend/.python-version`).
- [Node.js](https://nodejs.org/) and `npm` for the frontend.
- Optional, only for working with Spark runtimes: JDK 17 (Spark 3.x) or JDK 21/17 (Spark 4.x).
- Optional, only for the AWS Glue runtime: Docker (for example, via Colima). See the details in the [README](README.md#requirements).

## How to contribute

- **Bugs and feature requests:** open an [Issue](https://github.com/ROM-mm/Notisbook/issues) describing the
  problem or the proposal, with steps to reproduce when it is a bug.
- **Questions and open-ended ideas:** use [Discussions](https://github.com/ROM-mm/Notisbook/discussions).
- **Large changes** (new feature, architecture change, behavior change): open an Issue or Discussion **before**
  you start implementing, to agree on the approach with the maintainer and avoid rework.
- Small fixes (typos, one-off adjustments) can go straight to a Pull Request.

All contributions are made through a **fork** of the repository.

## Setting up the environment

1. Fork [ROM-mm/Notisbook](https://github.com/ROM-mm/Notisbook) from the GitHub interface.
2. Clone your fork and add the original repository as `upstream`:

   ```bash
   git clone https://github.com/<your-username>/Notisbook.git
   cd Notisbook
   git remote add upstream https://github.com/ROM-mm/Notisbook.git
   ```

3. Always work from an up-to-date `develop`:

   ```bash
   git fetch upstream
   git checkout develop
   git merge --ff-only upstream/develop
   ```

4. Run Notisbook from source:

   ```bash
   ./start.sh                  # starts at http://127.0.0.1:8765
   ./start.sh --port 8766      # uses a different port
   ./start.sh --replace        # stops the running instance and starts the development version
   ```

   `start.sh` checks that `uv`, `node` and `npm` are installed, runs `npm ci` in the frontend when
   `node_modules` does not exist, rebuilds the frontend when its code has changed, and starts the backend with
   `uv run --project backend notisbook`. Any other arguments (`--root`, `--no-browser`) are passed through to
   `notisbook`.

5. Useful frontend commands (defined in `frontend/package.json`):

   ```bash
   npm --prefix frontend run typecheck   # TypeScript type checking
   npm --prefix frontend run build       # typecheck + production build (Vite)
   npm --prefix frontend run dev         # Vite development server
   ```

> The repository does not yet have an automated test suite or a configured linter. Until they exist, validate
> your changes by running the app with `./start.sh` and, for the frontend, with `npm --prefix frontend run build`.

## Branch workflow

The default branch is `develop`. `main` only receives published releases.

```text
 fork: feat/<description>  ─┐
 fork: fix/<description>   ─┼──(PR, squash)──▶ develop ──(release PR, maintainer)──▶ main ──▶ tag/release
 fork: docs/<description>  ─┘                     ▲                                    │
                                                  └─────────────── merge back ─────────┘
```

Create your branch from an up-to-date `develop`, using the prefix that matches the type of change:

| Prefix | When to use | Example |
|---|---|---|
| `feat/` | New feature | `feat/export-csv` |
| `fix/` | Bug fix | `fix/kernel-duckdb-timeout` |
| `docs/` | Documentation only | `docs/glue-guide` |
| `chore/` | Maintenance, dependencies, build | `chore/update-vite` |
| `refactor/` | Refactoring with no behavior change | `refactor/sqlite-catalog` |

```bash
git checkout -b feat/<description> upstream/develop
```

Use short, lowercase names with hyphens.

## Commits

Commits follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification:

```text
<type>(<optional scope>): <short description in the imperative mood>
```

Accepted types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`, `build`, `ci`.

Examples:

```text
feat(export): add CSV export from the File menu
fix(duckdb): keep the iceberg extension pinned on kernel restart
docs(readme): document the --root option
```

A breaking change must be marked with `!` after the type (for example, `feat!: ...`) or with a
`BREAKING CHANGE:` footer.

## Opening a Pull Request

1. **The PR must always target `develop`.** PRs opened against `main` will have their base changed to `develop`
   by the maintainer.
2. **The PR title must follow Conventional Commits.** Since merges use *Squash and merge*, the title becomes the
   final commit message on `develop`.
3. Keep your branch up to date with the original repository's `develop` by rebasing:

   ```bash
   git fetch upstream
   git rebase upstream/develop
   git push --force-with-lease
   ```

   or with the **Update branch** button on the PR page.
4. Fill in the Pull Request template (summary, type of change, related Issue, how to test and checklist).
5. Prefer **small, focused** PRs: one topic per PR makes review easier and speeds up the merge.
6. Do not include secrets, tokens, credentials or personal data in code, commits or screenshots.

> GitHub Actions workflows on PRs from forks only run after the maintainer approves them.

## Review and approval

- The maintainer, @ROM-mm, reviews all PRs to `develop`.
- Merging requires **1 approval** from the maintainer and **all review conversations resolved**.
- If changes are requested (*Request changes*), update your branch and reply to or resolve the comments.
- A new push after approval **dismisses the previous approval**: the PR will need to be approved again.
- Merging is done exclusively with **Squash and merge**, and the source branch is deleted automatically after the
  merge.
- Force pushes and deletion of the `main` and `develop` branches are blocked.

## Releases

- Releases are made **only by the maintainer** @ROM-mm.
- The maintainer opens a release PR from `develop` to `main`, merged with a *merge commit*. The tag and the release
  are published from `main`, and then `main` is merged back into `develop`.
- Contributors **never** open PRs to `main`.
- [`CHANGELOG.md`](CHANGELOG.md) follows the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format, in
  English. Do not create or change version sections (for example, `## [0.10.0]`) unless the maintainer asks.

## Reporting vulnerabilities

**Do not open a public Issue** to report a security vulnerability.

Use GitHub's private reporting feature: in the repository's **Security** tab, click
**Report a vulnerability** and describe the problem, its impact and the steps to reproduce. The maintainer will
reply through that same private channel.

See [SECURITY.md](SECURITY.md) for the full security policy.

## License

Notisbook is distributed under the [Apache-2.0](LICENSE) license. By submitting a contribution, you agree that it
will be licensed under the same terms.
