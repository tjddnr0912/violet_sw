# Little Lion Phase 1a — Backend Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the headless backend that takes a text/voice query, routes it to the right model, retrieves vault context, calls the LLM, and writes an atom note + cross-links back into the Obsidian vault. Verifiable by `curl /chat` producing a new `.md` file with `[[wiki-links]]` to existing notes.

**Architecture:** FastAPI HTTP+WebSocket service on port 8765. Ollama provides local LLMs and embeddings. LiteLLM unifies Claude/Gemini/Ollama. LanceDB stores embeddings. `policy` gate sits in front of every cloud call. `vault_writer` produces atomic `.md` writes into the iCloud-synced Obsidian vault.

**Tech Stack:**
- Python 3.11+
- FastAPI 0.110+, uvicorn, websockets
- pydantic-settings 2.x
- httpx (Ollama HTTP)
- litellm 1.x (Claude / Gemini / Ollama unified)
- lancedb 0.6+, pyarrow
- mlx-whisper (Apple Silicon STT)
- watchdog (fs events)
- python-frontmatter, pyyaml
- rank-bm25 (hybrid search)
- pytest 8+, pytest-asyncio, pytest-httpx, freezegun

**Reference design doc:** `015_little_lion/docs/specs/2026-05-18-little-lion-personal-assistant-design.md`

**Vault location (M1 Max default):**
`/Users/seongwookjang/Library/Mobile Documents/iCloud~md~obsidian/Documents/violet`
Configurable via env var `LITTLE_LION_VAULT_PATH`.

**Working directory:** All commands assume CWD `/Users/seongwookjang/project/git/violet_sw/015_little_lion/` unless stated otherwise.

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `backend/__init__.py`
- Create: `backend/main.py`  (placeholder entry)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `README.md`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "little-lion"
version = "0.0.1"
description = "Personal AI assistant — vault-grounded, voice-capable"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.5",
    "pydantic-settings>=2.2",
    "httpx>=0.27",
    "litellm>=1.30",
    "lancedb>=0.6",
    "pyarrow>=15",
    "watchdog>=4.0",
    "python-frontmatter>=1.1",
    "pyyaml>=6.0",
    "rank-bm25>=0.2.2",
    "mlx-whisper>=0.4",
    "anthropic>=0.25",
    "google-generativeai>=0.5",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-httpx>=0.30",
    "freezegun>=1.4",
    "ruff>=0.3",
    "mypy>=1.9",
]

