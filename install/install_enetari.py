#!/usr/bin/env python3
"""Installateur unique d’Enetari pour Ubuntu."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

ROOT = Path("/opt/enetari")
DATA = Path("/var/lib/enetari")
CONFIG_DIR = Path("/etc/enetari")
VENV = ROOT / ".venv"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

WHISPER_DIR = ROOT / "whisper.cpp"
LLAMA_DIR = ROOT / "llama.cpp"
APP_DIR = ROOT / "app"
PIPER_MODELS = ROOT / "models" / "piper"
WHISPER_MODELS = ROOT / "models" / "whisper"
LLM_MODELS = ROOT / "models" / "llm"

PIPER_VOICE = "fr_FR-siwis-medium"
LLM_FILENAME = "Qwen3-4B-Q4_K_M.gguf"
LLM_URL = (
    "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/"
    + LLM_FILENAME
)

APT_PACKAGES = [
    "ca-certificates", "curl", "git", "cmake", "build-essential",
    "ffmpeg", "python3", "python3-venv", "python3-pip", "sqlite3",
    "alsa-utils", "libvulkan-dev", "vulkan-tools",
    "mesa-vulkan-drivers", "glslc",
]


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Lance cet installateur avec sudo.")


def create_directories() -> None:
    for path in (
        ROOT, APP_DIR, DATA, DATA / "memory", DATA / "audio" / "input",
        DATA / "audio" / "output", DATA / "backups", PIPER_MODELS,
        WHISPER_MODELS, LLM_MODELS, CONFIG_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def install_whisper(model_name: str) -> Path:
    if not WHISPER_DIR.exists():
        run([
            "git", "clone", "--depth", "1",
            "https://github.com/ggml-org/whisper.cpp.git", str(WHISPER_DIR),
        ])
    run(["cmake", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"], cwd=WHISPER_DIR)
    run([
        "cmake", "--build", "build", "-j", str(os.cpu_count() or 2),
        "--target", "whisper-cli",
    ], cwd=WHISPER_DIR)
    target = WHISPER_MODELS / f"ggml-{model_name}.bin"
    if not target.exists():
        run(["bash", "models/download-ggml-model.sh", model_name], cwd=WHISPER_DIR)
        shutil.copy2(WHISPER_DIR / "models" / target.name, target)
    return target


def install_python_and_piper() -> tuple[Path, Path]:
    if not (VENV / "bin" / "python").exists():
        run(["python3", "-m", "venv", str(VENV)])
    python = VENV / "bin" / "python"
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([
        str(python), "-m", "pip", "install",
        "piper-tts", "PyYAML", "requests",
    ])
    model = PIPER_MODELS / f"{PIPER_VOICE}.onnx"
    model_config = PIPER_MODELS / f"{PIPER_VOICE}.onnx.json"
    if not model.exists() or not model_config.exists():
        run([
            str(python), "-m", "piper.download_voices",
            "--data-dir", str(PIPER_MODELS), PIPER_VOICE,
        ])
    return model, model_config


def install_llama() -> tuple[Path, Path]:
    if not LLAMA_DIR.exists():
        run([
            "git", "clone", "--depth", "1",
            "https://github.com/ggml-org/llama.cpp.git", str(LLAMA_DIR),
        ])
    run([
        "cmake", "-B", "build", "-DGGML_VULKAN=ON",
        "-DCMAKE_BUILD_TYPE=Release",
    ], cwd=LLAMA_DIR)
    run([
        "cmake", "--build", "build", "-j", str(os.cpu_count() or 2),
        "--target", "llama-server",
    ], cwd=LLAMA_DIR)
    executable = LLAMA_DIR / "build" / "bin" / "llama-server"
    model = LLM_MODELS / LLM_FILENAME
    if not model.exists():
        run([
            "curl", "-L", "--fail", "--continue-at", "-",
            "-o", str(model), LLM_URL,
        ])
    return executable, model


def initialize_database() -> Path:
    database = DATA / "memory" / "enetari.db"
    schema = """
    PRAGMA journal_mode=WAL;
    PRAGMA foreign_keys=ON;

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL CHECK(role IN ('owner', 'user')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ended_at TEXT,
        summary TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT NOT NULL,
        content TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'conversation',
        protected INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS pending_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requested_by_user_id INTEGER,
        target TEXT NOT NULL,
        proposed_value TEXT NOT NULL,
        reason TEXT,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending', 'approved', 'rejected')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        decided_at TEXT,
        FOREIGN KEY(requested_by_user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS protected_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_key TEXT NOT NULL UNIQUE,
        rule_value TEXT NOT NULL,
        owner_only INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    INSERT OR IGNORE INTO users(name, role) VALUES ('proprietaire', 'owner');
    INSERT OR IGNORE INTO protected_rules(rule_key, rule_value, owner_only)
    VALUES
      ('personality_locked', 'true', 1),
      ('non_owner_cannot_change_personality', 'true', 1),
      ('conflict_keeps_current_value', 'true', 1);
    """
    with sqlite3.connect(database) as connection:
        connection.executescript(schema)
    return database


def install_personality() -> Path:
    source = PROJECT_ROOT / "config" / "personality.yaml"
    target = CONFIG_DIR / "personality.yaml"
    if not source.exists():
        raise SystemExit(f"Fichier manquant : {source}")
    if not target.exists():
        shutil.copy2(source, target)
    target.chmod(0o644)
    return target


def write_config(
    whisper_model: Path,
    piper_model: Path,
    piper_config: Path,
    llm_model: Path,
    database: Path,
    personality: Path,
) -> Path:
    path = CONFIG_DIR / "config.yaml"
    path.write_text(f"""stt:
  engine: whisper_cpp
  executable: {WHISPER_DIR / 'build' / 'bin' / 'whisper-cli'}
  model: {whisper_model}
  language: fr

tts:
  engine: piper
  executable: {VENV / 'bin' / 'piper'}
  model: {piper_model}
  model_config: {piper_config}

llm:
  engine: llama_server
  api_url: http://127.0.0.1:8080
  model_name: Qwen3-4B
  model_file: {llm_model}
  context_size: 4096
  max_tokens: 220
  temperature: 0.6
  top_p: 0.9
  timeout_seconds: 180

memory:
  engine: sqlite
  database: {database}
  personality_file: {personality}
  owner_name: proprietaire

paths:
  audio_input: {DATA / 'audio' / 'input'}
  audio_output: {DATA / 'audio' / 'output'}
  backups: {DATA / 'backups'}
""", encoding="utf-8")
    path.chmod(0o644)
    return path


def install_app() -> None:
    source = PROJECT_ROOT / "app" / "enetari.py"
    target = APP_DIR / "enetari.py"
    if not source.exists():
        raise SystemExit(f"Fichier manquant : {source}")
    shutil.copy2(source, target)
    target.chmod(0o755)
    launcher = Path("/usr/local/bin/enetari")
    launcher.write_text(
        f"#!/bin/sh\nexec {VENV / 'bin' / 'python'} {target} \"$@\"\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)


def install_llm_service(executable: Path, model: Path) -> None:
    service = Path("/etc/systemd/system/enetari-llm.service")
    service.write_text(f"""[Unit]
Description=Enetari local Qwen server
After=local-fs.target
Wants=local-fs.target

[Service]
Type=simple
WorkingDirectory={LLAMA_DIR}
ExecStart={executable} --model {model} --host 127.0.0.1 --port 8080 --ctx-size 4096 --gpu-layers 99 --threads {max(1, os.cpu_count() or 4)} --parallel 1
Restart=on-failure
RestartSec=5
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
""", encoding="utf-8")
    service.chmod(0o644)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "enetari-llm.service"])
    run(["systemctl", "restart", "enetari-llm.service"])


def wait_for_llm(timeout_seconds: int = 180) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["curl", "-fsS", "http://127.0.0.1:8080/health"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return True
        time.sleep(2)
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--whisper-model", default="small",
        choices=["tiny", "base", "small", "medium", "large-v3-turbo"],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    require_root()
    if platform.system() != "Linux":
        raise SystemExit("Cet installateur est prévu pour Linux.")

    run(["apt-get", "update"])
    run(["apt-get", "install", "-y", *APT_PACKAGES])
    create_directories()

    whisper_model = install_whisper(args.whisper_model)
    piper_model, piper_config = install_python_and_piper()
    llama_server, llm_model = install_llama()
    database = initialize_database()
    personality = install_personality()
    config = write_config(
        whisper_model, piper_model, piper_config,
        llm_model, database, personality,
    )
    install_app()
    install_llm_service(llama_server, llm_model)

    print()
    if wait_for_llm():
        print("Qwen est chargé et son service répond.")
    else:
        print("Qwen n’a pas répondu dans le délai prévu.")
        print("Diagnostic : systemctl status enetari-llm --no-pager")
        print("Journaux : journalctl -u enetari-llm -n 100 --no-pager")
    print("Enetari est installée.")
    print("Test : enetari --text 'Comment vas-tu ?' --no-voice")
    print("Configuration :", config)


if __name__ == "__main__":
    main()
