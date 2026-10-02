#!/bin/bash
# SessionStart hook for Claude Code on the web: installs bitig + dev tooling
# so ruff, mypy and pytest work in cloud sessions. Mirrors the CI lint/test jobs.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

# Editable install of the package plus dev extras (pytest, ruff, mypy, cluster).
uv pip install --system -e ".[dev]"

# Small English spaCy model used by the test suite; skip if already present.
if ! python3 -c "import en_core_web_sm" >/dev/null 2>&1; then
  python3 -m spacy download en_core_web_sm
fi

# textstat's syllable counting needs NLTK's cmudict corpus. The cloud container
# routes HTTPS through a proxy, which NLTK refuses unless explicitly allowed.
if ! python3 -c "import nltk; nltk.data.find('corpora/cmudict')" >/dev/null 2>&1; then
  NLTK_ALLOW_PROXIED_URLOPEN=1 python3 -c "import nltk, sys; sys.exit(0 if nltk.download('cmudict', quiet=True) else 1)"
fi

# Put the interpreter's bin dir first on PATH so pytest/mypy/ruff resolve to the
# copies installed above, not standalone tool installs (e.g. ~/.local/bin) that
# can't import the project's dependencies.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  bin_dir="$(python3 -c 'import sys, sysconfig; print(sysconfig.get_path("scripts"))')"
  echo "export PATH=\"${bin_dir}:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
