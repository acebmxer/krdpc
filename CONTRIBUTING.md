# Contributing

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Run it with `.venv/bin/krdpc`. The tests draw the windows without a screen, so
they need no display.

## Before opening a pull request

The same checks CI runs:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest
```

## Conventions

**Pull requests target `dev`.** `main` only moves when a release is merged.

**Update the CHANGELOG in the same pass.** Every user-facing change gets an
entry under `## [Unreleased]`, in the right subsection, newest first.
Repository plumbing (CI config, issue templates, editor settings) gets no
entry.

**Documentation ships with the code**, not after it.

**Never commit real connection details.** Use made-up names, addresses and
usernames in tests, fixtures and screenshots.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`,
`docs:`, `test:`, `refactor:`, `chore:`.

## Branches and releases

Work happens on `dev` and reaches `main` through a pull request. The changelog
version section is part of the branch the pull request carries. The release is
made by the **Release** workflow (`.github/workflows/release.yml`); nobody tags by
hand.

The version is kept in one place, `src/krdpc/__init__.py`; `scripts/package_version.sh`
prints it and every package recipe takes it from there.

- **Beta.** On GitHub: Actions, **Release**, **Run workflow**, branch `dev`. It
  builds the `.rpm`, `.deb` and Arch package, installs each in a clean Fedora,
  Debian, Ubuntu and Arch container and checks krdpc starts, then publishes a
  pre-release `v<version>-beta.<n>` (n counts up) with the files and the changelog's
  `[Unreleased]` notes.
- **Stable.** Bump the version and move `[Unreleased]` into a dated section on `dev`,
  open the pull request into `main` and merge it. The workflow then makes a **draft**
  release `v<version>` with the files attached. Check it, paste the release notes in,
  and publish it; publishing creates the tag. It stops if the version is already
  tagged.

To build and test the packages yourself (needs podman or docker):

```bash
scripts/build_package.sh rpm out      # or deb, or arch; add a number for a beta
scripts/smoke_test.sh fedora out      # or debian, ubuntu, arch
```
