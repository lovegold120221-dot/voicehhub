"""Configuration and secrets for the EburonHub orchestrator."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Populate os.environ from a simple KEY=VALUE .env file (no quoting magic)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
_PROJECT_ENV = Path(__file__).resolve().parent.parent / ".env"
_HERMES_ENV = HERMES_HOME / ".env"
_load_dotenv(_PROJECT_ENV)   # repo-local secrets first (lower priority)
_load_dotenv(_HERMES_ENV)    # hermes secrets override


_SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"


def _load_settings_file() -> dict:
    if _SETTINGS_FILE.is_file():
        try:
            import json
            return json.loads(_SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


@dataclass
class Settings:
    # Gemini Live (Beatrice voice).
    gemini_api_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))
    voice_model: str = os.environ.get("EBURON_VOICE_MODEL", "models/gemini-3.1-flash-live-preview")
    voice_name: str = os.environ.get("EBURON_VOICE_NAME", "Aoede")
    # Reasoning model used by the event-listener/planner. Gemini text or an
    # Ollama (self-hosted/cloud) model served via the OpenAI-compatible API.
    reason_model: str = os.environ.get("EBURON_REASON_MODEL", "gemini-2.5-flash")

    # Working directory the dispatcher operates in (opencode's project root).
    # Defaults to a sandbox under the repo so opencode never edits app source.
    workspace_dir: Path = field(default_factory=lambda: Path(os.environ.get("EBURON_WORKSPACE", str(Path(__file__).resolve().parent.parent / "workspace"))))

    # Preview server host/port base; 0 picks a free port.
    preview_host: str = os.environ.get("EBURON_PREVIEW_HOST", "127.0.0.1")
    preview_port: int = int(os.environ.get("EBURON_PREVIEW_PORT", "0"))

    # Dispatch backend selection: "opencode" (default for coding) or "hermes".
    default_backend: str = os.environ.get("EBURON_DEFAULT_BACKEND", "opencode")
    # Optional explicit model for the dispatch backend (e.g. freebuff/..., opencode-go/..., ollama-cloud/...).
    dispatch_model: str | None = None

    # Ollama OpenAI-compatible endpoint (self-hosted + cloud models).
    ollama_base_url: str = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

    opencode_bin: str = os.environ.get("OPCODE_BIN", "opencode")
    hermes_bin: str = os.environ.get("HERMES_BIN", "hermes")

    def apply_persisted(self) -> "Settings":
        """Override fields from orchestrator/settings.json (written by the UI)."""
        cfg = _load_settings_file()
        if v := cfg.get("voice_model"): self.voice_model = v
        if v := cfg.get("reason_model"): self.reason_model = v
        if v := cfg.get("backend"): self.default_backend = v
        if "dispatch_model" in cfg: self.dispatch_model = cfg["dispatch_model"] or None
        if v := cfg.get("ollama_base_url"): self.ollama_base_url = v
        if v := cfg.get("workspace_dir"): self.workspace_dir = Path(v)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        return self


def settings() -> Settings:
    return Settings().apply_persisted()


def ensure_api_key(s: Settings) -> str:
    if not s.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Put it in ~/.hermes/.env or export GEMINI_API_KEY."
        )
    return s.gemini_api_key
