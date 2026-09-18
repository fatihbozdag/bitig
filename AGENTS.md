# Repository Guidelines

## Project Structure & Module Organization

Bitig is a Python 3.11+ computational stylometry package using a `src/` layout. Core code lives in `src/bitig/`: `corpus/`, `preprocess/`, and `features/` prepare texts; `methods/` and `forensic/` implement analyses; `cli/`, `gui/`, `viz/`, and `report/` expose results. Language resources and Jinja2 templates live alongside their modules. Tests mirror these areas under `tests/`, with shared fixtures in `tests/conftest.py` and `tests/fixtures/`. Runnable studies live in `examples/`; documentation lives in `docs/site/`, including Turkish `.tr.md` translations.

## Build, Test, and Development Commands

Create an environment with `uv venv`, activate it with `source .venv/bin/activate`, then install development dependencies using `uv pip install -e ".[dev]"`.

- `python -m spacy download en_core_web_sm`: install the English model used by CI.
- `bitig --help`: explore the CLI; `bitig run study.yaml --name demo` executes a configured study.
- `pytest -n auto --cov=bitig --cov-report=term-missing -m "not slow"`: run the main CI test suite with coverage.
- `ruff check src tests` and `ruff format --check src tests`: check lint and formatting; use `ruff format src tests` to format.
- `mypy src`: check types.
- `uv build`: build wheel and source distributions.
- `mkdocs build --strict`: validate documentation after installing `.[docs]`.

## Coding Style & Naming Conventions

Use four-space indentation, double quotes, and Ruff's 100-character formatting target. Use `snake_case` for modules/functions, `PascalCase` for classes, and `UPPER_CASE` for constants. Type function signatures in `bitig` modules; mypy disallows untyped definitions. Keep optional heavyweight dependencies lazily imported. Run `pre-commit run --all-files` before submitting.

## Testing Guidelines

Use pytest, name files `test_*.py`, and place tests beside the corresponding subsystem's tests. Reuse shared corpus fixtures and add regression tests for behavior changes. Registered markers are `slow`, `spacy`, and `integration`; install relevant extras and models before exercising optional paths. Branch coverage is configured, but no minimum percentage is enforced.

## Commit & Pull Request Guidelines

Follow existing scoped subjects such as `fix(turkish): ...` and `feat(forensic): ...`. Keep commits focused. PRs should explain the problem, behavior changes, and validation commands/results; link relevant issues and include screenshots for GUI changes. Update affected documentation. Keep local corpora, generated runs, caches, secrets, and build outputs out of commits.
