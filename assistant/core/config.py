"""
core/config.py — Load and validate assistant.yaml.

Keep this the single place that knows how config is structured. Other
modules should import `load_config()` and use the returned object rather
than reading YAML themselves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger(__name__)


@dataclass
class AppConfig:
    name: str
    log_level: str
    data_dir: Path


@dataclass
class ModelConfig:
    backend: str
    ollama_model: str
    ollama_host: str
    path: Path
    context_length: int
    gpu_layers: int
    threads: int


@dataclass
class GenerationConfig:
    max_tokens: int
    temperature: float
    top_p: float
    repeat_penalty: float
    stream: bool


@dataclass
class PersonaConfig:
    active: str


@dataclass
class SessionConfig:
    max_turns_in_context: int


@dataclass
class Config:
    app: AppConfig
    model: ModelConfig
    generation: GenerationConfig
    persona: PersonaConfig
    session: SessionConfig
    root_dir: Path  # directory the config file lives in, for resolving relative paths


class ConfigError(Exception):
    """Raised when assistant.yaml is missing, malformed, or fails validation."""


def load_config(path: str | Path = "config/assistant.yaml") -> Config:
    """
    Read config/assistant.yaml and return a validated Config object.

    Relative paths inside the YAML (model.path, app.data_dir) are resolved
    relative to the config file's own directory, so this works regardless
    of the current working directory the process is started from.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {path}: {e}") from e

    if not raw:
        raise ConfigError(f"Config file is empty: {path}")

    root_dir = path.resolve().parent

    try:
        app = AppConfig(
            name=raw["app"]["name"],
            log_level=raw["app"].get("log_level", "INFO"),
            data_dir=_resolve(root_dir, raw["app"]["data_dir"]),
        )
        model = ModelConfig(
            backend=raw["model"].get("backend", "llamacpp"),
            ollama_model=raw["model"].get("ollama_model", ""),
            ollama_host=raw["model"].get("ollama_host", "http://localhost:11434"),
            path=_resolve(root_dir, raw["model"]["path"]),
            context_length=int(raw["model"]["context_length"]),
            gpu_layers=int(raw["model"]["gpu_layers"]),
            threads=int(raw["model"]["threads"]),
        )
        generation = GenerationConfig(
            max_tokens=int(raw["generation"]["max_tokens"]),
            temperature=float(raw["generation"]["temperature"]),
            top_p=float(raw["generation"]["top_p"]),
            repeat_penalty=float(raw["generation"]["repeat_penalty"]),
            stream=bool(raw["generation"]["stream"]),
        )
        persona = PersonaConfig(active=raw["persona"]["active"])
        session = SessionConfig(
            max_turns_in_context=int(raw["session"]["max_turns_in_context"])
        )
    except KeyError as e:
        raise ConfigError(f"Missing required config key: {e}") from e

    cfg = Config(
        app=app,
        model=model,
        generation=generation,
        persona=persona,
        session=session,
        root_dir=root_dir,
    )

    _validate(cfg)
    return cfg


def _resolve(root_dir: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (root_dir / p).resolve()


def _validate(cfg: Config) -> None:
    if cfg.model.backend not in ("ollama", "llamacpp"):
        # Without this a typo'd backend silently falls into the llamacpp
        # branch and fails with a confusing "weights not found" error.
        raise ConfigError(
            f"model.backend must be 'ollama' or 'llamacpp', got '{cfg.model.backend}'"
        )
    if cfg.generation.temperature < 0:
        raise ConfigError("generation.temperature must be >= 0")
    if cfg.model.context_length <= 0:
        raise ConfigError("model.context_length must be > 0")
    if not cfg.model.path.exists():
        # Not fatal at load time — the model loader will raise a clearer
        # error when it actually tries to load. We just warn here so
        # `load_config` stays usable for tests/tools that don't need weights.
        log.warning("Model weights not found at %s", cfg.model.path)
    cfg.app.data_dir.mkdir(parents=True, exist_ok=True)