[tool.hatch.build.targets.wheel]
packages = ["backend"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Vault (iCloud Obsidian)
LITTLE_LION_VAULT_PATH=/Users/seongwookjang/Library/Mobile Documents/iCloud~md~obsidian/Documents/violet
LITTLE_LION_ASSISTANT_SUBDIR=assistant

# Ollama
OLLAMA_HOST=http://127.0.0.1:11434

# Cloud LLM
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=

# Service
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8765
BACKEND_AUTH_TOKEN=change-me-to-a-random-32-byte-hex

# Modes
OFFLINE_MODE=false
LOG_LEVEL=INFO

# RAG
RAG_DB_PATH=./data/lancedb
RAG_TOP_K=8
RAG_CROSS_LINK_THRESHOLD=0.75
RAG_CROSS_LINK_K=5

# STT
WHISPER_MODEL=mlx-community/whisper-large-v3-mlx
```

- [ ] **Step 3: Create `.gitignore`**

```gitignore
.env
.env.local
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.mypy_cache/
data/
.venv/
node_modules/
frontend/dist/
.DS_Store
```

- [ ] **Step 4: Create `backend/__init__.py`** (empty file)

```python
```

- [ ] **Step 5: Create placeholder `backend/main.py`**

```python
"""Entry point — wired up in Task 19."""

def main() -> None:
    raise SystemExit("Backend not yet implemented — see docs/specs/2026-05-18-little-lion-phase1a-backend-plan.md")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Create `tests/__init__.py`** (empty)

```python
```

- [ ] **Step 7: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """A throwaway vault directory with the `assistant/` substructure pre-created.

    `_traces/` and `_proposals/` are operational subdirs (deep-dive §4/§5), skipped
    by indexer + watcher. `_review-queue.md` is created lazily by reflection jobs.
    """
    vault = tmp_path / "vault"
    (vault / "assistant" / "atoms").mkdir(parents=True)
    (vault / "assistant" / "daily").mkdir(parents=True)
    (vault / "assistant" / "sessions").mkdir(parents=True)
    (vault / "assistant" / "MOC").mkdir(parents=True)
    (vault / "assistant" / "_traces").mkdir(parents=True)
    (vault / "assistant" / "_proposals").mkdir(parents=True)
    return vault


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_vault: Path) -> None:
    """Block real env vars and pin paths into tmp_vault for every test."""
    for key in list(os.environ):
        if key.startswith("LITTLE_LION_") or key in {"OLLAMA_HOST", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OFFLINE_MODE"}:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LITTLE_LION_VAULT_PATH", str(tmp_vault))
    monkeypatch.setenv("LITTLE_LION_ASSISTANT_SUBDIR", "assistant")
    monkeypatch.setenv("BACKEND_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("OFFLINE_MODE", "true")
    monkeypatch.setenv("RAG_DB_PATH", str(tmp_vault.parent / "lancedb"))
```

- [ ] **Step 8: Create `README.md`**

```markdown
# Little Lion — Personal AI Assistant (Backend Phase 1a)

See `docs/specs/2026-05-18-little-lion-personal-assistant-design.md` for the full design.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in keys
pytest -q
uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload
```
```

- [ ] **Step 9: Verify install works**

Run: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
Expected: install completes; `pytest -q` runs zero tests with `no tests ran` (still passes exit 0 since `tests/` is empty save for `__init__.py`).

- [ ] **Step 10: Commit**

```bash
git add 015_little_lion/pyproject.toml 015_little_lion/.env.example 015_little_lion/.gitignore \
        015_little_lion/backend/__init__.py 015_little_lion/backend/main.py \
        015_little_lion/tests/__init__.py 015_little_lion/tests/conftest.py 015_little_lion/README.md
git commit -m "Add 015_little_lion scaffold: pyproject + tests fixtures"
```

---

## Task 2: Configuration loader

**Files:**
- Create: `backend/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test `tests/test_config.py`**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from backend.config import Settings, get_settings


def test_settings_pulls_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LITTLE_LION_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("BACKEND_AUTH_TOKEN", "abc")
    monkeypatch.setenv("OFFLINE_MODE", "true")

    s = Settings()  # type: ignore[call-arg]

    assert s.vault_path == tmp_path
    assert s.assistant_subdir == "assistant"
    assert s.auth_token == "abc"
    assert s.offline_mode is True
    assert s.rag_cross_link_threshold == 0.75
    assert s.rag_cross_link_k == 5


def test_settings_requires_vault_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITTLE_LION_VAULT_PATH", raising=False)
    with pytest.raises(ValueError):
        Settings()  # type: ignore[call-arg]


def test_get_settings_is_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITTLE_LION_VAULT_PATH", str(tmp_path))
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2  # cached singleton
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: ImportError — `backend.config` does not exist.

- [ ] **Step 3: Implement `backend/config.py`**

```python
"""Application configuration — env-driven, validated by pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Vault
    vault_path: Path = Field(..., alias="LITTLE_LION_VAULT_PATH")
    assistant_subdir: str = Field(default="assistant", alias="LITTLE_LION_ASSISTANT_SUBDIR")

    # Ollama
    ollama_host: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_HOST")

    # Cloud
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")

    # Service
    backend_host: str = Field(default="127.0.0.1", alias="BACKEND_HOST")
    backend_port: int = Field(default=8765, alias="BACKEND_PORT")
    auth_token: str = Field(..., alias="BACKEND_AUTH_TOKEN")

    # Modes
    offline_mode: bool = Field(default=False, alias="OFFLINE_MODE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # RAG
    rag_db_path: Path = Field(default=Path("./data/lancedb"), alias="RAG_DB_PATH")
    rag_top_k: int = Field(default=8, alias="RAG_TOP_K")
    rag_cross_link_threshold: float = Field(default=0.75, alias="RAG_CROSS_LINK_THRESHOLD")
    rag_cross_link_k: int = Field(default=5, alias="RAG_CROSS_LINK_K")

    # STT
    whisper_model: str = Field(default="mlx-community/whisper-large-v3-mlx", alias="WHISPER_MODEL")

    @field_validator("vault_path")
    @classmethod
    def _vault_must_exist(cls, v: Path) -> Path:
        if not v.exists():
            raise ValueError(f"vault_path does not exist: {v}")
        return v

    @property
    def assistant_root(self) -> Path:
        return self.vault_path / self.assistant_subdir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()
```

- [ ] **Step 4: Update `tests/conftest.py` to clear the cache between tests**

Modify `tests/conftest.py` — add to the `_isolate_env` fixture at the end:

```python
    from backend.config import reset_settings_cache
    reset_settings_cache()
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/config.py tests/test_config.py tests/conftest.py
git commit -m "Add config loader (Settings + get_settings singleton)"
```

---

## Task 3: Filesystem utils (slugify + atomic write)

**Files:**
- Create: `backend/vault/__init__.py`
- Create: `backend/vault/fs_utils.py`
- Create: `tests/vault/__init__.py`
- Create: `tests/vault/test_fs_utils.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/vault/test_fs_utils.py
from __future__ import annotations

from pathlib import Path

import pytest

from backend.vault.fs_utils import atomic_write_text, slugify


@pytest.mark.parametrize(
    "title,expected",
    [
        ("LiteLLM Router Pattern", "litellm-router-pattern"),
        ("한국어 STT 평가", "한국어-stt-평가"),
        ("  spaces  and  --dashes--", "spaces-and-dashes"),
        ("Foo: Bar / Baz", "foo-bar-baz"),
        ("", "untitled"),
    ],
)
def test_slugify(title: str, expected: str) -> None:
    assert slugify(title) == expected


def test_atomic_write_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_no_partial_on_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the rename step would fail, the target must NOT exist (no half-written file)."""
    target = tmp_path / "b.md"

    def boom(*_a: object, **_kw: object) -> None:
        raise OSError("simulated")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(target, "x")
    assert not target.exists()


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "c.md"
    target.write_text("old", encoding="utf-8")
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/vault/test_fs_utils.py -v`
Expected: ImportError on `backend.vault.fs_utils`.

- [ ] **Step 3: Implement `backend/vault/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/vault/fs_utils.py`**

```python
"""Filesystem helpers — slugify + atomic write."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_SLUG_BAD = re.compile(r"[^\w\-]+", re.UNICODE)
_SLUG_DASH_RUN = re.compile(r"-+")


def slugify(title: str) -> str:
    """Convert a title to a filesystem-friendly slug.

    Keeps Unicode letters/digits (so 한글 works), replaces everything else with `-`,
    collapses runs of dashes, strips leading/trailing dashes, lowercases ASCII.
    """
    s = title.strip().lower()
    s = _SLUG_BAD.sub("-", s)
    s = _SLUG_DASH_RUN.sub("-", s).strip("-")
    return s or "untitled"


def atomic_write_text(target: Path, content: str, encoding: str = "utf-8") -> None:
    """Write `content` to `target` atomically: tmp file → fsync → os.replace.

    If anything fails before the replace step, `target` is left untouched.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
```

- [ ] **Step 5: Create `tests/vault/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/vault/test_fs_utils.py -v`
Expected: 7 passed (4 parametrized slugify + 3 atomic_write).

- [ ] **Step 7: Commit**

```bash
git add backend/vault/__init__.py backend/vault/fs_utils.py tests/vault/__init__.py tests/vault/test_fs_utils.py
git commit -m "Add vault fs_utils: slugify + atomic_write_text"
```

---

## Task 4: Frontmatter parser/serializer

**Files:**
- Create: `backend/vault/frontmatter.py`
- Create: `tests/vault/test_frontmatter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/vault/test_frontmatter.py
from __future__ import annotations

from datetime import datetime

import pytest

from backend.vault.frontmatter import dump, load, merge_into


SAMPLE = """---
type: atom
created: 2026-05-18T14:23:00
tags:
- ai/router
- infra/litellm
local-only: false
---

# Body

Hello.
"""


def test_load_parses_metadata_and_body() -> None:
    meta, body = load(SAMPLE)
    assert meta["type"] == "atom"
    assert meta["tags"] == ["ai/router", "infra/litellm"]
    assert meta["local-only"] is False
    assert body.startswith("# Body")


def test_load_handles_no_frontmatter() -> None:
    meta, body = load("# Just a note\n\ntext\n")
    assert meta == {}
    assert body == "# Just a note\n\ntext\n"


def test_dump_roundtrip() -> None:
    meta, body = load(SAMPLE)
    out = dump(meta, body)
    meta2, body2 = load(out)
    assert meta2 == meta
    assert body2.strip() == body.strip()


def test_merge_into_updates_existing_keys() -> None:
    text = "---\nfoo: 1\nbar: 2\n---\n\nbody"
    updated = merge_into(text, {"foo": 99, "baz": "new"})
    meta, _ = load(updated)
    assert meta == {"foo": 99, "bar": 2, "baz": "new"}


def test_merge_into_adds_frontmatter_when_missing() -> None:
    updated = merge_into("plain body\n", {"foo": "bar"})
    meta, body = load(updated)
    assert meta == {"foo": "bar"}
    assert body.strip() == "plain body"


def test_dump_serializes_datetime() -> None:
    out = dump({"created": datetime(2026, 5, 18, 14, 23)}, "x")
    meta, _ = load(out)
    assert isinstance(meta["created"], datetime)
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/vault/test_frontmatter.py -v`
Expected: ImportError on `backend.vault.frontmatter`.

- [ ] **Step 3: Implement `backend/vault/frontmatter.py`**

```python
"""Markdown frontmatter (YAML) parser/serializer — thin wrapper for stability."""
from __future__ import annotations

from typing import Any

import frontmatter


def load(text: str) -> tuple[dict[str, Any], str]:
    """Parse a markdown string with optional YAML frontmatter.

    Returns (metadata_dict, body_text). Empty metadata if no frontmatter.
    """
    post = frontmatter.loads(text)
    return dict(post.metadata), post.content


def dump(metadata: dict[str, Any], body: str) -> str:
    """Serialize metadata + body back to a markdown string with YAML frontmatter."""
    post = frontmatter.Post(body, **metadata)
    return frontmatter.dumps(post) + "\n"


def merge_into(text: str, updates: dict[str, Any]) -> str:
    """Merge `updates` into the frontmatter of `text` (preserves other keys + body)."""
    meta, body = load(text)
    meta.update(updates)
    return dump(meta, body)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/vault/test_frontmatter.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/vault/frontmatter.py tests/vault/test_frontmatter.py
git commit -m "Add vault frontmatter load/dump/merge"
```

---

## Task 5: Vault Writer — atom creation

**Files:**
- Create: `backend/vault/writer.py`
- Create: `tests/vault/test_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/vault/test_writer.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from freezegun import freeze_time

from backend.vault.writer import AtomWriteResult, VaultWriter


@pytest.fixture
def writer(tmp_vault: Path) -> VaultWriter:
    return VaultWriter(vault_path=tmp_vault, assistant_subdir="assistant")


@freeze_time("2026-05-18 14:23:00")
def test_write_atom_creates_file_with_frontmatter(writer: VaultWriter, tmp_vault: Path) -> None:
    result = writer.write_atom(
        title="LiteLLM Router Pattern",
        body="작업 유형별로 Claude/Gemini/Ollama 통합 호출.",
        tags=["ai/router", "infra/litellm"],
        source_session="sessions/2026-05-18T14-23.md",
    )
    assert isinstance(result, AtomWriteResult)
    expected = tmp_vault / "assistant" / "atoms" / "litellm-router-pattern.md"
    assert result.path == expected
    text = expected.read_text(encoding="utf-8")
    assert "type: atom" in text
    assert "state: published" in text          # see deep-dive §1 atom lifecycle
    assert "linked-count: 0" in text
    assert "ai/router" in text
    assert "# LiteLLM Router Pattern" in text
    assert "## Related" in text  # empty section is still present


@freeze_time("2026-05-18 14:23:00")
def test_write_atom_includes_lifecycle_fields(writer: VaultWriter) -> None:
    """All atoms start with state=published, linked-count=0, null reflection fields (§1)."""
    r = writer.write_atom(title="L", body="b")
    text = r.path.read_text(encoding="utf-8")
    assert "state: published" in text
    assert "linked-count: 0" in text
    # last-reflected and quality-score start null; YAML renders as empty
    assert "last-reflected:" in text
    assert "quality-score:" in text


def test_write_atom_is_idempotent_for_same_slug(writer: VaultWriter) -> None:
    r1 = writer.write_atom(title="Foo", body="first")
    r2 = writer.write_atom(title="Foo", body="second")
    assert r1.path == r2.path
    assert r2.created is False  # second call updates, doesn't create
    assert r1.path.read_text(encoding="utf-8").count("first") == 0  # overwritten
    assert "second" in r1.path.read_text(encoding="utf-8")


def test_write_atom_records_conflict_when_user_edited(writer: VaultWriter, tmp_vault: Path) -> None:
    r1 = writer.write_atom(title="Bar", body="A")
    # simulate user edit removing assistant-touched-at marker
    text = r1.path.read_text(encoding="utf-8").replace("assistant-touched-at", "user-touched")
    r1.path.write_text(text, encoding="utf-8")
    r2 = writer.write_atom(title="Bar", body="B")
    assert r2.path != r1.path
    assert r2.path.name.startswith("bar-conflict-")


def test_default_local_only_false(writer: VaultWriter) -> None:
    r = writer.write_atom(title="X", body="b")
    assert "local-only: false" in r.path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/vault/test_writer.py -v`
Expected: ImportError on `backend.vault.writer`.

- [ ] **Step 3: Implement `backend/vault/writer.py`**

```python
"""Vault writer — produces atom notes with frontmatter, atomically."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backend.vault.fs_utils import atomic_write_text, slugify
from backend.vault.frontmatter import dump, load


@dataclass(frozen=True)
class AtomWriteResult:
    path: Path
    slug: str
    created: bool   # True if newly created, False if updated existing


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().replace(microsecond=0).isoformat()


def _render_atom(title: str, body: str, meta: dict) -> str:
    body_section = f"# {title}\n\n{body.strip()}\n\n## Related\n"
    return dump(meta, body_section)


class VaultWriter:
    """Writes atom notes to <vault>/<assistant_subdir>/atoms/<slug>.md."""

    def __init__(self, vault_path: Path, assistant_subdir: str = "assistant") -> None:
        self.vault_path = Path(vault_path)
        self.subdir = assistant_subdir

    @property
    def atoms_dir(self) -> Path:
        return self.vault_path / self.subdir / "atoms"

    def write_atom(
        self,
        *,
        title: str,
        body: str,
        tags: list[str] | None = None,
        local_only: bool = False,
        source_session: str | None = None,
    ) -> AtomWriteResult:
        slug = slugify(title)
        target = self.atoms_dir / f"{slug}.md"
        meta = {
            "type": "atom",
            "state": "published",          # §1 atom lifecycle initial state
            "created": _now_iso(),
            "tags": tags or [],
            "local-only": local_only,
            "source": source_session or "",
            "assistant-touched-at": _now_iso(),
            "linked-count": 0,             # incremented by linker (Task 6)
            "last-reflected": None,        # populated by reflection job (Phase 2)
            "quality-score": None,         # populated by reflection job (Phase 2)
        }

        if target.exists():
            existing_text = target.read_text(encoding="utf-8")
            existing_meta, _ = load(existing_text)
            if existing_meta.get("assistant-touched-at") is None:
                # The user has stripped our marker → treat as conflict
                conflict = self._next_conflict_path(slug)
                atomic_write_text(conflict, _render_atom(title, body, meta))
                return AtomWriteResult(path=conflict, slug=conflict.stem, created=True)
            # Preserve the original `created` timestamp
            if existing_meta.get("created"):
                meta["created"] = existing_meta["created"]
            atomic_write_text(target, _render_atom(title, body, meta))
            return AtomWriteResult(path=target, slug=slug, created=False)

        atomic_write_text(target, _render_atom(title, body, meta))
        return AtomWriteResult(path=target, slug=slug, created=True)

    def _next_conflict_path(self, slug: str) -> Path:
        n = 1
        while True:
            candidate = self.atoms_dir / f"{slug}-conflict-{n}.md"
            if not candidate.exists():
                return candidate
            n += 1
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/vault/test_writer.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/vault/writer.py tests/vault/test_writer.py
git commit -m "Add VaultWriter.write_atom with conflict-safe atomic write"
```

---

## Task 6: Cross-link insertion (linker)

**Files:**
- Create: `backend/vault/linker.py`
- Create: `tests/vault/test_linker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/vault/test_linker.py
from __future__ import annotations

from pathlib import Path

import pytest

from backend.vault.linker import add_related_link, link_bidirectional


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_add_related_link_appends_under_section(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    _write(target, "---\ntype: atom\n---\n\n# A\n\n## Related\n")
    add_related_link(target, "b")
    text = target.read_text(encoding="utf-8")
    assert "- [[b]]" in text


def test_add_related_link_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    _write(target, "---\ntype: atom\n---\n\n# A\n\n## Related\n- [[b]]\n")
    add_related_link(target, "b")
    text = target.read_text(encoding="utf-8")
    assert text.count("- [[b]]") == 1


def test_add_related_link_creates_section_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    _write(target, "---\ntype: atom\n---\n\n# A\n\nbody only\n")
    add_related_link(target, "b")
    text = target.read_text(encoding="utf-8")
    assert "## Related" in text
    assert "- [[b]]" in text


def test_link_bidirectional(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    _write(a, "---\n---\n# A\n\n## Related\n")
    _write(b, "---\n---\n# B\n\n## Related\n")
    link_bidirectional(a, b)
    assert "- [[b]]" in a.read_text(encoding="utf-8")
    assert "- [[a]]" in b.read_text(encoding="utf-8")


def test_link_bidirectional_promotes_state(tmp_path: Path) -> None:
    """Per deep-dive §1: published atoms transition to linked when first edge added."""
    from backend.vault.frontmatter import load
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    _write(a, "---\ntype: atom\nstate: published\nlinked-count: 0\n---\n# A\n\n## Related\n")
    _write(b, "---\ntype: atom\nstate: published\nlinked-count: 0\n---\n# B\n\n## Related\n")
    link_bidirectional(a, b)
    meta_a, _ = load(a.read_text(encoding="utf-8"))
    meta_b, _ = load(b.read_text(encoding="utf-8"))
    assert meta_a["state"] == "linked"
    assert meta_b["state"] == "linked"
    assert meta_a["linked-count"] == 1
    assert meta_b["linked-count"] == 1


def test_link_bidirectional_increments_existing_count(tmp_path: Path) -> None:
    from backend.vault.frontmatter import load
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    _write(a, "---\ntype: atom\nstate: linked\nlinked-count: 3\n---\n# A\n\n## Related\n")
    _write(b, "---\ntype: atom\nstate: published\nlinked-count: 0\n---\n# B\n\n## Related\n")
    link_bidirectional(a, b)
    meta_a, _ = load(a.read_text(encoding="utf-8"))
    assert meta_a["linked-count"] == 4


def test_link_bidirectional_skips_non_atom(tmp_path: Path) -> None:
    """Linker should not promote files that aren't atoms (e.g., MOC, daily)."""
    from backend.vault.frontmatter import load
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    _write(a, "---\ntype: moc\n---\n# A\n\n## Related\n")
    _write(b, "---\ntype: atom\nstate: published\nlinked-count: 0\n---\n# B\n\n## Related\n")
    link_bidirectional(a, b)
    meta_a, _ = load(a.read_text(encoding="utf-8"))
    meta_b, _ = load(b.read_text(encoding="utf-8"))
    assert meta_a.get("state") is None      # untouched
    assert meta_b["state"] == "linked"      # promoted


def test_add_related_link_sorted(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    _write(target, "---\n---\n# A\n\n## Related\n- [[c]]\n")
    add_related_link(target, "b")
    text = target.read_text(encoding="utf-8")
    # alphabetical order ensures deterministic output
    b_idx = text.index("- [[b]]")
    c_idx = text.index("- [[c]]")
    assert b_idx < c_idx
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/vault/test_linker.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/vault/linker.py`**

```python
"""Insert [[wiki-links]] under the ## Related section of a markdown atom note."""
from __future__ import annotations

import re
from pathlib import Path

from backend.vault.fs_utils import atomic_write_text

_RELATED_HEADER = "## Related"
_WIKI_LINE = re.compile(r"^- \[\[(?P<name>[^\]]+)\]\]\s*$")


def _slug_of(path_or_str: str | Path) -> str:
    if isinstance(path_or_str, Path):
        return path_or_str.stem
    return path_or_str


def add_related_link(target: Path, related_slug: str | Path) -> None:
    """Insert `- [[related_slug]]` under `## Related` of `target`. Idempotent + sorted."""
    slug = _slug_of(related_slug)
    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    if _RELATED_HEADER not in text:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(_RELATED_HEADER)
        lines.append(f"- [[{slug}]]")
        atomic_write_text(target, "\n".join(lines) + "\n")
        return

    out: list[str] = []
    in_section = False
    section_links: list[str] = []
    after_section: list[str] = []
    section_done = False

    for line in lines:
        if not section_done and line.strip() == _RELATED_HEADER:
            in_section = True
            out.append(line)
            continue
        if in_section:
            m = _WIKI_LINE.match(line)
            if m:
                section_links.append(m.group("name"))
                continue
            if line.strip() == "":
                # blank line within section is OK, treat as continuation marker
                section_links.append("")  # sentinel for blank
                continue
            # any non-link non-blank line closes the section
            in_section = False
            section_done = True
            # emit links sorted (drop sentinels), then this line
            for name in _emit_sorted(section_links, slug):
                out.append(f"- [[{name}]]")
            out.append(line)
            continue
        out.append(line)

    if in_section:
        # file ended while still in section
        for name in _emit_sorted(section_links, slug):
            out.append(f"- [[{name}]]")

    atomic_write_text(target, "\n".join(out) + "\n")


def _emit_sorted(existing: list[str], new: str) -> list[str]:
    names = sorted({n for n in existing if n} | {new})
    return names


def link_bidirectional(a: Path, b: Path) -> None:
    add_related_link(a, b.stem)
    add_related_link(b, a.stem)
    _promote_to_linked(a)
    _promote_to_linked(b)


def _promote_to_linked(target: Path) -> None:
    """Transition atom state published → linked (deep-dive §1) and bump linked-count.

    No-op for non-atom files (type != 'atom'). Idempotent: already-linked atoms
    only have their counter incremented.
    """
    from backend.vault.frontmatter import dump, load

    text = target.read_text(encoding="utf-8")
    meta, body = load(text)
    if meta.get("type") != "atom":
        return
    meta["state"] = "linked"
    meta["linked-count"] = int(meta.get("linked-count") or 0) + 1
    atomic_write_text(target, dump(meta, body))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/vault/test_linker.py -v`
Expected: 8 passed (5 link insertion + 3 state promotion).

- [ ] **Step 5: Commit**

```bash
git add backend/vault/linker.py tests/vault/test_linker.py
git commit -m "Add vault linker.add_related_link + link_bidirectional"
```

---

## Task 7: Ollama HTTP client (embed + generate)

**Files:**
- Create: `backend/llm/__init__.py`
- Create: `backend/llm/ollama.py`
- Create: `tests/llm/__init__.py`
- Create: `tests/llm/test_ollama.py`

- [ ] **Step 1: Write failing tests (HTTP mocked with pytest-httpx)**

```python
# tests/llm/test_ollama.py
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from pytest_httpx import HTTPXMock

from backend.llm.ollama import OllamaClient


@pytest.mark.asyncio
async def test_embed_returns_vector(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="http://127.0.0.1:11434/api/embeddings",
        json={"embedding": [0.1, 0.2, 0.3]},
    )
    client = OllamaClient(host="http://127.0.0.1:11434")
    vec = await client.embed("nomic-embed-text", "hello")
    assert vec == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_generate_stream_yields_tokens(httpx_mock: HTTPXMock) -> None:
    # Ollama streams newline-delimited JSON
    body = (
        json.dumps({"response": "hel", "done": False}) + "\n"
        + json.dumps({"response": "lo", "done": False}) + "\n"
        + json.dumps({"response": "", "done": True}) + "\n"
    )
    httpx_mock.add_response(
        url="http://127.0.0.1:11434/api/generate",
        content=body.encode(),
    )
    client = OllamaClient(host="http://127.0.0.1:11434")
    chunks: list[str] = []
    async for tok in client.generate("qwen2.5:14b", prompt="hi", system="be terse"):
        chunks.append(tok)
    assert "".join(chunks) == "hello"


@pytest.mark.asyncio
async def test_embed_raises_on_500(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="http://127.0.0.1:11434/api/embeddings", status_code=500)
    client = OllamaClient(host="http://127.0.0.1:11434")
    with pytest.raises(RuntimeError):
        await client.embed("nomic-embed-text", "x")
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/llm/test_ollama.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/llm/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/llm/ollama.py`**

```python
"""Async Ollama HTTP client — embed + streaming generate, no SDK."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class OllamaClient:
    """Thin async client for Ollama's REST API."""

    def __init__(self, host: str, timeout: float = 60.0) -> None:
        self.host = host.rstrip("/")
        self._timeout = timeout

    async def embed(self, model: str, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=self._timeout) as cx:
            r = await cx.post(
                f"{self.host}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            if r.status_code != 200:
                raise RuntimeError(f"Ollama embed failed: {r.status_code} {r.text}")
            data: dict[str, Any] = r.json()
            return list(data["embedding"])

    async def generate(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if options:
            payload["options"] = options

        async with httpx.AsyncClient(timeout=self._timeout) as cx:
            async with cx.stream("POST", f"{self.host}/api/generate", json=payload) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    raise RuntimeError(f"Ollama generate failed: {r.status_code} {body!r}")
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if "response" in obj and obj["response"]:
                        yield obj["response"]
                    if obj.get("done"):
                        break
```

- [ ] **Step 5: Create `tests/llm/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/llm/test_ollama.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/llm/__init__.py backend/llm/ollama.py tests/llm/__init__.py tests/llm/test_ollama.py
git commit -m "Add OllamaClient (embed + streaming generate)"
```

---

## Task 8: LanceDB store

**Files:**
- Create: `backend/rag/__init__.py`
- Create: `backend/rag/store.py`
- Create: `tests/rag/__init__.py`
- Create: `tests/rag/test_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/rag/test_store.py
from __future__ import annotations

from pathlib import Path

import pytest

from backend.rag.store import Chunk, LanceStore


@pytest.fixture
def store(tmp_path: Path) -> LanceStore:
    return LanceStore(db_path=tmp_path / "lancedb", vector_dim=4)


def test_upsert_then_search(store: LanceStore) -> None:
    store.upsert([
        Chunk(id="a#0", path="a.md", text="alpha doc", vector=[1.0, 0.0, 0.0, 0.0]),
        Chunk(id="b#0", path="b.md", text="bravo doc", vector=[0.0, 1.0, 0.0, 0.0]),
        Chunk(id="c#0", path="c.md", text="charlie doc", vector=[0.0, 0.0, 1.0, 0.0]),
    ])
    hits = store.search(query_vec=[1.0, 0.0, 0.0, 0.0], k=2)
    assert hits[0].path == "a.md"
    assert len(hits) == 2


def test_upsert_replaces_existing_id(store: LanceStore) -> None:
    store.upsert([Chunk(id="a#0", path="a.md", text="v1", vector=[1.0, 0.0, 0.0, 0.0])])
    store.upsert([Chunk(id="a#0", path="a.md", text="v2", vector=[1.0, 0.0, 0.0, 0.0])])
    hits = store.search(query_vec=[1.0, 0.0, 0.0, 0.0], k=5)
    matching = [h for h in hits if h.id == "a#0"]
    assert len(matching) == 1
    assert matching[0].text == "v2"


def test_delete_by_path(store: LanceStore) -> None:
    store.upsert([
        Chunk(id="a#0", path="a.md", text="x", vector=[1.0, 0.0, 0.0, 0.0]),
        Chunk(id="a#1", path="a.md", text="y", vector=[0.0, 1.0, 0.0, 0.0]),
        Chunk(id="b#0", path="b.md", text="z", vector=[0.0, 0.0, 1.0, 0.0]),
    ])
    store.delete_by_path("a.md")
    hits = store.search(query_vec=[1.0, 0.0, 0.0, 0.0], k=10)
    assert all(h.path != "a.md" for h in hits)
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/rag/test_store.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/rag/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/rag/store.py`**

```python
"""LanceDB-backed vector store for vault chunks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import lancedb
import pyarrow as pa


@dataclass
class Chunk:
    id: str       # e.g. "<path>#<idx>"
    path: str     # vault-relative path
    text: str
    vector: list[float]


@dataclass
class SearchHit:
    id: str
    path: str
    text: str
    score: float


_TABLE = "chunks"


class LanceStore:
    def __init__(self, db_path: Path, vector_dim: int) -> None:
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.vector_dim = vector_dim
        self._db = lancedb.connect(str(self.db_path))
        self._ensure_table()

    def _ensure_table(self) -> None:
        if _TABLE not in self._db.table_names():
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("path", pa.string()),
                pa.field("text", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.vector_dim)),
            ])
            self._db.create_table(_TABLE, schema=schema)

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        tbl = self._db.open_table(_TABLE)
        rows = [
            {"id": c.id, "path": c.path, "text": c.text, "vector": c.vector}
            for c in chunks
        ]
        # LanceDB upsert: delete by id then add
        ids = [c.id for c in chunks]
        tbl.delete(f"id IN {tuple(ids) if len(ids) > 1 else f'(\"{ids[0]}\")'}")
        tbl.add(rows)

    def delete_by_path(self, path: str) -> None:
        tbl = self._db.open_table(_TABLE)
        tbl.delete(f"path = '{path}'")

    def search(self, query_vec: list[float], k: int = 8) -> list[SearchHit]:
        tbl = self._db.open_table(_TABLE)
        result = tbl.search(query_vec).limit(k).to_list()
        out: list[SearchHit] = []
        for row in result:
            out.append(SearchHit(
                id=row["id"],
                path=row["path"],
                text=row["text"],
                score=float(row.get("_distance", 0.0)),
            ))
        return out
```

- [ ] **Step 5: Create `tests/rag/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/rag/test_store.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/rag/__init__.py backend/rag/store.py tests/rag/__init__.py tests/rag/test_store.py
git commit -m "Add LanceStore (upsert / delete_by_path / search)"
```

---

## Task 9: Markdown chunking + RAG indexer (bulk)

**Files:**
- Create: `backend/rag/chunk.py`
- Create: `backend/rag/indexer.py`
- Create: `tests/rag/test_chunk.py`
- Create: `tests/rag/test_indexer.py`

- [ ] **Step 1: Write failing tests for chunking**

```python
# tests/rag/test_chunk.py
from __future__ import annotations

from backend.rag.chunk import chunk_markdown


def test_chunk_short_doc_is_one_chunk() -> None:
    chunks = chunk_markdown("hello world", target_tokens=500)
    assert len(chunks) == 1
    assert chunks[0] == "hello world"


def test_chunk_splits_on_paragraph_boundaries() -> None:
    body = ("para one. " * 50) + "\n\n" + ("para two. " * 50)
    chunks = chunk_markdown(body, target_tokens=80)
    assert len(chunks) >= 2
    assert all(len(c.split()) <= 200 for c in chunks)  # rough cap


def test_chunk_strips_frontmatter() -> None:
    body = "---\nfoo: 1\n---\n\nactual content\n"
    chunks = chunk_markdown(body, target_tokens=500)
    assert "foo: 1" not in chunks[0]
    assert "actual content" in chunks[0]
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/rag/test_chunk.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/rag/chunk.py`**

```python
"""Markdown chunking — paragraph-aware, target token size."""
from __future__ import annotations

from backend.vault.frontmatter import load


def _tok_estimate(s: str) -> int:
    # Rough: 1 token ≈ 0.75 words for English; 1 char ≈ 0.5 tokens for Korean.
    # We use a simple word-count proxy + Korean character bias.
    words = len(s.split())
    ko_chars = sum(1 for c in s if "가" <= c <= "힯")
    return words + ko_chars // 2


def chunk_markdown(text: str, target_tokens: int = 500) -> list[str]:
    _, body = load(text)
    body = body.strip()
    if not body:
        return []

    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    buf_tok = 0

    for p in paragraphs:
        ptok = _tok_estimate(p)
        if buf and buf_tok + ptok > target_tokens:
            chunks.append("\n\n".join(buf))
            buf, buf_tok = [], 0
        buf.append(p)
        buf_tok += ptok

    if buf:
        chunks.append("\n\n".join(buf))

    return chunks
```

- [ ] **Step 4: Run chunk tests, verify pass**

Run: `pytest tests/rag/test_chunk.py -v`
Expected: 3 passed.

- [ ] **Step 5: Write failing tests for indexer**

```python
# tests/rag/test_indexer.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.rag.indexer import Indexer
from backend.rag.store import LanceStore


@pytest.mark.asyncio
async def test_index_directory_indexes_all_md(tmp_vault: Path, tmp_path: Path) -> None:
    (tmp_vault / "a.md").write_text("---\n---\n# A\n\nhello world\n", encoding="utf-8")
    (tmp_vault / "b.md").write_text("---\n---\n# B\n\ngoodbye world\n", encoding="utf-8")

    store = LanceStore(db_path=tmp_path / "db", vector_dim=4)
    embedder = AsyncMock(side_effect=lambda model, text: [1.0, 0.0, 0.0, 0.0])
    indexer = Indexer(store=store, embed=embedder, embed_model="nomic-embed-text")

    n = await indexer.index_directory(tmp_vault)
    assert n == 2  # 2 files, each one chunk

    hits = store.search(query_vec=[1.0, 0.0, 0.0, 0.0], k=10)
    paths = {h.path for h in hits}
    assert paths == {"a.md", "b.md"}


@pytest.mark.asyncio
async def test_index_skips_obsidian_metadata(tmp_vault: Path, tmp_path: Path) -> None:
    (tmp_vault / ".obsidian").mkdir(exist_ok=True)
    (tmp_vault / ".obsidian" / "workspace.json").write_text("{}", encoding="utf-8")
    (tmp_vault / "a.md").write_text("hello", encoding="utf-8")

    store = LanceStore(db_path=tmp_path / "db", vector_dim=4)
    embedder = AsyncMock(return_value=[1.0, 0.0, 0.0, 0.0])
    indexer = Indexer(store=store, embed=embedder, embed_model="nomic-embed-text")

    n = await indexer.index_directory(tmp_vault)
    assert n == 1


@pytest.mark.asyncio
async def test_index_skips_traces_proposals_and_queue(tmp_vault: Path, tmp_path: Path) -> None:
    """Per deep-dive §4: _traces, _proposals, and _-prefix files are operational, not knowledge."""
    (tmp_vault / "_traces").mkdir(exist_ok=True)
    (tmp_vault / "_traces" / "sid.md").write_text("trace dump", encoding="utf-8")
    (tmp_vault / "_proposals").mkdir(exist_ok=True)
    (tmp_vault / "_proposals" / "MOC-foo.md").write_text("proposal", encoding="utf-8")
    (tmp_vault / "_review-queue.md").write_text("queue", encoding="utf-8")
    (tmp_vault / "a.md").write_text("real content", encoding="utf-8")

    store = LanceStore(db_path=tmp_path / "db", vector_dim=4)
    embedder = AsyncMock(return_value=[1.0, 0.0, 0.0, 0.0])
    indexer = Indexer(store=store, embed=embedder, embed_model="nomic-embed-text")

    n = await indexer.index_directory(tmp_vault)
    assert n == 1   # only a.md
```

- [ ] **Step 6: Run to fail**

Run: `pytest tests/rag/test_indexer.py -v`
Expected: ImportError.

- [ ] **Step 7: Implement `backend/rag/indexer.py`**

```python
"""Index vault markdown files into LanceDB."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from backend.rag.chunk import chunk_markdown
from backend.rag.store import Chunk, LanceStore

EmbedFn = Callable[[str, str], Awaitable[list[float]]]
"""(model, text) -> vector"""

_SKIP_DIRS = {".obsidian", ".trash", "node_modules", ".git", "_traces", "_proposals"}
# Underscore-prefixed root files like _review-queue.md are also skipped — they're
# operational queues, not knowledge. See deep-dive §1 & §4.


def _vault_relative(p: Path, root: Path) -> str:
    return str(p.relative_to(root))


class Indexer:
    def __init__(self, *, store: LanceStore, embed: EmbedFn, embed_model: str) -> None:
        self.store = store
        self.embed = embed
        self.embed_model = embed_model

    async def index_directory(self, root: Path) -> int:
        chunks_total = 0
        for md in self._walk_md(root):
            chunks_total += await self.index_file(md, root)
        return chunks_total

    async def index_file(self, file: Path, root: Path) -> int:
        rel = _vault_relative(file, root)
        text = file.read_text(encoding="utf-8")
        pieces = chunk_markdown(text)
        if not pieces:
            self.store.delete_by_path(rel)
            return 0
        self.store.delete_by_path(rel)
        chunks: list[Chunk] = []
        for i, piece in enumerate(pieces):
            vec = await self.embed(self.embed_model, piece)
            chunks.append(Chunk(id=f"{rel}#{i}", path=rel, text=piece, vector=vec))
        self.store.upsert(chunks)
        return len(chunks)

    def _walk_md(self, root: Path):
        for p in root.rglob("*.md"):
            if any(part in _SKIP_DIRS for part in p.parts):
                continue
            if p.name.startswith("_"):
                # _review-queue.md, _moc-proposal-*.md, etc. are operational, not knowledge.
                continue
            yield p
```

- [ ] **Step 8: Run indexer tests, verify pass**

Run: `pytest tests/rag/test_indexer.py -v`
Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
git add backend/rag/chunk.py backend/rag/indexer.py tests/rag/test_chunk.py tests/rag/test_indexer.py
git commit -m "Add RAG markdown chunker + Indexer.index_directory/file"
```

---

## Task 10: Hybrid RAG search (vector + BM25)

**Files:**
- Create: `backend/rag/search.py`
- Create: `tests/rag/test_search.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/rag/test_search.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.rag.indexer import Indexer
from backend.rag.search import HybridSearcher
from backend.rag.store import LanceStore


@pytest.mark.asyncio
async def test_hybrid_search_combines_vector_and_bm25(tmp_vault: Path, tmp_path: Path) -> None:
    (tmp_vault / "litellm.md").write_text("LiteLLM router pattern unifies Claude and Gemini", encoding="utf-8")
    (tmp_vault / "whisper.md").write_text("mlx-whisper transcribes Korean audio", encoding="utf-8")

    store = LanceStore(db_path=tmp_path / "db", vector_dim=4)

    async def fake_embed(model: str, text: str) -> list[float]:
        # very crude: 1.0 in slot 0 if "litellm" in text, slot 1 if "whisper"
        return [
            1.0 if "litellm" in text.lower() else 0.0,
            1.0 if "whisper" in text.lower() else 0.0,
            0.0,
            0.0,
        ]

    indexer = Indexer(store=store, embed=fake_embed, embed_model="nomic")
    await indexer.index_directory(tmp_vault)

    searcher = HybridSearcher(
        store=store,
        embed=fake_embed,
        embed_model="nomic",
        documents=[(c, p) for c, p in _iter_chunks(store)],
    )
    hits = await searcher.search("litellm router", k=2)
    assert hits[0].path == "litellm.md"


def _iter_chunks(store: LanceStore):
    # helper that pulls all chunks from the store for BM25 corpus
    tbl = store._db.open_table("chunks").to_pandas()
    for _, row in tbl.iterrows():
        yield row["text"], row["path"]
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/rag/test_search.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/rag/search.py`**

```python
"""Hybrid (vector + BM25) search over LanceDB chunks."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from backend.rag.store import LanceStore, SearchHit

EmbedFn = Callable[[str, str], Awaitable[list[float]]]


@dataclass
class HybridHit:
    id: str
    path: str
    text: str
    score: float


def _tokenize(s: str) -> list[str]:
    return [t.lower() for t in s.split() if t.strip()]


class HybridSearcher:
    """Combines LanceDB ANN (alpha) + BM25 (1-alpha) scores."""

    def __init__(
        self,
        *,
        store: LanceStore,
        embed: EmbedFn,
        embed_model: str,
        documents: Iterable[tuple[str, str]],
        alpha: float = 0.7,
    ) -> None:
        self.store = store
        self.embed = embed
        self.embed_model = embed_model
        self.alpha = alpha
        docs = list(documents)
        self._texts = [d[0] for d in docs]
        self._paths = [d[1] for d in docs]
        self._bm25 = BM25Okapi([_tokenize(t) for t in self._texts]) if self._texts else None

    async def search(self, query: str, k: int = 8) -> list[HybridHit]:
        qvec = await self.embed(self.embed_model, query)
        vec_hits = self.store.search(query_vec=qvec, k=k * 3)  # over-fetch then re-rank

        # BM25 scores keyed by path (max score across that path's chunks)
        bm25_by_path: dict[str, float] = {}
        if self._bm25:
            qtoks = _tokenize(query)
            scores = self._bm25.get_scores(qtoks)
            max_score = max(scores) or 1.0
            for s, path in zip(scores, self._paths, strict=False):
                norm = float(s) / max_score
                if norm > bm25_by_path.get(path, 0.0):
                    bm25_by_path[path] = norm

        # Vector scores normalized inversely (LanceDB returns distance, smaller = closer)
        if not vec_hits:
            return []
        max_dist = max(h.score for h in vec_hits) or 1.0
        out: list[HybridHit] = []
        seen: set[str] = set()
        for h in vec_hits:
            if h.id in seen:
                continue
            seen.add(h.id)
            vec_score = 1.0 - (h.score / max_dist)
            bm_score = bm25_by_path.get(h.path, 0.0)
            blended = self.alpha * vec_score + (1.0 - self.alpha) * bm_score
            out.append(HybridHit(id=h.id, path=h.path, text=h.text, score=blended))

        out.sort(key=lambda x: x.score, reverse=True)
        return out[:k]
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/rag/test_search.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/rag/search.py tests/rag/test_search.py
git commit -m "Add HybridSearcher (vector + BM25 blended scoring)"
```

---

## Task 11: Vault Watcher (incremental re-embed)

**Files:**
- Create: `backend/rag/watcher.py`
- Create: `tests/rag/test_watcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/rag/test_watcher.py
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.rag.watcher import VaultWatcher


@pytest.mark.asyncio
async def test_watcher_triggers_reindex_on_modify(tmp_vault: Path) -> None:
    file = tmp_vault / "a.md"
    file.write_text("v1", encoding="utf-8")

    on_change = AsyncMock()
    w = VaultWatcher(root=tmp_vault, on_change=on_change, debounce_ms=50)
    await w.start()
    try:
        file.write_text("v2", encoding="utf-8")
        # wait > debounce
        await asyncio.sleep(0.3)
        assert on_change.await_count >= 1
        call_args = on_change.await_args
        assert call_args is not None
        path_arg = call_args[0][0]
        assert Path(path_arg).resolve() == file.resolve()
    finally:
        await w.stop()


@pytest.mark.asyncio
async def test_watcher_ignores_obsidian_dir(tmp_vault: Path) -> None:
    (tmp_vault / ".obsidian").mkdir(exist_ok=True)
    on_change = AsyncMock()
    w = VaultWatcher(root=tmp_vault, on_change=on_change, debounce_ms=50)
    await w.start()
    try:
        (tmp_vault / ".obsidian" / "x.json").write_text("{}", encoding="utf-8")
        await asyncio.sleep(0.3)
        assert on_change.await_count == 0
    finally:
        await w.stop()
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/rag/test_watcher.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/rag/watcher.py`**

```python
"""Filesystem watcher for vault changes — debounced async callbacks."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

OnChangeFn = Callable[[Path], Awaitable[None]]

_SKIP_DIRS = {".obsidian", ".trash", "node_modules", ".git", "_traces", "_proposals"}


class _Handler(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[Path]) -> None:
        self.loop = loop
        self.queue = queue

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if not path.name.endswith(".md"):
            return
        if any(part in _SKIP_DIRS for part in path.parts):
            return
        if path.name.startswith("_"):
            # operational queue/proposal files — see deep-dive §4
            return
        asyncio.run_coroutine_threadsafe(self.queue.put(path), self.loop)


class VaultWatcher:
    def __init__(self, *, root: Path, on_change: OnChangeFn, debounce_ms: int = 2000) -> None:
        self.root = Path(root)
        self.on_change = on_change
        self.debounce = debounce_ms / 1000.0
        self._observer: Observer | None = None
        self._queue: asyncio.Queue[Path] | None = None
        self._worker: asyncio.Task | None = None

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._observer = Observer()
        self._observer.schedule(_Handler(loop, self._queue), str(self.root), recursive=True)
        self._observer.start()
        self._worker = asyncio.create_task(self._drain())

    async def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    async def _drain(self) -> None:
        assert self._queue is not None
        pending: dict[Path, asyncio.TimerHandle] = {}
        loop = asyncio.get_running_loop()

        def fire(path: Path) -> None:
            pending.pop(path, None)
            asyncio.create_task(self.on_change(path))

        while True:
            path = await self._queue.get()
            handle = pending.get(path)
            if handle:
                handle.cancel()
            pending[path] = loop.call_later(self.debounce, fire, path)
```

- [ ] **Step 4: Run watcher tests, verify pass**

Run: `pytest tests/rag/test_watcher.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/rag/watcher.py tests/rag/test_watcher.py
git commit -m "Add VaultWatcher (watchdog + async debounce)"
```

---

## Task 12: Policy gate (offline mode + local-only redaction)

**Files:**
- Create: `backend/policy/__init__.py`
- Create: `backend/policy/gate.py`
- Create: `tests/policy/__init__.py`
- Create: `tests/policy/test_gate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/policy/test_gate.py
from __future__ import annotations

from pathlib import Path

import pytest

from backend.policy.gate import Decision, PolicyGate, RAGItem


def _ragitem(path: str, body: str, local_only: bool = False) -> RAGItem:
    return RAGItem(path=path, title=Path(path).stem, body=body, tags=[], local_only=local_only)


def test_offline_blocks_cloud_provider() -> None:
    gate = PolicyGate(offline_mode=True)
    d = gate.check(provider="anthropic", rag=[_ragitem("a.md", "ok")])
    assert d.action == "deny"
    assert "offline" in d.reason.lower()


def test_offline_allows_local_provider() -> None:
    gate = PolicyGate(offline_mode=True)
    d = gate.check(provider="ollama", rag=[_ragitem("a.md", "ok")])
    assert d.action == "allow"


def test_local_only_redacts_body_for_cloud() -> None:
    gate = PolicyGate(offline_mode=False)
    rag = [_ragitem("secret.md", "private body", local_only=True), _ragitem("ok.md", "public body")]
    d = gate.check(provider="anthropic", rag=rag)
    assert d.action == "allow"
    # secret.md should be redacted (no body, keep title+tags)
    redacted = {r.path: r for r in d.rag}
    assert redacted["secret.md"].body == ""
    assert redacted["ok.md"].body == "public body"


def test_local_only_unchanged_for_local_provider() -> None:
    gate = PolicyGate(offline_mode=False)
    rag = [_ragitem("secret.md", "private body", local_only=True)]
    d = gate.check(provider="ollama", rag=rag)
    assert d.rag[0].body == "private body"
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/policy/test_gate.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/policy/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/policy/gate.py`**

```python
"""Policy gate — the single choke-point for every cloud LLM call."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Provider = Literal["anthropic", "google", "ollama"]
Action = Literal["allow", "deny"]
LOCAL_PROVIDERS = {"ollama"}


@dataclass
class RAGItem:
    path: str
    title: str
    body: str
    tags: list[str] = field(default_factory=list)
    local_only: bool = False


@dataclass
class Decision:
    action: Action
    rag: list[RAGItem]
    reason: str


class PolicyGate:
    """Decides whether a call can proceed, and redacts local-only content for cloud providers."""

    def __init__(self, *, offline_mode: bool) -> None:
        self.offline_mode = offline_mode

    def check(self, *, provider: Provider, rag: list[RAGItem]) -> Decision:
        if self.offline_mode and provider not in LOCAL_PROVIDERS:
            return Decision(action="deny", rag=[], reason="offline mode is on")

        if provider in LOCAL_PROVIDERS:
            return Decision(action="allow", rag=rag, reason="local provider")

        # Cloud: redact bodies of local-only items but keep title + tags as a hint
        redacted: list[RAGItem] = []
        for item in rag:
            if item.local_only:
                redacted.append(RAGItem(
                    path=item.path, title=item.title, body="", tags=item.tags, local_only=True,
                ))
            else:
                redacted.append(item)
        return Decision(action="allow", rag=redacted, reason="cloud provider, local-only redacted")
```

- [ ] **Step 5: Create `tests/policy/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/policy/test_gate.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/policy/__init__.py backend/policy/gate.py tests/policy/__init__.py tests/policy/test_gate.py
git commit -m "Add PolicyGate (offline + local-only redaction)"
```

---

## Task 13: LiteLLM client wrapper

**Files:**
- Create: `backend/llm/router_client.py`
- Create: `tests/llm/test_router_client.py`

- [ ] **Step 1: Write failing tests (LiteLLM mocked)**

```python
# tests/llm/test_router_client.py
from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest

from backend.llm.router_client import LLMClient, ProviderKey


@pytest.mark.asyncio
async def test_chat_dispatches_anthropic_via_litellm() -> None:
    async def fake_chunks() -> AsyncIterator:
        for tok in ["hel", "lo"]:
            yield type("X", (), {"choices": [type("C", (), {"delta": type("D", (), {"content": tok})()})()]})()

    with patch("backend.llm.router_client.acompletion", new_callable=AsyncMock) as mock_acom:
        mock_acom.return_value = fake_chunks()
        client = LLMClient(anthropic_key="k", google_key="g", ollama_host="http://x")
        out: list[str] = []
        async for tok in client.chat(
            provider=ProviderKey.ANTHROPIC,
            model="claude-sonnet",
            messages=[{"role": "user", "content": "hi"}],
        ):
            out.append(tok)
        assert "".join(out) == "hello"
        assert mock_acom.await_args.kwargs["model"] == "claude-3-5-sonnet-latest"


@pytest.mark.asyncio
async def test_chat_dispatches_ollama_via_litellm() -> None:
    async def fake_chunks() -> AsyncIterator:
        yield type("X", (), {"choices": [type("C", (), {"delta": type("D", (), {"content": "ok"})()})()]})()

    with patch("backend.llm.router_client.acompletion", new_callable=AsyncMock) as mock_acom:
        mock_acom.return_value = fake_chunks()
        client = LLMClient(anthropic_key="k", google_key="g", ollama_host="http://localhost:11434")
        out = [t async for t in client.chat(
            provider=ProviderKey.OLLAMA, model="qwen2.5:14b", messages=[{"role": "user", "content": "hi"}],
        )]
        assert out == ["ok"]
        assert mock_acom.await_args.kwargs["model"] == "ollama/qwen2.5:14b"
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/llm/test_router_client.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/llm/router_client.py`**

```python
"""LiteLLM wrapper unifying Claude / Gemini / Ollama under one streaming API."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any

from litellm import acompletion


class ProviderKey(StrEnum):
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"


_MODEL_MAP: dict[tuple[ProviderKey, str], str] = {
    (ProviderKey.ANTHROPIC, "claude-haiku"): "claude-3-5-haiku-latest",
    (ProviderKey.ANTHROPIC, "claude-sonnet"): "claude-3-5-sonnet-latest",
    (ProviderKey.ANTHROPIC, "claude-opus"): "claude-opus-4-7",
    (ProviderKey.GOOGLE, "gemini-flash"): "gemini/gemini-2.5-flash",
    (ProviderKey.GOOGLE, "gemini-pro"): "gemini/gemini-2.5-pro",
}


def _resolve_model(provider: ProviderKey, name: str) -> str:
    if provider == ProviderKey.OLLAMA:
        return f"ollama/{name}"
    return _MODEL_MAP.get((provider, name), name)


class LLMClient:
    def __init__(self, *, anthropic_key: str, google_key: str, ollama_host: str) -> None:
        if anthropic_key:
            os.environ["ANTHROPIC_API_KEY"] = anthropic_key
        if google_key:
            os.environ["GOOGLE_API_KEY"] = google_key
        os.environ["OLLAMA_API_BASE"] = ollama_host

    async def chat(
        self,
        *,
        provider: ProviderKey,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        resolved = _resolve_model(provider, model)
        kwargs: dict[str, Any] = {
            "model": resolved,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        response = await acompletion(**kwargs)
        async for chunk in response:
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content
```

- [ ] **Step 4: Run, verify pass**

Run: `pytest tests/llm/test_router_client.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/llm/router_client.py tests/llm/test_router_client.py
git commit -m "Add LLMClient (LiteLLM-backed unified streaming chat)"
```

---

## Task 14: Router cascade (rules → classifier → scorer)

Per deep-dive §3, the router is a 3-stage cascade. This is split into three sub-tasks. Each ends with its own commit.

**Top-level files (all created across 14a-c):**
- Create: `backend/router/__init__.py`
- Create: `backend/router/rules.py`         (14a)
- Create: `backend/router/classifier.py`    (14b)
- Create: `backend/router/scorer.py`        (14c)
- Create: `backend/router/orchestrator.py`  (14c)
- Create: `tests/router/__init__.py`        (14a)
- Create: `tests/router/test_rules.py`      (14a)
- Create: `tests/router/test_classifier.py` (14b)
- Create: `tests/router/test_scorer.py`     (14c)
- Create: `tests/router/test_orchestrator.py` (14c)

---

### Task 14a — Stage 1: 33-rule pattern matcher

- [ ] **Step 1: Write failing rule tests**

```python
# tests/router/test_rules.py
from __future__ import annotations

import pytest

from backend.router.rules import classify_by_rules


@pytest.mark.parametrize(
    "text,expected_category,need_rag,need_web",
    [
        # code (8)
        ("```python\ndef foo(): pass\n```", "code", True, False),
        ("def foo() 어디 있어", "code", True, False),
        ("backend/main.py 보자", "code", True, False),
        ("스택트레이스: traceback", "code", True, False),
        ("코드 리뷰해줘", "code", True, False),
        ("리팩토링 부탁", "code", True, False),
        ("SELECT * FROM x", "code", True, False),
        ("이 함수 타입힌트 좀", "code", True, False),
        # web (5)
        ("https://example.com 요약", "web", False, True),
        ("오늘 비트코인 어때", "web", False, True),
        ("latest tesla news", "web", False, True),
        ("애플 주가 알려줘", "web", False, True),
        ("내일 날씨", "web", False, True),
        # rag (6)
        ("내 vault에서 검색", "rag", True, False),
        ("내 노트에 있던 거", "rag", True, False),
        ("MOC-trading 찾아", "rag", True, False),
        ("그거 모아줘", "rag", True, False),
        ("전에 말했었던 라우터", "rag", True, False),
        ("지난주에 정리한 내용", "rag", True, False),
        # reasoning (4) — note: long-text rule is order-sensitive; tested with explicit length
        ("이 시스템이 왜 그렇게 동작하는지 설명해줘 한 번 차근차근 정리해줘 좀 길게 부탁해", "reasoning", True, False),
        ("왜 그래?", "reasoning", True, False),
        ("어떻게 비교할 수 있을까", "reasoning", True, False),
        ("explain the trade-off", "reasoning", True, False),
        # schedule (3, Phase 2 — still classified at Stage 1)
        ("오늘 일정 보여줘", "schedule", False, False),
        ("내일 할일 목록", "schedule", False, False),
        ("내일 점심 미팅", "schedule", False, False),
        # default / greeting (3)
        ("안녕", "default", False, False),
        ("hi", "default", False, False),
        ("ㄱㄱ", "default", False, False),
        # force_* (4) — explicit model override, scorer skipped
        ("/claude 분석해", "_force_claude", False, False),
        ("/gemini 검색", "_force_gemini", False, True),
        ("/local 정리", "_force_local", False, False),
        ("/code def foo", "code", True, False),
    ],
)
def test_rules_match_category(text: str, expected_category: str, need_rag: bool, need_web: bool) -> None:
    decision = classify_by_rules(text)
    assert decision is not None, f"no rule matched: {text!r}"
    assert decision["category"] == expected_category
    assert decision["need_rag"] == need_rag
    assert decision["need_web"] == need_web


def test_rules_return_none_when_nothing_matches() -> None:
    # ordinary medium-length statement with no signals
    assert classify_by_rules("음 그러니까 잠깐만 그게 그러게") is None
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/router/test_rules.py -v`
Expected: ImportError on `backend.router.rules`.

- [ ] **Step 3: Implement `backend/router/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/router/rules.py`**

```python
"""Stage 1 — rule-based classification. 33 patterns; see deep-dive §3."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict


class RuleDecision(TypedDict):
    category: str   # "code" | "web" | "rag" | "reasoning" | "schedule" | "default"
                    # plus force overrides: "_force_claude" | "_force_gemini" | "_force_local"
    need_rag: bool
    need_web: bool


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    category: str
    need_rag: bool
    need_web: bool


_RULES: list[_Rule] = [
    # force overrides first — explicit user intent wins
    _Rule(re.compile(r"^\s*/claude\b"), "_force_claude", False, False),
    _Rule(re.compile(r"^\s*/gemini\b"), "_force_gemini", False, True),
    _Rule(re.compile(r"^\s*/local\b"), "_force_local", False, False),
    _Rule(re.compile(r"^\s*/code\b"), "code", True, False),
    # code (8)
    _Rule(re.compile(r"```"), "code", True, False),
    _Rule(re.compile(r"\b(def|class|import|return|async|await|yield)\b"), "code", True, False),
    _Rule(re.compile(r"[a-zA-Z_/.]+\.(py|ts|tsx|js|jsx|swift|md|yaml|yml|json|sh|toml)\b"), "code", True, False),
    _Rule(re.compile(r"\b(backend|frontend|src|tests|scripts)/"), "code", True, False),
    _Rule(re.compile(r"\b(stack ?trace|traceback|exception|error ?log)\b", re.IGNORECASE), "code", True, False),
    _Rule(re.compile(r"리팩토링|버그|코드 ?리뷰|디버그"), "code", True, False),
    _Rule(re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\s+\w"), "code", True, False),
    _Rule(re.compile(r"\b(typehint|타입 ?힌트|시그니처)\b"), "code", True, False),
    # web (5)
    _Rule(re.compile(r"https?://"), "web", False, True),
    _Rule(re.compile(r"\b(오늘|어제|최근|지금|요즘|현재)\b"), "web", False, True),
    _Rule(re.compile(r"\b(latest|today|yesterday|news|breaking)\b", re.IGNORECASE), "web", False, True),
    _Rule(re.compile(r"\b(주가|환율|시세|가격)\b"), "web", False, True),
    _Rule(re.compile(r"\b(weather|날씨)\b", re.IGNORECASE), "web", False, True),
    # rag (6)
    _Rule(re.compile(r"vault|볼트"), "rag", True, False),
    _Rule(re.compile(r"내 ?(노트|메모|기록)"), "rag", True, False),
    _Rule(re.compile(r"\b(atom|MOC|wiki)\b", re.IGNORECASE), "rag", True, False),
    _Rule(re.compile(r"검색해|찾아|모아|정리해"), "rag", True, False),
    _Rule(re.compile(r"전에 (말|얘기)했(었)?(는데|던)"), "rag", True, False),
    _Rule(re.compile(r"지난주|지난달|작년"), "rag", True, False),
    # reasoning (4)
    _Rule(re.compile(r"^.{60,}", re.DOTALL), "reasoning", True, False),  # ≥ 60 chars
    _Rule(re.compile(r"\b(왜|어떻게|분석|설명|비교)\b"), "reasoning", True, False),
    _Rule(re.compile(r"\b(why|how|analyze|explain|compare)\b", re.IGNORECASE), "reasoning", True, False),
    _Rule(re.compile(r"\?[^?\n]*\?"), "reasoning", True, False),  # two question marks
    # schedule (3, Phase 2 active)
    _Rule(re.compile(r"오늘 ?일정|내일 ?일정|이번주 ?일정|일정"), "schedule", False, False),
    _Rule(re.compile(r"할 ?일|todo|task", re.IGNORECASE), "schedule", False, False),
    _Rule(re.compile(r"\b(미팅|회의|약속|점심|저녁)\b"), "schedule", False, False),
    # default / greeting (3)
    _Rule(re.compile(r"^\s*(안녕|hi|hello|hey|반가워)\b", re.IGNORECASE), "default", False, False),
    _Rule(re.compile(r"^.{1,4}$"), "default", False, False),  # ≤ 4 chars
    _Rule(re.compile(r"고마워|감사|thanks", re.IGNORECASE), "default", False, False),
]


def classify_by_rules(text: str) -> RuleDecision | None:
    """Return the first matching rule's decision, or None if no rule matches."""
    for rule in _RULES:
        if rule.pattern.search(text):
            return {
                "category": rule.category,
                "need_rag": rule.need_rag,
                "need_web": rule.need_web,
            }
    return None
```

- [ ] **Step 5: Create `tests/router/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Run rule tests, verify pass**

Run: `pytest tests/router/test_rules.py -v`
Expected: ≥ 30 parameterized passes + the negative test = ≥ 31 passed.

- [ ] **Step 7: Commit 14a**

```bash
git add backend/router/__init__.py backend/router/rules.py tests/router/__init__.py tests/router/test_rules.py
git commit -m "Add Router Stage 1: 33-rule pattern matcher (force/code/web/rag/reasoning/schedule/default)"
```

---

### Task 14b — Stage 2: 0.5b classifier with JSON-mode

- [ ] **Step 1: Write failing classifier tests**

```python
# tests/router/test_classifier.py
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from backend.router.classifier import OllamaClassifier


async def _stream(s: str) -> AsyncIterator[str]:
    yield s


@pytest.mark.asyncio
async def test_classifier_parses_json_response() -> None:
    raw = json.dumps({"category": "rag", "need_rag": True, "need_web": False, "confidence": 0.78})
    chat = AsyncMock(return_value=_stream(raw))
    c = OllamaClassifier(chat=chat, model="qwen2.5:0.5b")
    result = await c.classify("내가 전에 정리한 거")
    assert result["category"] == "rag"
    assert result["need_rag"] is True
    assert result["confidence"] == 0.78


@pytest.mark.asyncio
async def test_classifier_low_confidence_demotes_to_default() -> None:
    raw = json.dumps({"category": "reasoning", "need_rag": True, "need_web": False, "confidence": 0.42})
    chat = AsyncMock(return_value=_stream(raw))
    c = OllamaClassifier(chat=chat, model="qwen2.5:0.5b")
    result = await c.classify("음 그래")
    assert result["category"] == "default"      # confidence < 0.6 → default
    assert result["need_rag"] is True           # original flag preserved


@pytest.mark.asyncio
async def test_classifier_invalid_json_returns_default() -> None:
    chat = AsyncMock(return_value=_stream("not json at all"))
    c = OllamaClassifier(chat=chat, model="qwen2.5:0.5b")
    result = await c.classify("x")
    assert result == {"category": "default", "need_rag": False, "need_web": False, "confidence": 0.0}


@pytest.mark.asyncio
async def test_classifier_missing_fields_returns_default() -> None:
    chat = AsyncMock(return_value=_stream(json.dumps({"only": "this"})))
    c = OllamaClassifier(chat=chat, model="qwen2.5:0.5b")
    result = await c.classify("x")
    assert result["category"] == "default"
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/router/test_classifier.py -v`
Expected: ImportError on `backend.router.classifier`.

- [ ] **Step 3: Implement `backend/router/classifier.py`**

```python
"""Stage 2 — 0.5b LLM classifier with JSON-mode + confidence guardrail (deep-dive §3)."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypedDict

ChatFn = Callable[..., Awaitable[AsyncIterator[str]]]


class ClassifierResult(TypedDict):
    category: str
    need_rag: bool
    need_web: bool
    confidence: float


_VALID_CATEGORIES = {"code", "web", "rag", "reasoning", "schedule", "default"}
_CONFIDENCE_FLOOR = 0.6


_SYSTEM = (
    "You are a query classifier for a personal assistant. "
    "Given a Korean/English query, output ONLY a JSON object: "
    '{"category":"code|web|rag|reasoning|schedule|default",'
    '"need_rag":true|false,"need_web":true|false,"confidence":0.0~1.0}. '
    "No prose, no explanation. If unsure, category=\"default\" with confidence<=0.5."
)


async def _drain(stream: AsyncIterator[str]) -> str:
    parts: list[str] = []
    async for tok in stream:
        parts.append(tok)
    return "".join(parts).strip()


def _default() -> ClassifierResult:
    return {"category": "default", "need_rag": False, "need_web": False, "confidence": 0.0}


class OllamaClassifier:
    def __init__(self, *, chat: ChatFn, model: str = "qwen2.5:0.5b") -> None:
        self.chat = chat
        self.model = model

    async def classify(self, text: str) -> ClassifierResult:
        stream = await self.chat(messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Query: {text}\nJSON:"},
        ])
        raw = await _drain(stream)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return _default()
        category = obj.get("category")
        if category not in _VALID_CATEGORIES:
            return _default()
        need_rag = bool(obj.get("need_rag", False))
        need_web = bool(obj.get("need_web", False))
        confidence = float(obj.get("confidence", 0.0))
        if confidence < _CONFIDENCE_FLOOR:
            return {"category": "default", "need_rag": need_rag, "need_web": need_web, "confidence": confidence}
        return {"category": category, "need_rag": need_rag, "need_web": need_web, "confidence": confidence}
```

- [ ] **Step 4: Run classifier tests, verify pass**

Run: `pytest tests/router/test_classifier.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit 14b**

```bash
git add backend/router/classifier.py tests/router/test_classifier.py
git commit -m "Add Router Stage 2: 0.5b classifier with JSON-mode + confidence floor"
```

---

### Task 14c — Stage 3: Scorer + Orchestrator

- [ ] **Step 1: Write failing scorer tests**

```python
# tests/router/test_scorer.py
from __future__ import annotations

from backend.router.scorer import ModelChoice, pick_model


def test_reasoning_default_picks_claude_sonnet() -> None:
    choice = pick_model(category="default", input_tokens=500)
    assert isinstance(choice, ModelChoice)
    assert choice.provider == "anthropic"
    assert choice.model == "claude-sonnet"


def test_code_picks_qwen_coder() -> None:
    choice = pick_model(category="code", input_tokens=500)
    assert choice.provider == "ollama"
    assert choice.model == "qwen2.5-coder:7b"


def test_rag_short_picks_local_qwen14b() -> None:
    choice = pick_model(category="rag", input_tokens=500)
    assert choice.provider == "ollama"
    assert choice.model == "qwen2.5:14b"


def test_web_forced_to_gemini_flash() -> None:
    choice = pick_model(category="web", input_tokens=500)
    assert choice.provider == "google"
    assert choice.model == "gemini-flash"


def test_long_ctx_forces_claude_opus() -> None:
    choice = pick_model(category="reasoning", input_tokens=200_000)
    assert choice.provider == "anthropic"
    assert choice.model == "claude-opus"


def test_force_claude_override() -> None:
    choice = pick_model(category="_force_claude", input_tokens=500)
    assert choice.provider == "anthropic"
    assert choice.model == "claude-sonnet"


def test_force_local_override() -> None:
    choice = pick_model(category="_force_local", input_tokens=500)
    assert choice.provider == "ollama"


def test_choice_includes_score_breakdown() -> None:
    choice = pick_model(category="rag", input_tokens=500)
    assert isinstance(choice.candidate_scores, dict)
    assert "qwen2.5:14b" in choice.candidate_scores
    assert "claude-haiku" in choice.candidate_scores
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/router/test_scorer.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/router/scorer.py`**

```python
"""Stage 3 — score-based model selection (deep-dive §3 table)."""
from __future__ import annotations

from dataclasses import dataclass, field

# (provider, model_logical_name) → (quality, speed, cost) on a 1..10 scale.
_MODEL_TABLE: dict[tuple[str, str], tuple[int, int, int]] = {
    ("anthropic", "claude-opus"):  (10, 3, 10),
    ("anthropic", "claude-sonnet"): (9, 6, 6),
    ("anthropic", "claude-haiku"):  (7, 9, 2),
    ("google",    "gemini-pro"):    (9, 5, 5),
    ("google",    "gemini-flash"):  (7, 8, 1),
    ("ollama",    "qwen2.5:14b"):       (7, 7, 0),
    ("ollama",    "qwen2.5-coder:7b"):  (6, 8, 0),  # base quality; +2 in code
    ("ollama",    "qwen2.5:0.5b"):      (3, 10, 0),
}

# Bonuses applied conditionally (deep-dive §3).
_KO_BONUS = {
    ("anthropic", "claude-opus"): 1.0,
    ("anthropic", "claude-sonnet"): 1.0,
    ("anthropic", "claude-haiku"): 0.5,
    ("ollama", "qwen2.5:14b"): 1.0,
}
_CODE_BONUS = {
    ("anthropic", "claude-opus"): 1.0,
    ("anthropic", "claude-sonnet"): 1.0,
    ("ollama", "qwen2.5:14b"): 0.5,
    ("ollama", "qwen2.5-coder:7b"): 2.0,
}

# Category → (α quality, β speed, γ cost).
_WEIGHTS: dict[str, tuple[float, float, float]] = {
    "reasoning": (1.0, 0.2, 0.5),
    "code":      (0.7, 0.5, 0.6),
    "rag":       (0.5, 1.0, 0.8),
    "schedule":  (0.5, 1.0, 0.5),
    "default":   (0.8, 0.5, 0.5),
}

_LONG_CTX_THRESHOLD = 100_000


@dataclass
class ModelChoice:
    provider: str
    model: str
    score: float
    reason: str
    candidate_scores: dict[str, float] = field(default_factory=dict)


def pick_model(*, category: str, input_tokens: int) -> ModelChoice:
    # 1) Force overrides (deep-dive §3 stage-1 force_*)
    if category == "_force_claude":
        return ModelChoice("anthropic", "claude-sonnet", score=99.0, reason="force-claude")
    if category == "_force_gemini":
        return ModelChoice("google", "gemini-flash", score=99.0, reason="force-gemini")
    if category == "_force_local":
        return ModelChoice("ollama", "qwen2.5:14b", score=99.0, reason="force-local")

    # 2) Hard rules: web → Gemini grounding; long ctx → Opus
    if category == "web":
        return ModelChoice("google", "gemini-flash", score=99.0, reason="web grounding required")
    if input_tokens > _LONG_CTX_THRESHOLD:
        return ModelChoice("anthropic", "claude-opus", score=99.0, reason=f"ctx {input_tokens} > 100k")

    # 3) Scored selection
    alpha, beta, gamma = _WEIGHTS.get(category, _WEIGHTS["default"])
    scores: dict[str, float] = {}
    for (provider, model), (q, s, c) in _MODEL_TABLE.items():
        ko = _KO_BONUS.get((provider, model), 0.0)
        code = _CODE_BONUS.get((provider, model), 0.0) if category == "code" else 0.0
        score = alpha * (q + ko + code) + beta * s - gamma * c
        scores[f"{model}"] = round(score, 3)

    best_model = max(scores, key=lambda k: scores[k])
    # Reverse-lookup the provider for the chosen model
    provider = next(p for (p, m) in _MODEL_TABLE if m == best_model)
    return ModelChoice(
        provider=provider,
        model=best_model,
        score=scores[best_model],
        reason=f"category={category} scorer",
        candidate_scores=scores,
    )
```

- [ ] **Step 4: Run scorer tests, verify pass**

Run: `pytest tests/router/test_scorer.py -v`
Expected: 8 passed.

- [ ] **Step 5: Write failing orchestrator tests**

```python
# tests/router/test_orchestrator.py
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.router.orchestrator import RouteDecision, Router


@pytest.mark.asyncio
async def test_rule_match_short_rag_uses_scorer_and_skips_classifier() -> None:
    classifier = AsyncMock()
    r = Router(classifier=classifier)
    d = await r.route(text="내 vault에서 atom 검색", input_tokens=200)
    assert isinstance(d, RouteDecision)
    assert d.provider == "ollama"
    assert d.model == "qwen2.5:14b"
    assert d.need_rag is True
    classifier.classify.assert_not_awaited()
    assert "stage1" in d.reason


@pytest.mark.asyncio
async def test_web_rule_short_circuits_to_gemini() -> None:
    classifier = AsyncMock()
    r = Router(classifier=classifier)
    d = await r.route(text="오늘 뉴스", input_tokens=200)
    assert d.provider == "google"
    assert d.model == "gemini-flash"
    assert d.need_web is True


@pytest.mark.asyncio
async def test_long_ctx_forces_opus_even_with_rule_match() -> None:
    classifier = AsyncMock()
    r = Router(classifier=classifier)
    d = await r.route(text="긴 reasoning 부탁 분석해", input_tokens=200_000)
    assert d.provider == "anthropic"
    assert d.model == "claude-opus"


@pytest.mark.asyncio
async def test_no_rule_falls_through_to_classifier() -> None:
    classifier = AsyncMock()
    classifier.classify.return_value = {
        "category": "default", "need_rag": False, "need_web": False, "confidence": 0.8,
    }
    r = Router(classifier=classifier)
    d = await r.route(text="음 잠깐만 어떻게 보지 좀 봐", input_tokens=100)
    classifier.classify.assert_awaited_once()
    assert d.provider == "anthropic"
    assert d.model == "claude-sonnet"


@pytest.mark.asyncio
async def test_force_claude_via_rule_uses_override() -> None:
    classifier = AsyncMock()
    r = Router(classifier=classifier)
    d = await r.route(text="/claude 분석해줘", input_tokens=100)
    assert d.provider == "anthropic"
    assert "force" in d.reason
```

- [ ] **Step 6: Run to fail**

Run: `pytest tests/router/test_orchestrator.py -v`
Expected: ImportError on `backend.router.orchestrator`.

- [ ] **Step 7: Implement `backend/router/orchestrator.py`**

```python
"""Router orchestrator: rules → classifier → scorer (deep-dive §3 cascade)."""
from __future__ import annotations

from dataclasses import dataclass

from backend.router.classifier import ClassifierResult, OllamaClassifier
from backend.router.rules import classify_by_rules
from backend.router.scorer import ModelChoice, pick_model

SYSTEM_KO = (
    "너는 vault 기반 개인 비서. 한국어 자연스럽게, 사실 기반, "
    "모르면 모른다고 답한다."
)


@dataclass
class RouteDecision:
    provider: str
    model: str
    system_prompt: str
    need_rag: bool
    need_web: bool
    reason: str
    score: float = 0.0
    candidate_scores: dict[str, float] | None = None


def _decision_from_choice(
    choice: ModelChoice, *, need_rag: bool, need_web: bool, stage_reason: str,
) -> RouteDecision:
    return RouteDecision(
        provider=choice.provider,
        model=choice.model,
        system_prompt=SYSTEM_KO,
        need_rag=need_rag,
        need_web=need_web,
        reason=f"{stage_reason} → {choice.reason}",
        score=choice.score,
        candidate_scores=choice.candidate_scores,
    )


class Router:
    def __init__(self, *, classifier: OllamaClassifier | None) -> None:
        self.classifier = classifier

    async def route(self, *, text: str, input_tokens: int) -> RouteDecision:
        # Stage 1
        rule = classify_by_rules(text)
        if rule is not None:
            choice = pick_model(category=rule["category"], input_tokens=input_tokens)
            return _decision_from_choice(
                choice, need_rag=rule["need_rag"], need_web=rule["need_web"],
                stage_reason="stage1",
            )

        # Stage 2 — only when no rule fires and a classifier is wired
        if self.classifier is None:
            choice = pick_model(category="default", input_tokens=input_tokens)
            return _decision_from_choice(choice, need_rag=False, need_web=False, stage_reason="stage1-fallthrough")

        result: ClassifierResult = await self.classifier.classify(text)
        choice = pick_model(category=result["category"], input_tokens=input_tokens)
        return _decision_from_choice(
            choice, need_rag=result["need_rag"], need_web=result["need_web"],
            stage_reason=f"stage2:{result['category']}@{result['confidence']:.2f}",
        )
```

- [ ] **Step 8: Run orchestrator tests, verify pass**

Run: `pytest tests/router/test_orchestrator.py -v`
Expected: 5 passed.

- [ ] **Step 9: Commit 14c**

```bash
git add backend/router/scorer.py backend/router/orchestrator.py \
        tests/router/test_scorer.py tests/router/test_orchestrator.py
git commit -m "Add Router Stage 3: scorer + orchestrator (rules→classifier→scorer cascade)"
```

---

## Task 15: Atom extraction + cross-link selection

**Files:**
- Create: `backend/pipeline/__init__.py`
- Create: `backend/pipeline/atomize.py`
- Create: `backend/pipeline/cross_link.py`
- Create: `tests/pipeline/__init__.py`
- Create: `tests/pipeline/test_atomize.py`
- Create: `tests/pipeline/test_cross_link.py`

- [ ] **Step 1: Write failing atomize tests**

```python
# tests/pipeline/test_atomize.py
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from backend.pipeline.atomize import extract_atom


async def _stream(s: str) -> AsyncIterator[str]:
    yield s


@pytest.mark.asyncio
async def test_extract_atom_parses_json_response() -> None:
    response = json.dumps({
        "title": "LiteLLM Router Pattern",
        "body": "통합 진입점.",
        "tags": ["ai/router"],
    })
    chat = AsyncMock(return_value=_stream(response))
    atom = await extract_atom(question="라우터 설명", answer="LiteLLM이 통합...", chat=chat)
    assert atom is not None
    assert atom.title == "LiteLLM Router Pattern"
    assert atom.tags == ["ai/router"]


@pytest.mark.asyncio
async def test_extract_atom_returns_none_for_smalltalk() -> None:
    chat = AsyncMock(return_value=_stream(json.dumps({"skip": True})))
    atom = await extract_atom(question="안녕", answer="안녕하세요", chat=chat)
    assert atom is None


@pytest.mark.asyncio
async def test_extract_atom_handles_invalid_json() -> None:
    chat = AsyncMock(return_value=_stream("not json"))
    atom = await extract_atom(question="x", answer="y", chat=chat)
    assert atom is None
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/pipeline/test_atomize.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/pipeline/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/pipeline/atomize.py`**

```python
"""LLM-driven atomic note extraction from (question, answer) pairs."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

ChatFn = Callable[..., Awaitable[AsyncIterator[str]]]
"""Same shape as LLMClient.chat (returns an async iterator of token strings)."""


@dataclass
class AtomCandidate:
    title: str
    body: str
    tags: list[str]


_SYSTEM = (
    "너는 atom 추출기다. 주어진 (질문, 답)에서 재사용 가능한 원자 지식이 있으면 "
    "{\"title\": \"...\", \"body\": \"...\", \"tags\": [...]} JSON 한 줄로 답해라. "
    "단순 잡담/인사면 {\"skip\": true} 만 답해라. 추가 설명 절대 금지."
)


async def _drain(stream: AsyncIterator[str]) -> str:
    parts: list[str] = []
    async for tok in stream:
        parts.append(tok)
    return "".join(parts).strip()


async def extract_atom(*, question: str, answer: str, chat: ChatFn) -> AtomCandidate | None:
    prompt = f"질문: {question}\n\n답: {answer}\n\nJSON으로만 답해라."
    stream = await chat(messages=[
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": prompt},
    ])
    raw = await _drain(stream)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if obj.get("skip"):
        return None
    title = obj.get("title")
    body = obj.get("body")
    if not title or not body:
        return None
    return AtomCandidate(title=title, body=body, tags=list(obj.get("tags", [])))
```

- [ ] **Step 5: Run atomize tests, verify pass**

Run: `pytest tests/pipeline/test_atomize.py -v`
Expected: 3 passed.

- [ ] **Step 6: Write failing cross_link tests**

```python
# tests/pipeline/test_cross_link.py
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from backend.pipeline.cross_link import pick_related


async def _stream(s: str) -> AsyncIterator[str]:
    yield s


@pytest.mark.asyncio
async def test_pick_related_filters_by_threshold_and_llm() -> None:
    candidates = [
        ("note-a", "alpha summary", 0.92),
        ("note-b", "bravo summary", 0.80),
        ("note-c", "charlie summary", 0.50),  # below threshold → dropped
        ("note-d", "delta summary", 0.78),
    ]
    response = json.dumps(["note-a", "note-d"])
    chat = AsyncMock(return_value=_stream(response))
    picked = await pick_related(
        atom_title="root",
        atom_body="root body",
        candidates=candidates,
        threshold=0.75,
        k_final=5,
        chat=chat,
    )
    assert picked == ["note-a", "note-d"]


@pytest.mark.asyncio
async def test_pick_related_caps_at_k_final() -> None:
    candidates = [(f"n{i}", "x", 0.9) for i in range(10)]
    response = json.dumps([f"n{i}" for i in range(10)])
    chat = AsyncMock(return_value=_stream(response))
    picked = await pick_related(
        atom_title="r", atom_body="b",
        candidates=candidates, threshold=0.7, k_final=3, chat=chat,
    )
    assert len(picked) == 3
```

- [ ] **Step 7: Run to fail**

Run: `pytest tests/pipeline/test_cross_link.py -v`
Expected: ImportError.

- [ ] **Step 8: Implement `backend/pipeline/cross_link.py`**

```python
"""Cross-link selection: threshold filter + LLM second-pass gate."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable

ChatFn = Callable[..., Awaitable[AsyncIterator[str]]]


_SYSTEM = (
    "주어진 atom과 후보 노트들 중에서 정말로 의미적으로 연결되는 노트의 slug만 "
    "JSON 배열로 답해라. 예: [\"note-a\", \"note-b\"]. 설명 금지."
)


async def _drain(stream: AsyncIterator[str]) -> str:
    parts: list[str] = []
    async for tok in stream:
        parts.append(tok)
    return "".join(parts).strip()


async def pick_related(
    *,
    atom_title: str,
    atom_body: str,
    candidates: list[tuple[str, str, float]],  # (slug, summary, score)
    threshold: float,
    k_final: int,
    chat: ChatFn,
) -> list[str]:
    filtered = [(s, m, sc) for s, m, sc in candidates if sc >= threshold]
    if not filtered:
        return []
    listing = "\n".join(f"- {slug}: {summ[:120]}" for slug, summ, _ in filtered)
    user = (
        f"Atom: {atom_title}\n{atom_body[:500]}\n\n"
        f"후보:\n{listing}\n\n"
        f"이 중 최대 {k_final}개의 의미적 연결 slug만 JSON 배열로."
    )
    stream = await chat(messages=[
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ])
    raw = await _drain(stream)
    try:
        names = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(names, list):
        return []
    valid_slugs = {s for s, _, _ in filtered}
    out = [n for n in names if isinstance(n, str) and n in valid_slugs]
    return out[:k_final]
```

- [ ] **Step 9: Create `tests/pipeline/__init__.py`** (empty)

```python
```

- [ ] **Step 10: Run cross_link tests, verify pass**

Run: `pytest tests/pipeline/test_cross_link.py -v`
Expected: 2 passed.

- [ ] **Step 11: Commit**

```bash
git add backend/pipeline/__init__.py backend/pipeline/atomize.py backend/pipeline/cross_link.py \
        tests/pipeline/__init__.py tests/pipeline/test_atomize.py tests/pipeline/test_cross_link.py
git commit -m "Add atom extraction + cross-link selection (threshold + LLM gate)"
```

---

## Task 16: Trace builder

Per deep-dive §5, every `/chat` response carries a 7-stage decision trace and persists it to `assistant/_traces/<sid>.json` for offline analysis. This task is the foundation: subsequent tasks (chat endpoint, integration) thread a `TraceBuilder` through the pipeline.

**Files:**
- Create: `backend/trace/__init__.py`
- Create: `backend/trace/builder.py`
- Create: `tests/trace/__init__.py`
- Create: `tests/trace/test_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/trace/test_builder.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.trace.builder import TraceBuilder


def test_finalize_includes_all_seven_stages_plus_meta() -> None:
    b = TraceBuilder(session_id="sid-1")
    out = b.finalize()
    keys = set(out.keys())
    assert {"session_id", "stt", "router", "policy", "rag", "llm",
            "atom_extraction", "cross_link", "vault_writes", "total_duration_ms"} <= keys


def test_record_stt_populates_fields() -> None:
    b = TraceBuilder(session_id="sid-1")
    b.record_stt(engine="mlx-whisper", model="m", text="안녕", lang="ko",
                 duration_ms=320.4, input_bytes=1024)
    out = b.finalize()
    assert out["stt"]["text"] == "안녕"
    assert out["stt"]["duration_ms"] == 320.4
    assert out["stt"]["lang"] == "ko"


def test_record_router_three_stages() -> None:
    b = TraceBuilder(session_id="sid")
    b.record_router(
        stage1=None,
        stage2={"category": "rag", "confidence": 0.78},
        stage3={"chosen": "qwen2.5:14b", "score": 8.4},
        decided_at_stage=3,
    )
    out = b.finalize()
    assert out["router"]["decided_at_stage"] == 3
    assert out["router"]["stage3_scorer"]["chosen"] == "qwen2.5:14b"
    assert out["router"]["stage1_rule"] is None
    assert out["router"]["stage2_classifier"]["confidence"] == 0.78


def test_record_vault_write_appends() -> None:
    b = TraceBuilder(session_id="sid")
    b.record_vault_write("atoms/a.md")
    b.record_vault_write("atoms/b.md")
    out = b.finalize()
    assert out["vault_writes"] == ["atoms/a.md", "atoms/b.md"]


def test_save_to_vault_writes_json(tmp_vault: Path) -> None:
    b = TraceBuilder(session_id="sid-x")
    b.record_stt(engine="mlx", model="m", text="hi", lang="en",
                 duration_ms=10.0, input_bytes=0)
    out_path = b.save_to_vault(tmp_vault)
    assert out_path == tmp_vault / "assistant" / "_traces" / "sid-x.json"
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["session_id"] == "sid-x"
    assert data["stt"]["text"] == "hi"


def test_total_duration_is_nonnegative_after_finalize() -> None:
    b = TraceBuilder(session_id="sid")
    out = b.finalize()
    assert out["total_duration_ms"] >= 0
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/trace/test_builder.py -v`
Expected: ImportError on `backend.trace.builder`.

- [ ] **Step 3: Implement `backend/trace/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/trace/builder.py`**

```python
"""Per-request decision trace accumulator (deep-dive §5)."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.vault.fs_utils import atomic_write_text


@dataclass
class Trace:
    session_id: str = ""
    stt: dict[str, Any] = field(default_factory=dict)
    router: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    rag: dict[str, Any] = field(default_factory=dict)
    llm: dict[str, Any] = field(default_factory=dict)
    atom_extraction: dict[str, Any] = field(default_factory=dict)
    cross_link: dict[str, Any] = field(default_factory=dict)
    vault_writes: list[str] = field(default_factory=list)
    total_duration_ms: float = 0.0


class TraceBuilder:
    """Mutable accumulator for one /chat request's trace. Not thread-safe."""

    def __init__(self, session_id: str) -> None:
        self.trace = Trace(session_id=session_id)
        self._start = time.monotonic()

    # Stage recorders ────────────────────────────────────────────────────
    def record_stt(self, *, engine: str, model: str, text: str, lang: str,
                   duration_ms: float, input_bytes: int) -> None:
        self.trace.stt = {
            "engine": engine, "model": model, "text": text, "lang": lang,
            "duration_ms": round(duration_ms, 1), "input_bytes": input_bytes,
        }

    def record_router(self, *, stage1: dict | None, stage2: dict | None,
                      stage3: dict, decided_at_stage: int) -> None:
        self.trace.router = {
            "stage1_rule": stage1,
            "stage2_classifier": stage2,
            "stage3_scorer": stage3,
            "decided_at_stage": decided_at_stage,
        }

    def record_policy(self, *, offline_mode: bool, provider: str,
                      action: str, redacted_paths: list[str]) -> None:
        self.trace.policy = {
            "offline_mode": offline_mode, "provider": provider,
            "action": action, "redacted_paths": redacted_paths,
        }

    def record_rag(self, *, query_embedding_ms: float, search_ms: float,
                   hits: list[dict], passed_threshold: int, used_in_prompt: int) -> None:
        self.trace.rag = {
            "query_embedding_ms": round(query_embedding_ms, 1),
            "search_ms": round(search_ms, 1),
            "hits": hits,
            "passed_threshold": passed_threshold,
            "used_in_prompt": used_in_prompt,
        }

    def record_llm(self, *, provider: str, model: str, input_tokens: int,
                   output_tokens: int, duration_ms: float, stop_reason: str = "") -> None:
        self.trace.llm = {
            "provider": provider, "model": model,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "duration_ms": round(duration_ms, 1), "stop_reason": stop_reason,
        }

    def record_atom_extraction(self, *, model: str, extracted: dict | None,
                               skipped: bool) -> None:
        self.trace.atom_extraction = {
            "model": model, "extracted": extracted, "skipped": skipped,
        }

    def record_cross_link(self, *, candidates_count: int, passed_threshold: int,
                          llm_picked: int, linked: list[str]) -> None:
        self.trace.cross_link = {
            "candidates_count": candidates_count,
            "passed_threshold": passed_threshold,
            "llm_picked": llm_picked,
            "linked": linked,
        }

    def record_vault_write(self, path: str) -> None:
        self.trace.vault_writes.append(path)

    # Finalization ───────────────────────────────────────────────────────
    def finalize(self) -> dict[str, Any]:
        self.trace.total_duration_ms = round((time.monotonic() - self._start) * 1000, 1)
        return asdict(self.trace)

    def save_to_vault(self, vault_path: Path, assistant_subdir: str = "assistant") -> Path:
        target = vault_path / assistant_subdir / "_traces" / f"{self.trace.session_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, json.dumps(self.finalize(), ensure_ascii=False, indent=2))
        return target
```

- [ ] **Step 5: Create `tests/trace/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/trace/test_builder.py -v`
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/trace/__init__.py backend/trace/builder.py tests/trace/__init__.py tests/trace/test_builder.py
git commit -m "Add TraceBuilder (7-stage decision trace + _traces/<sid>.json persist)"
```

---

## Task 17: Session manager

**Files:**
- Create: `backend/session/__init__.py`
- Create: `backend/session/manager.py`
- Create: `tests/session/__init__.py`
- Create: `tests/session/test_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/session/test_manager.py
from __future__ import annotations

from pathlib import Path

import pytest
from freezegun import freeze_time

from backend.session.manager import SessionManager


@freeze_time("2026-05-18 14:23:00")
def test_start_session_creates_session_file(tmp_vault: Path) -> None:
    mgr = SessionManager(vault_path=tmp_vault, assistant_subdir="assistant")
    sid = mgr.start_session()
    session_path = tmp_vault / "assistant" / "sessions" / f"{sid}.md"
    assert session_path.exists()
    assert "## Turns" in session_path.read_text(encoding="utf-8")


@freeze_time("2026-05-18 14:23:00")
def test_log_turn_appends_to_session_and_daily(tmp_vault: Path) -> None:
    mgr = SessionManager(vault_path=tmp_vault, assistant_subdir="assistant")
    sid = mgr.start_session()
    mgr.log_turn(sid, user_text="안녕", assistant_text="안녕하세요", atom_slug=None)
    session_text = (tmp_vault / "assistant" / "sessions" / f"{sid}.md").read_text(encoding="utf-8")
    assert "안녕하세요" in session_text
    daily = (tmp_vault / "assistant" / "daily" / "2026-05-18.md")
    assert daily.exists()


@freeze_time("2026-05-18 14:23:00")
def test_daily_embeds_atom_when_logged(tmp_vault: Path) -> None:
    mgr = SessionManager(vault_path=tmp_vault, assistant_subdir="assistant")
    sid = mgr.start_session()
    mgr.log_turn(sid, user_text="q", assistant_text="a", atom_slug="foo-atom")
    daily = (tmp_vault / "assistant" / "daily" / "2026-05-18.md").read_text(encoding="utf-8")
    assert "![[foo-atom]]" in daily
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/session/test_manager.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/session/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/session/manager.py`**

```python
"""Session manager: writes sessions/<id>.md raw transcript + daily/<date>.md embeds."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from backend.vault.fs_utils import atomic_write_text


def _ts_id() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S") + "-" + uuid.uuid4().hex[:4]


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


class SessionManager:
    def __init__(self, vault_path: Path, assistant_subdir: str = "assistant") -> None:
        self.vault = Path(vault_path)
        self.subdir = assistant_subdir

    @property
    def sessions_dir(self) -> Path:
        return self.vault / self.subdir / "sessions"

    @property
    def daily_dir(self) -> Path:
        return self.vault / self.subdir / "daily"

    def start_session(self) -> str:
        sid = _ts_id()
        path = self.sessions_dir / f"{sid}.md"
        header = (
            f"---\ntype: session\nid: {sid}\nstarted: {datetime.now().isoformat(timespec='seconds')}\n---\n\n"
            f"# Session {sid}\n\n## Turns\n"
        )
        atomic_write_text(path, header)
        return sid

    def log_turn(self, sid: str, *, user_text: str, assistant_text: str, atom_slug: str | None) -> None:
        # Append to session
        session_path = self.sessions_dir / f"{sid}.md"
        text = session_path.read_text(encoding="utf-8")
        ts = datetime.now().isoformat(timespec="seconds")
        turn = (
            f"\n### {ts}\n\n"
            f"**User:** {user_text}\n\n"
            f"**Assistant:** {assistant_text}\n"
        )
        if atom_slug:
            turn += f"\n→ atom: [[{atom_slug}]]\n"
        atomic_write_text(session_path, text + turn)

        # Update daily
        daily_path = self.daily_dir / f"{_today()}.md"
        if daily_path.exists():
            daily_text = daily_path.read_text(encoding="utf-8")
        else:
            daily_text = (
                f"---\ntype: daily\ndate: {_today()}\n---\n\n# {_today()}\n\n## Atoms\n\n## Sessions\n"
            )
        if atom_slug and f"![[{atom_slug}]]" not in daily_text:
            daily_text = daily_text.replace("## Atoms\n", f"## Atoms\n- ![[{atom_slug}]]\n", 1)
        if f"[[{sid}]]" not in daily_text:
            daily_text = daily_text.rstrip() + f"\n- [[{sid}]]\n"
        atomic_write_text(daily_path, daily_text)
```

- [ ] **Step 5: Create `tests/session/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/session/test_manager.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/session/__init__.py backend/session/manager.py tests/session/__init__.py tests/session/test_manager.py
git commit -m "Add SessionManager (sessions/<id>.md + daily/<date>.md)"
```

---

## Task 18: STT (mlx-whisper) wrapper

**Files:**
- Create: `backend/stt/__init__.py`
- Create: `backend/stt/whisper_mlx.py`
- Create: `tests/stt/__init__.py`
- Create: `tests/stt/test_whisper_mlx.py`

mlx-whisper is heavy to load — test will mock the transcribe call.

- [ ] **Step 1: Write failing tests**

```python
# tests/stt/test_whisper_mlx.py
from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.stt.whisper_mlx import TranscriptResult, WhisperSTT


def test_transcribe_returns_text_and_lang(tmp_path) -> None:
    audio = tmp_path / "x.wav"
    audio.write_bytes(b"fake")
    with patch("backend.stt.whisper_mlx.mlx_transcribe", return_value={"text": "안녕", "language": "ko"}):
        stt = WhisperSTT(model="mlx-community/whisper-large-v3-mlx")
        out = stt.transcribe_file(audio)
    assert isinstance(out, TranscriptResult)
    assert out.text == "안녕"
    assert out.lang == "ko"


def test_transcribe_handles_empty_audio(tmp_path) -> None:
    audio = tmp_path / "x.wav"
    audio.write_bytes(b"")
    with patch("backend.stt.whisper_mlx.mlx_transcribe", return_value={"text": "", "language": "en"}):
        stt = WhisperSTT(model="mlx-community/whisper-large-v3-mlx")
        out = stt.transcribe_file(audio)
    assert out.text == ""
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/stt/test_whisper_mlx.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `backend/stt/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/stt/whisper_mlx.py`**

```python
"""mlx-whisper wrapper. Loaded lazily — the model is heavy."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Imported at module level so tests can monkeypatch it.
try:  # pragma: no cover - import-time fallback for environments without mlx
    from mlx_whisper import transcribe as mlx_transcribe
except Exception:  # pragma: no cover
    def mlx_transcribe(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("mlx-whisper not available in this environment")


@dataclass
class TranscriptResult:
    text: str
    lang: str


class WhisperSTT:
    def __init__(self, model: str) -> None:
        self.model = model

    def transcribe_file(self, audio_path: Path) -> TranscriptResult:
        result = mlx_transcribe(str(audio_path), path_or_hf_repo=self.model)
        return TranscriptResult(text=result.get("text", "").strip(), lang=result.get("language", "en"))

    def transcribe_bytes(self, audio_bytes: bytes, suffix: str = ".wav") -> TranscriptResult:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            tmp = Path(f.name)
        try:
            return self.transcribe_file(tmp)
        finally:
            tmp.unlink(missing_ok=True)
```

- [ ] **Step 5: Create `tests/stt/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Run tests, verify pass**

Run: `pytest tests/stt/test_whisper_mlx.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/stt/__init__.py backend/stt/whisper_mlx.py tests/stt/__init__.py tests/stt/test_whisper_mlx.py
git commit -m "Add WhisperSTT wrapper around mlx-whisper"
```

---

## Task 19: FastAPI app skeleton + auth middleware + /healthz

**Files:**
- Modify: `backend/main.py`
- Create: `backend/api/__init__.py`
- Create: `backend/api/auth.py`
- Create: `backend/api/health.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_health.py`
- Create: `tests/api/test_auth.py`

- [ ] **Step 1: Write failing health + auth tests**

```python
# tests/api/test_health.py
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import build_app


def test_healthz_returns_ok() -> None:
    client = TestClient(build_app())
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

```python
# tests/api/test_auth.py
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import build_app


def test_protected_route_rejects_missing_token() -> None:
    app = build_app()
    client = TestClient(app)
    r = client.post("/chat", json={"text": "hi"})
    assert r.status_code == 401


def test_protected_route_rejects_wrong_token() -> None:
    client = TestClient(build_app())
    r = client.post("/chat", json={"text": "hi"}, headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/api/ -v`
Expected: ImportError on `build_app`.

- [ ] **Step 3: Implement `backend/api/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/api/auth.py`**

```python
"""Bearer token middleware — single user."""
from __future__ import annotations

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware


PUBLIC_PATHS = {"/healthz"}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != self._token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad token")
        return await call_next(request)
```

- [ ] **Step 5: Implement `backend/api/health.py`**

```python
"""Health endpoint."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Implement `backend/main.py`**

```python
"""FastAPI entry — wires config, auth, routes."""
from __future__ import annotations

from fastapi import APIRouter, FastAPI

from backend.api.auth import BearerAuthMiddleware
from backend.api.health import router as health_router
from backend.config import get_settings


def build_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Little Lion", version="0.0.1")
    app.add_middleware(BearerAuthMiddleware, token=settings.auth_token)
    app.include_router(health_router)
    # `/chat` placeholder route so unauthenticated tests see 401 (real impl in Task 20)
    chat_stub = APIRouter()

    @chat_stub.post("/chat")
    async def _chat_stub() -> dict:
        return {"detail": "not implemented yet"}

    app.include_router(chat_stub)
    return app


app = build_app()


def main() -> None:
    import uvicorn
    s = get_settings()
    uvicorn.run("backend.main:app", host=s.backend_host, port=s.backend_port, log_level=s.log_level.lower())


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Create `tests/api/__init__.py`** (empty)

```python
```

- [ ] **Step 8: Run tests, verify pass**

Run: `pytest tests/api/ -v`
Expected: 3 passed (healthz + 2 auth).

- [ ] **Step 9: Commit**

```bash
git add backend/main.py backend/api/__init__.py backend/api/auth.py backend/api/health.py \
        tests/api/__init__.py tests/api/test_health.py tests/api/test_auth.py
git commit -m "Add FastAPI app skeleton + bearer auth middleware + /healthz"
```

---

## Task 20: POST /chat endpoint (end-to-end pipeline)

**Files:**
- Create: `backend/api/chat.py`
- Create: `backend/services/__init__.py`
- Create: `backend/services/pipeline.py`
- Modify: `backend/main.py:1-40`
- Create: `tests/api/test_chat.py`

- [ ] **Step 1: Write failing chat test**

```python
# tests/api/test_chat.py
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import build_app


async def _stream_text(s: str) -> AsyncIterator[str]:
    for ch in s:
        yield ch


def test_chat_end_to_end_writes_atom(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The full /chat pipeline must run with mocked LLM and produce an atom in the vault."""
    monkeypatch.setenv("OFFLINE_MODE", "false")    # let cloud provider through (mocked)
    from backend.config import reset_settings_cache
    from backend.api.chat import reset_pipeline_for_tests
    reset_settings_cache()
    reset_pipeline_for_tests()

    async def fake_chat(**kwargs):
        msgs = kwargs.get("messages", [])
        sys_text = msgs[0]["content"] if msgs else ""
        if "atom 추출기" in sys_text:
            return _stream_text('{"title": "Test Atom", "body": "기록할 가치 있음.", "tags": ["test"]}')
        if "의미적으로 연결" in sys_text:
            return _stream_text("[]")
        if "query classifier" in sys_text:
            return _stream_text('{"category": "default", "need_rag": false, "need_web": false, "confidence": 0.8}')
        return _stream_text("이것은 모의 답변입니다.")

    async def fake_embed(model: str, text: str) -> list[float]:
        return [0.0, 0.0, 0.0, 0.0]

    with patch("backend.services.pipeline.LLMClient") as mock_llm, \
         patch("backend.services.pipeline.OllamaClient") as mock_oll:
        mock_llm.return_value.chat.side_effect = fake_chat
        mock_oll.return_value.embed.side_effect = fake_embed
        client = TestClient(build_app())
        r = client.post(
            "/chat",
            json={"text": "테스트 질문을 좀 길게 적어서 라우팅이 명확히 분류기로 떨어지도록"},
            headers={"Authorization": "Bearer test-token"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "answer" in data
    assert data.get("atom_slug") == "test-atom"
    atom_path = tmp_vault / "assistant" / "atoms" / "test-atom.md"
    assert atom_path.exists()
    # Trace must be present per deep-dive §5
    assert "trace" in data
    assert data["trace"]["session_id"] == data["session_id"]
    assert data["trace"]["router"]["decided_at_stage"] in (1, 3)
    trace_path = tmp_vault / "assistant" / "_traces" / f"{data['session_id']}.json"
    assert trace_path.exists()
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/api/test_chat.py -v`
Expected: 404 (no /chat) or AttributeError on import.

- [ ] **Step 3: Implement `backend/services/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Implement `backend/services/pipeline.py`**

```python
"""End-to-end /chat pipeline composition with full decision trace (deep-dive §5)."""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from backend.config import Settings
from backend.llm.ollama import OllamaClient
from backend.llm.router_client import LLMClient, ProviderKey
from backend.pipeline.atomize import extract_atom
from backend.pipeline.cross_link import pick_related
from backend.policy.gate import PolicyGate, RAGItem
from backend.rag.search import HybridSearcher
from backend.rag.store import LanceStore
from backend.router.classifier import OllamaClassifier
from backend.router.orchestrator import Router
from backend.session.manager import SessionManager
from backend.trace.builder import TraceBuilder
from backend.vault.linker import link_bidirectional
from backend.vault.writer import VaultWriter


@dataclass
class ChatResult:
    answer: str
    route_reason: str
    atom_slug: str | None
    session_id: str
    trace: dict[str, Any] = field(default_factory=dict)


async def _drain(stream: AsyncIterator[str]) -> str:
    parts: list[str] = []
    async for tok in stream:
        parts.append(tok)
    return "".join(parts)


class ChatPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = LLMClient(
            anthropic_key=settings.anthropic_api_key,
            google_key=settings.google_api_key,
            ollama_host=settings.ollama_host,
        )
        self.ollama = OllamaClient(host=settings.ollama_host)
        self.writer = VaultWriter(settings.vault_path, settings.assistant_subdir)
        self.session = SessionManager(settings.vault_path, settings.assistant_subdir)
        self.policy = PolicyGate(offline_mode=settings.offline_mode)

        classifier = OllamaClassifier(
            chat=lambda **kw: self.llm.chat(provider=ProviderKey.OLLAMA, model="qwen2.5:0.5b", **kw),
            model="qwen2.5:0.5b",
        )
        self.router = Router(classifier=classifier)

        self.store = LanceStore(db_path=settings.rag_db_path, vector_dim=768)

    async def handle(self, *, user_text: str) -> ChatResult:
        sid = self.session.start_session()
        trace = TraceBuilder(session_id=sid)

        # ── Routing ───────────────────────────────────────────────────────────
        decision = await self.router.route(text=user_text, input_tokens=len(user_text.split()))
        stage1_match = "stage1" in decision.reason
        stage3_payload = {
            "chosen": decision.model,
            "provider": decision.provider,
            "score": decision.score,
            "candidates": decision.candidate_scores or {},
            "reason": decision.reason,
        }
        trace.record_router(
            stage1=({"category": decision.reason} if stage1_match else None),
            stage2=(None if stage1_match else {"reason": decision.reason}),
            stage3=stage3_payload,
            decided_at_stage=(1 if stage1_match else 3),
        )

        # ── RAG ───────────────────────────────────────────────────────────────
        rag_items: list[RAGItem] = []
        rag_hits_meta: list[dict] = []
        embed_ms = 0.0
        search_ms = 0.0
        if decision.need_rag:
            try:
                t0 = time.monotonic()
                searcher = HybridSearcher(
                    store=self.store, embed=self.ollama.embed, embed_model="nomic-embed-text",
                    documents=[],
                )
                hits = await searcher.search(user_text, k=self.settings.rag_top_k)
                search_ms = (time.monotonic() - t0) * 1000
                for h in hits:
                    rag_items.append(RAGItem(path=h.path, title=h.path, body=h.text, tags=[], local_only=False))
                    rag_hits_meta.append({"path": h.path, "score": round(h.score, 3)})
            except Exception:
                rag_items = []
        trace.record_rag(
            query_embedding_ms=embed_ms, search_ms=search_ms,
            hits=rag_hits_meta, passed_threshold=len(rag_items),
            used_in_prompt=len([r for r in rag_items if r.body]),
        )

        # ── Policy ────────────────────────────────────────────────────────────
        gate = self.policy.check(provider=decision.provider, rag=rag_items)
        trace.record_policy(
            offline_mode=self.settings.offline_mode,
            provider=decision.provider,
            action=gate.action,
            redacted_paths=[r.path for r in rag_items if r.local_only],
        )
        if gate.action == "deny":
            self.session.log_turn(sid, user_text=user_text,
                                  assistant_text=f"(거부됨: {gate.reason})", atom_slug=None)
            trace_path = trace.save_to_vault(self.settings.vault_path, self.settings.assistant_subdir)
            trace.record_vault_write(str(trace_path.relative_to(self.settings.vault_path)))
            return ChatResult(answer=f"(거부됨: {gate.reason})", route_reason=decision.reason,
                              atom_slug=None, session_id=sid, trace=trace.finalize())

        # ── LLM call ──────────────────────────────────────────────────────────
        context_text = "\n\n".join(f"- {r.title}: {r.body}" for r in gate.rag if r.body)
        messages = [
            {"role": "system",
             "content": decision.system_prompt + (f"\n\n참조:\n{context_text}" if context_text else "")},
            {"role": "user", "content": user_text},
        ]
        provider_key = ProviderKey(decision.provider)
        t0 = time.monotonic()
        answer = await _drain(self.llm.chat(provider=provider_key, model=decision.model, messages=messages))
        llm_ms = (time.monotonic() - t0) * 1000
        trace.record_llm(
            provider=decision.provider, model=decision.model,
            input_tokens=len(user_text.split()) + sum(len(r.body.split()) for r in gate.rag),
            output_tokens=len(answer.split()),
            duration_ms=llm_ms,
        )

        # ── Atom extraction + cross-link ─────────────────────────────────────
        atom = await extract_atom(
            question=user_text, answer=answer,
            chat=lambda **kw: self.llm.chat(provider=ProviderKey.OLLAMA, model="qwen2.5:14b", **kw),
        )
        trace.record_atom_extraction(
            model="qwen2.5:14b",
            extracted=({"title": atom.title, "tags": atom.tags} if atom else None),
            skipped=(atom is None),
        )
        atom_slug: str | None = None
        linked: list[str] = []
        candidates_count = 0
        if atom is not None:
            w = self.writer.write_atom(title=atom.title, body=atom.body, tags=atom.tags,
                                        source_session=f"sessions/{sid}.md")
            atom_slug = w.slug
            trace.record_vault_write(str(w.path.relative_to(self.settings.vault_path)))
            candidates = [(r.title, r.body[:200], 0.9) for r in gate.rag if r.body]
            candidates_count = len(candidates)
            related = await pick_related(
                atom_title=atom.title, atom_body=atom.body,
                candidates=candidates,
                threshold=self.settings.rag_cross_link_threshold,
                k_final=self.settings.rag_cross_link_k,
                chat=lambda **kw: self.llm.chat(provider=ProviderKey.OLLAMA, model="qwen2.5:14b", **kw),
            )
            for slug in related:
                other = self.writer.atoms_dir / f"{slug}.md"
                if other.exists():
                    link_bidirectional(w.path, other)
                    linked.append(slug)
        trace.record_cross_link(
            candidates_count=candidates_count,
            passed_threshold=candidates_count,
            llm_picked=len(linked),
            linked=linked,
        )

        # ── Session + persist trace ──────────────────────────────────────────
        self.session.log_turn(sid, user_text=user_text, assistant_text=answer, atom_slug=atom_slug)
        trace_path = trace.save_to_vault(self.settings.vault_path, self.settings.assistant_subdir)
        trace.record_vault_write(str(trace_path.relative_to(self.settings.vault_path)))

        return ChatResult(
            answer=answer, route_reason=decision.reason, atom_slug=atom_slug,
            session_id=sid, trace=trace.finalize(),
        )
```

- [ ] **Step 5: Implement `backend/api/chat.py`**

```python
"""POST /chat endpoint."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.services.pipeline import ChatPipeline

router = APIRouter()
_pipeline: ChatPipeline | None = None


def _get_pipeline() -> ChatPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ChatPipeline(get_settings())
    return _pipeline


class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    answer: str
    route_reason: str
    atom_slug: str | None
    session_id: str
    trace: dict   # deep-dive §5 — 7-stage decision trace


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    pipeline = _get_pipeline()
    result = await pipeline.handle(user_text=req.text)
    return ChatResponse(
        answer=result.answer,
        route_reason=result.route_reason,
        atom_slug=result.atom_slug,
        session_id=result.session_id,
        trace=result.trace,
    )


def reset_pipeline_for_tests() -> None:
    global _pipeline
    _pipeline = None
```

- [ ] **Step 6: Update `backend/main.py`** to use the real chat router

Replace the stub block in `backend/main.py`. The full new file:

```python
"""FastAPI entry — wires config, auth, routes."""
from __future__ import annotations

from fastapi import FastAPI

from backend.api.auth import BearerAuthMiddleware
from backend.api.chat import router as chat_router
from backend.api.health import router as health_router
from backend.config import get_settings


def build_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Little Lion", version="0.0.1")
    app.add_middleware(BearerAuthMiddleware, token=settings.auth_token)
    app.include_router(health_router)
    app.include_router(chat_router)
    return app


app = build_app()


def main() -> None:
    import uvicorn
    s = get_settings()
    uvicorn.run("backend.main:app", host=s.backend_host, port=s.backend_port, log_level=s.log_level.lower())


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Reset pipeline singleton between tests**

Add to `tests/conftest.py` `_isolate_env` (after the cache reset):

```python
    from backend.api.chat import reset_pipeline_for_tests
    reset_pipeline_for_tests()
```

- [ ] **Step 8: Run chat test, verify pass**

Run: `pytest tests/api/test_chat.py -v`
Expected: 1 passed. The atom file `test-atom.md` should exist in `tmp_vault/assistant/atoms/`.

- [ ] **Step 9: Run the full suite**

Run: `pytest -v`
Expected: all tests pass (≈ 40 tests across all modules).

- [ ] **Step 10: Commit**

```bash
git add backend/api/chat.py backend/services/__init__.py backend/services/pipeline.py \
        backend/main.py tests/api/test_chat.py tests/conftest.py
git commit -m "Add POST /chat end-to-end pipeline (route → RAG → policy → LLM → atom)"
```

---

## Task 21: WebSocket /ws/voice endpoint

**Files:**
- Create: `backend/api/voice.py`
- Modify: `backend/main.py`
- Create: `tests/api/test_voice_ws.py`

- [ ] **Step 1: Write failing WS test**

```python
# tests/api/test_voice_ws.py
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import build_app
from backend.stt.whisper_mlx import TranscriptResult


async def _stream(s: str) -> AsyncIterator[str]:
    for ch in s:
        yield ch


def test_voice_ws_runs_stt_then_chat(tmp_vault: Path) -> None:
    with patch("backend.api.voice.WhisperSTT") as mock_stt_cls, \
         patch("backend.services.pipeline.LLMClient") as mock_llm, \
         patch("backend.services.pipeline.OllamaClient") as mock_oll:
        mock_stt_cls.return_value.transcribe_bytes.return_value = TranscriptResult(text="안녕", lang="ko")
        mock_llm.return_value.chat.return_value = _stream("안녕하세요")
        mock_oll.return_value.embed.return_value = [0.0, 0.0, 0.0, 0.0]

        client = TestClient(build_app())
        with client.websocket_connect("/ws/voice?token=test-token") as ws:
            ws.send_bytes(b"fake-audio")
            ws.send_text("__END__")
            data = ws.receive_json()
        assert "answer" in data
        assert "안녕" in data["answer"] or "안녕하세요" in data["answer"]
```

- [ ] **Step 2: Run to fail**

Run: `pytest tests/api/test_voice_ws.py -v`
Expected: 404 (route not yet wired).

- [ ] **Step 3: Implement `backend/api/voice.py`**

```python
"""WebSocket /ws/voice — accumulates audio frames, transcribes, runs /chat pipeline."""
from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from backend.api.chat import _get_pipeline
from backend.config import get_settings
from backend.stt.whisper_mlx import WhisperSTT

router = APIRouter()


@router.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket, token: str = Query(default="")) -> None:
    settings = get_settings()
    if token != settings.auth_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    audio_chunks: list[bytes] = []
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                return
            if "bytes" in msg and msg["bytes"] is not None:
                audio_chunks.append(msg["bytes"])
            elif "text" in msg and msg["text"] == "__END__":
                break
    except WebSocketDisconnect:
        return

    audio = b"".join(audio_chunks)
    stt = WhisperSTT(model=settings.whisper_model)
    transcript = stt.transcribe_bytes(audio)
    pipeline = _get_pipeline()
    result = await pipeline.handle(user_text=transcript.text)
    await websocket.send_json({
        "transcript": transcript.text,
        "lang": transcript.lang,
        "answer": result.answer,
        "atom_slug": result.atom_slug,
        "route_reason": result.route_reason,
        "session_id": result.session_id,
    })
    await websocket.close()
```

- [ ] **Step 4: Wire `voice_ws` in `backend/main.py`**

Edit `backend/main.py:1-30` to add the import and include router. The new `build_app`:

```python
from backend.api.voice import router as voice_router
# ...
def build_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Little Lion", version="0.0.1")
    app.add_middleware(BearerAuthMiddleware, token=settings.auth_token)
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(voice_router)
    return app
```

(The WS route does its own token check via query string, so it stays out of the bearer middleware — middleware sees no `Authorization` header and would 401 an HTTP-style request, but WebSocket upgrade requests bypass `dispatch` when the path matches a registered `@app.websocket`. If the middleware still rejects WS upgrades in your FastAPI version, add `/ws/voice` to `PUBLIC_PATHS` in `backend/api/auth.py`.)

- [ ] **Step 5: Run WS test, verify pass**

Run: `pytest tests/api/test_voice_ws.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/api/voice.py backend/main.py tests/api/test_voice_ws.py
git commit -m "Add WebSocket /ws/voice (STT → pipeline → JSON response)"
```

---

## Task 22: Integration smoke test (end-to-end with real-ish stack, optional ollama)

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_smoke_pipeline.py`
- Create: `tests/integration/conftest.py`

This test verifies the **Phase 1a gate**: text in → vault file out + at least one cross-link if a matching atom exists.

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_smoke_pipeline.py
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import build_app


async def _stream(s: str) -> AsyncIterator[str]:
    for ch in s:
        yield ch


def test_smoke_chat_writes_atom_and_session(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFLINE_MODE", "false")
    from backend.api.chat import reset_pipeline_for_tests
    from backend.config import reset_settings_cache
    reset_settings_cache()
    reset_pipeline_for_tests()

    # Pre-populate vault with a candidate atom so cross-linking has a target
    candidate = tmp_vault / "assistant" / "atoms" / "litellm-router-pattern.md"
    candidate.write_text(
        "---\ntype: atom\nstate: published\nlinked-count: 0\n"
        "assistant-touched-at: 2026-05-01T00:00\n---\n\n# LiteLLM Router Pattern\n\nbody\n\n## Related\n",
        encoding="utf-8",
    )

    async def fake_llm_chat(**kwargs):
        sys = kwargs.get("messages", [{}])[0].get("content", "")
        if "atom 추출기" in sys:
            return _stream(
                '{"title": "Router Cascade", "body": "rules → classifier → default.", "tags": ["router"]}'
            )
        if "의미적으로 연결" in sys:
            return _stream('["litellm-router-pattern"]')
        if "query classifier" in sys:
            return _stream('{"category": "rag", "need_rag": true, "need_web": false, "confidence": 0.8}')
        return _stream("라우터는 3단 캐스케이드.")

    async def fake_embed(model: str, text: str) -> list[float]:
        return [0.0] * 4

    with patch("backend.services.pipeline.LLMClient") as mock_llm, \
         patch("backend.services.pipeline.OllamaClient") as mock_oll:
        mock_llm.return_value.chat.side_effect = fake_llm_chat
        mock_oll.return_value.embed.side_effect = fake_embed

        client = TestClient(build_app())
        r = client.post(
            "/chat",
            json={"text": "내 vault에서 라우터 구조 모아줘"},   # "vault" rule → category=rag → ollama
            headers={"Authorization": "Bearer test-token"},
        )

    assert r.status_code == 200, r.text
    data = r.json()
    new_atom = tmp_vault / "assistant" / "atoms" / "router-cascade.md"
    assert new_atom.exists()
    new_text = new_atom.read_text(encoding="utf-8")
    assert "[[litellm-router-pattern]]" in new_text  # forward link
    assert "state: linked" in new_text               # promoted by linker (Task 6)

    target_text = candidate.read_text(encoding="utf-8")
    assert "[[router-cascade]]" in target_text       # backward link
    assert "state: linked" in target_text            # candidate also promoted

    session_file = next((tmp_vault / "assistant" / "sessions").glob("*.md"))
    assert (
        "Router Cascade" in session_file.read_text(encoding="utf-8")
        or data["atom_slug"] == "router-cascade"
    )

    # Trace persisted (deep-dive §5)
    assert "trace" in data
    assert data["trace"]["router"]["stage3_scorer"]["chosen"]
    assert data["trace"]["policy"]["action"] == "allow"
    trace_path = tmp_vault / "assistant" / "_traces" / f"{data['session_id']}.json"
    assert trace_path.exists()
    import json as _json
    disk_trace = _json.loads(trace_path.read_text(encoding="utf-8"))
    assert disk_trace["session_id"] == data["session_id"]
    assert "router-cascade.md" in " ".join(disk_trace["vault_writes"])
```

- [ ] **Step 2: Create `tests/integration/__init__.py`** + minimal `tests/integration/conftest.py`

```python
# tests/integration/__init__.py
```

```python
# tests/integration/conftest.py
# Re-exports root conftest fixtures so pytest discovers them in this subtree.
from tests.conftest import *  # noqa: F401,F403
```

- [ ] **Step 3: Run integration test, verify pass**

Run: `pytest tests/integration/ -v`
Expected: 1 passed. Inspect tmp output if curious.

- [ ] **Step 4: Run full suite once more**

Run: `pytest -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/__init__.py tests/integration/conftest.py tests/integration/test_smoke_pipeline.py
git commit -m "Add Phase 1a smoke test: /chat → atom + bidirectional cross-link"
```

---

## Task 23: Dev runner script + README quickstart

**Files:**
- Create: `scripts/run_dev.sh`
- Create: `scripts/index_vault.py`
- Modify: `README.md`

- [ ] **Step 1: Create `scripts/run_dev.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo ".env not found — copy .env.example and fill in keys."
  exit 1
fi

# Ensure Ollama is reachable (best-effort warning, do not exit).
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "WARN: Ollama not responding at http://127.0.0.1:11434 — start it with: ollama serve"
fi

exec uvicorn backend.main:app \
  --host 127.0.0.1 \
  --port 8765 \
  --reload \
  --log-level info
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x scripts/run_dev.sh`

- [ ] **Step 3: Create `scripts/index_vault.py`**

```python
"""One-shot initial vault embedding. Run after `ollama pull nomic-embed-text`."""
from __future__ import annotations

import asyncio
from pathlib import Path

from backend.config import get_settings
from backend.llm.ollama import OllamaClient
from backend.rag.indexer import Indexer
from backend.rag.store import LanceStore


async def main() -> None:
    s = get_settings()
    ollama = OllamaClient(host=s.ollama_host)
    # Discover embedding dim once
    probe = await ollama.embed("nomic-embed-text", "probe")
    store = LanceStore(db_path=s.rag_db_path, vector_dim=len(probe))
    indexer = Indexer(store=store, embed=ollama.embed, embed_model="nomic-embed-text")
    n = await indexer.index_directory(s.vault_path)
    print(f"Indexed {n} chunks from {s.vault_path}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Update `README.md` with end-to-end quickstart**

```markdown
# Little Lion — Personal AI Assistant (Backend Phase 1a)

See `docs/specs/2026-05-18-little-lion-personal-assistant-design.md` for the full design.

## Prerequisites

```bash
brew install ollama
ollama serve &  # leave running
ollama pull qwen2.5:14b
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:0.5b
ollama pull nomic-embed-text
```

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in ANTHROPIC_API_KEY, GOOGLE_API_KEY, BACKEND_AUTH_TOKEN
```

## Initial index (one-shot)

```bash
python scripts/index_vault.py
```

## Run

```bash
./scripts/run_dev.sh
# → http://127.0.0.1:8765
```

## Test

```bash
pytest -q
curl -X POST http://127.0.0.1:8765/chat \
  -H "Authorization: Bearer $BACKEND_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"내 vault에서 라우터 관련 내용 정리해줘"}'
```

The response includes `atom_slug`. Open the Obsidian vault — a new note in `assistant/atoms/` should exist and the graph view should show a new node + edges.
```

- [ ] **Step 5: Verify dev script syntax**

Run: `bash -n scripts/run_dev.sh && python -c "import ast; ast.parse(open('scripts/index_vault.py').read())"`
Expected: no output (syntax OK).

- [ ] **Step 6: Commit**

```bash
git add scripts/run_dev.sh scripts/index_vault.py README.md
git commit -m "Add dev runner + index_vault.py + README quickstart"
```

---

## Self-Review Results

**1. Spec coverage** — checked against `2026-05-18-little-lion-personal-assistant-design.md` Phase 1 list:
- FastAPI + LiteLLM router → Tasks 13, 14, 18, 19
- Ollama model pins → README in Task 23 (real `ollama pull` commands)
- mlx-whisper STT → Task 18, wired in Task 21
- LanceDB RAG + bulk index + fswatch → Tasks 8, 9, 10, 11
- Vault Writer + cross-link (0.75 threshold + LLM gate + K=5) → Tasks 5, 6, 15
- `policy` (local-only + offline mode) → Task 12
- launchd → **deferred to Plan 1c (Ops)** — explicitly noted in plan intro
- Tailscale setup → **deferred to Plan 1c (Ops)** — explicitly noted
- PWA → **deferred to Plan 1b** — explicitly noted

**2. Placeholder scan** — none. Every code block is complete; no "TBD"/"TODO" in plan instructions.

**3. Type consistency** — verified across tasks:
- `Chunk`, `SearchHit`, `HybridHit` types match between `rag/store.py`, `rag/search.py`, `rag/indexer.py`.
- `RouteDecision.provider` (str) matches `PolicyGate.check(provider=...)` Literal.
- `AtomCandidate.title/body/tags` matches `VaultWriter.write_atom(title=, body=, tags=)`.
- `ChatPipeline.handle` returns `ChatResult` with `atom_slug`, matching `ChatResponse.atom_slug`.

No outstanding issues.

---

## Execution Handoff

**Plan complete and saved to `015_little_lion/docs/specs/2026-05-18-little-lion-phase1a-backend-plan.md`. Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
