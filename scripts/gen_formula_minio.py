#!/usr/bin/env python3
"""Regenera, na fórmula Homebrew do Notisbook, as regiões do MinIO (notislake).

Três regiões delimitadas por marcadores são reescritas a cada execução:
  - `# BEGIN/END notislake resources`: resources por arquitetura (url do asset
    da release + sha256 do manifesto), no nível da classe;
  - `# BEGIN/END notislake install`: instalação dentro de `def install`;
  - `# BEGIN/END notislake test`: corpo do `test do` (chama `--check-notislake`).
O par resources/install e a região de test são migrados (bootstrap) de forma
independente a partir do formato original; marcadores incompletos fazem o
script falhar. A saída é idempotente.

Uso: gen_formula_minio.py --formula IN --manifest MANIFEST --repo OWNER/REPO
                          --tag vX.Y.Z --out OUT
Só stdlib; compatível com o python3 do sistema.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RES_BEGIN = "# BEGIN notislake resources"
RES_END = "# END notislake resources"
INS_BEGIN = "# BEGIN notislake install"
INS_END = "# END notislake install"
TEST_BEGIN = "# BEGIN notislake test"
TEST_END = "# END notislake test"
BUILD_MARKERS = (RES_BEGIN, RES_END, INS_BEGIN, INS_END)
TEST_MARKERS = (TEST_BEGIN, TEST_END)
MARKERS = BUILD_MARKERS + TEST_MARKERS

INSTALL_DEF = "  def install"
INSTALL_ORIGINAL = "    virtualenv_install_with_resources"
TEST_DEF = "  test do"
BLOCK_END = "  end"

# Chave do manifesto -> (bloco de sistema do Homebrew, predicado em Ruby)
ARCHS = {
    "darwin-arm64": ("on_arm", "Hardware::CPU.arm?"),
    "darwin-amd64": ("on_intel", "Hardware::CPU.intel?"),
}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TARBALL_RE = re.compile(r"^[A-Za-z0-9_.-]+\.tar\.gz$")
MINIO_TAG_RE = re.compile(r"^RELEASE\.[0-9A-Za-z.-]+$")


class FormulaError(Exception):
    """Entrada inválida ou fórmula em formato não reconhecido."""


def load_manifest(path: Path) -> tuple[str, dict[str, dict[str, str]]]:
    """Valida o manifesto e devolve (tag do MinIO, {arquitetura: {tarball, sha256}})."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        minio_tag = data["tag"]
        archs = data["archs"]
    except (OSError, ValueError, KeyError) as exc:
        raise FormulaError(f"manifesto ilegível ou incompleto: {path} ({exc})") from exc
    if not isinstance(minio_tag, str) or not MINIO_TAG_RE.match(minio_tag):
        raise FormulaError(f"tag do MinIO inválida no manifesto: {minio_tag!r}")
    if not isinstance(archs, dict):
        raise FormulaError("campo 'archs' do manifesto inválido")
    unknown = sorted(set(archs) - set(ARCHS))
    missing = sorted(set(ARCHS) - set(archs))
    if unknown or missing:
        raise FormulaError(f"arquiteturas do manifesto: inesperadas={unknown} ausentes={missing}")
    result: dict[str, dict[str, str]] = {}
    for arch, entry in archs.items():
        tarball, sha = entry.get("tarball"), entry.get("sha256")
        if not isinstance(tarball, str) or not TARBALL_RE.match(tarball):
            raise FormulaError(f"tarball inválido para {arch}: {tarball!r}")
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            raise FormulaError(f"sha256 inválido para {arch}: {sha!r}")
        result[arch] = {"tarball": tarball, "sha256": sha}
    return minio_tag, result


def resource_name(arch: str) -> str:
    return f"notislake-minio-{arch}"


def render_resources(repo: str, tag: str, minio_tag: str, archs: dict[str, dict[str, str]]) -> list[str]:
    """Linhas (já indentadas) da região de resources, marcadores incluídos."""
    lines = [f"  {RES_BEGIN}"]
    for arch in sorted(ARCHS):
        block, _ = ARCHS[arch]
        entry = archs[arch]
        url = f"https://github.com/{repo}/releases/download/{tag}/{entry['tarball']}"
        lines += [
            f"  {block} do",
            f'    resource "{resource_name(arch)}" do',
            f'      url "{url}"',
            f'      version "{minio_tag}"',
            f'      sha256 "{entry["sha256"]}"',
            "",
            "      livecheck do",
            '        skip "Versioned together with the Notisbook release"',
            "      end",
            "    end",
            "  end",
        ]
    lines.append(f"  {RES_END}")
    return lines


def render_install(minio_tag: str, archs: dict[str, dict[str, str]]) -> list[str]:
    """Linhas (já indentadas) da região de instalação, marcadores incluídos."""
    lines = [f"    {INS_BEGIN}"]
    for position, arch in enumerate(sorted(ARCHS)):
        _, predicate = ARCHS[arch]
        keyword = "if" if position == 0 else "elsif"
        lines += [
            f"    {keyword} {predicate}",
            f'      minio = resource("{resource_name(arch)}")',
            f'      minio_file = "{archs[arch]["tarball"]}"',
            f'      ohai "Installing MinIO {minio_tag} ({arch})"',
        ]
    lines += [
        "    else",
        '      odie "Unsupported architecture for the bundled MinIO"',
        "    end",
        "",
        "    virtualenv_install_with_resources without: minio.name",
        "",
        "    # O backend confere o sha pelo manifesto e exige o tarball com o nome original",
        '    (libexec/"notislake").mkpath',
        '    cp minio.cached_download, libexec/"notislake"/minio_file',
        "",
        '    # bin/notisbook é symlink para libexec/bin/notisbook; sem remover, o wrapper apontaria para si mesmo',
        '    rm bin/"notisbook"',
        '    (bin/"notisbook").write_env_script libexec/"bin/notisbook",',
        '                                       NOTISBOOK_MINIO_DIST: libexec/"notislake"',
        f"    {INS_END}",
    ]
    return lines


