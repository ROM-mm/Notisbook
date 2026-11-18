# Changelog

All notable changes to Notisbook are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2026-11-17

### Added

- **Release notes come from this changelog.** Each GitHub release now publishes this version's section of
  `CHANGELOG.md` as its body, instead of the auto-generated "Full Changelog" line. `scripts/release.sh` stops
  before building anything when the section is missing or empty, and `--dry-run` prints the notes so they can be
  reviewed before publishing.
- **Safer recovery when publishing fails.** If `gh release create` fails after the push, the notes are kept in
  `backend/dist/release-notes-v0.8.0.md` and the printed recovery command points to that file.

### Changed

- **Release titles are now the tag.** Releases are named after the tag, e.g. `v0.8.0` instead of `Notisbook 0.8.0`.

## [0.7.0] - 2026-11-17

### Changed

- **The README is now in English.** It was rewritten with a quick start based on the `install.sh` one-liner, a
  capability table, the other install options, requirements, documentation links and a contributing section.
- **Installation is documented only through `install.sh` and `uv tool`.** Every Homebrew reference was removed
  from the README; Homebrew is no longer a supported channel.
