# Contributing

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install ruff
```

The app's own dependencies (PySide6) are added to this section with the first
code, in stage 2 of the roadmap.

## Before opening a pull request

The same checks CI runs:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
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
version section is part of the branch the pull request carries. The tag is
created on `main` after the merge.