def render_test() -> list[str]:
    """Linhas (já indentadas) da região do `test do`, marcadores incluídos."""
    return [
        f"    {TEST_BEGIN}",
        '    assert_match version.to_s, shell_output("#{bin}/notisbook --version")',
        "",
        "    # Instala o MinIO num home temporário, confere o sha e roda minio --version, sem subir servidor",
        '    system bin/"notisbook", "--check-notislake"',
        f"    {TEST_END}",
    ]


def find_markers(lines: list[str]) -> dict[str, int]:
    """Índice de cada marcador presente; falha se repetido."""
    found: dict[str, int] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped in MARKERS:
            if stripped in found:
                raise FormulaError(f"marcador duplicado: {stripped}")
            found[stripped] = index
    return found


def replace_region(lines: list[str], begin: int, end: int, new: list[str]) -> list[str]:
    return lines[:begin] + new + lines[end + 1:]


def unique_index(lines: list[str], predicate, description: str) -> int:
    hits = [i for i, line in enumerate(lines) if predicate(line)]
    if len(hits) != 1:
        raise FormulaError(f"esperava exatamente uma ocorrência de {description}; achei {len(hits)}")
    return hits[0]


def apply_test_region(lines: list[str], markers: dict[str, int]) -> list[str]:
    """Substitui a região do `test do` ou, sem marcadores, troca o corpo original do bloco por ela."""
    present = [m for m in TEST_MARKERS if m in markers]
    if not present:
        start = unique_index(lines, lambda s: s.rstrip() == TEST_DEF, f"'{TEST_DEF.strip()}'")
        end = next((i for i in range(start + 1, len(lines)) if lines[i].rstrip() == BLOCK_END), None)
        if end is None:
            raise FormulaError("fim do bloco 'test do' não encontrado")
        return lines[: start + 1] + render_test() + lines[end:]
    if len(present) != len(TEST_MARKERS):
        raise FormulaError(f"marcadores de test incompletos; presentes: {present}")
    if markers[TEST_BEGIN] >= markers[TEST_END]:
        raise FormulaError("marcadores de test fora de ordem")
    return replace_region(lines, markers[TEST_BEGIN], markers[TEST_END], render_test())


def apply_build_regions(lines: list[str], markers: dict[str, int], repo: str, tag: str, minio_tag: str, archs: dict[str, dict[str, str]]) -> list[str]:
    """Regiões de resources e install: bootstrap sem marcadores, substituição com os quatro."""
    resources = render_resources(repo, tag, minio_tag, archs)
    install = render_install(minio_tag, archs)
    present = [m for m in BUILD_MARKERS if m in markers]
    if not present:
        # Bootstrap: o install original é exatamente uma chamada; a região de resources vai antes de def install
        install_def = unique_index(lines, lambda s: s.rstrip() == INSTALL_DEF, f"'{INSTALL_DEF.strip()}'")
        original = unique_index(lines, lambda s: s.rstrip() == INSTALL_ORIGINAL, f"'{INSTALL_ORIGINAL.strip()}'")
        if original < install_def:
            raise FormulaError("virtualenv_install_with_resources fora de def install")
        lines = lines[:original] + install + lines[original + 1:]
        return lines[:install_def] + resources + [""] + lines[install_def:]
    if len(present) != len(BUILD_MARKERS):
        raise FormulaError(f"marcadores incompletos; presentes: {present}")
    if not (markers[RES_BEGIN] < markers[RES_END] < markers[INS_BEGIN] < markers[INS_END]):
        raise FormulaError("marcadores fora de ordem")
    # Região de baixo primeiro, para não deslocar os índices da de cima
    lines = replace_region(lines, markers[INS_BEGIN], markers[INS_END], install)
    return replace_region(lines, markers[RES_BEGIN], markers[RES_END], resources)


def generate(formula: str, repo: str, tag: str, minio_tag: str, archs: dict[str, dict[str, str]]) -> str:
    lines = formula.split("\n")
    markers = find_markers(lines)
    build_end = markers.get(INS_END, -1)
    if TEST_BEGIN in markers and build_end > markers[TEST_BEGIN]:
        raise FormulaError("marcadores fora de ordem")
    # `test do` fica depois de `def install`: tratá-lo primeiro não desloca os índices da região de build
    lines = apply_test_region(lines, markers)
    lines = apply_build_regions(lines, find_markers(lines), repo, tag, minio_tag, archs)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--formula", required=True, type=Path, help="fórmula de entrada")
    parser.add_argument("--manifest", required=True, type=Path, help="minio_manifest.json")
    parser.add_argument("--repo", required=True, help="OWNER/REPO que hospeda a release")
    parser.add_argument("--tag", required=True, help="tag da release (vX.Y.Z)")
    parser.add_argument("--out", required=True, type=Path, help="fórmula de saída")
    args = parser.parse_args(argv)

    try:
        if not TAG_RE.match(args.tag):
            raise FormulaError(f"tag inválida: {args.tag!r} (use vX.Y.Z)")
        if not REPO_RE.match(args.repo):
            raise FormulaError(f"repositório inválido: {args.repo!r}")
        minio_tag, archs = load_manifest(args.manifest)
        try:
            formula = args.formula.read_text(encoding="utf-8")
        except OSError as exc:
            raise FormulaError(f"fórmula ilegível: {args.formula} ({exc})") from exc
        result = generate(formula, args.repo, args.tag, minio_tag, archs)
        args.out.write_text(result, encoding="utf-8")
    except FormulaError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
