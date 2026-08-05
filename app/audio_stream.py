#!/usr/bin/env python3
"""Pipeline audio en continu pour Enetari.

Ce module reçoit des phrases complètes, les synthétise avec Piper dans un
thread, puis les lit dans l'ordre avec aplay dans un second thread.
Il n'est pas encore raccordé au flux Qwen dans ce premier commit.
"""

from __future__ import annotations

import queue
import subprocess
import tempfile
import threading
from pathlib import Path
from time import perf_counter
from typing import Any


class StreamingAudioError(RuntimeError):
    """Erreur produite par le pipeline audio en continu."""


_STOP = object()


class StreamingSpeaker:
    """Synthétise et lit des phrases en parallèle, dans leur ordre d'arrivée."""

    def __init__(self, config: dict[str, Any], playback_device: str) -> None:
        tts = config["tts"]
        self._piper_executable = str(tts["executable"])
        self._piper_model = str(tts["model"])
        self._piper_model_config = str(tts["model_config"])
        self._playback_device = playback_device

        self._phrase_queue: queue.Queue[str | object] = queue.Queue()
        self._audio_queue: queue.Queue[Path | object] = queue.Queue()
        self._errors: queue.Queue[BaseException] = queue.Queue()
        self._closed = False
        self._sequence = 0
        self._sequence_lock = threading.Lock()
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="enetari-stream-")
        self._output_directory = Path(self._temporary_directory.name)

        self._piper_thread = threading.Thread(
            target=self._piper_worker,
            name="enetari-piper",
            daemon=True,
        )
        self._player_thread = threading.Thread(
            target=self._player_worker,
            name="enetari-player",
            daemon=True,
        )
        self._piper_thread.start()
        self._player_thread.start()

    def enqueue(self, text: str) -> None:
        """Ajoute une phrase à synthétiser sans attendre sa lecture."""
        self._raise_worker_error()
        if self._closed:
            raise StreamingAudioError("Le pipeline audio est déjà fermé.")

        phrase = text.strip()
        if phrase:
            self._phrase_queue.put(phrase)

    def close(self) -> None:
        """Attend la synthèse et la lecture de toutes les phrases en attente."""
        if self._closed:
            self._raise_worker_error()
            return

        self._closed = True
        self._phrase_queue.put(_STOP)
        self._piper_thread.join()
        self._player_thread.join()
        self._temporary_directory.cleanup()
        self._raise_worker_error()

    def __enter__(self) -> "StreamingSpeaker":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _next_output_path(self) -> Path:
        with self._sequence_lock:
            self._sequence += 1
            sequence = self._sequence
        return self._output_directory / f"phrase-{sequence:04d}.wav"

    def _piper_worker(self) -> None:
        try:
            while True:
                item = self._phrase_queue.get()
                try:
                    if item is _STOP:
                        self._audio_queue.put(_STOP)
                        return

                    phrase = str(item)
                    output = self._next_output_path()
                    started = perf_counter()
                    result = subprocess.run(
                        [
                            self._piper_executable,
                            "--model",
                            self._piper_model,
                            "--config",
                            self._piper_model_config,
                            "--output_file",
                            str(output),
                        ],
                        input=phrase,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    if result.returncode != 0:
                        detail = (result.stderr or result.stdout or "").strip()
                        raise StreamingAudioError(detail or "Échec de Piper.")

                    print(
                        f"[STREAM] Piper : {output.name} "
                        f"({perf_counter() - started:.3f}s)"
                    )
                    self._audio_queue.put(output)
                finally:
                    self._phrase_queue.task_done()
        except BaseException as exc:
            self._errors.put(exc)
            self._audio_queue.put(_STOP)

    def _player_worker(self) -> None:
        try:
            while True:
                item = self._audio_queue.get()
                try:
                    if item is _STOP:
                        return

                    wav_path = Path(item)
                    started = perf_counter()
                    result = subprocess.run(
                        [
                            "aplay",
                            "-q",
                            "-D",
                            self._playback_device,
                            str(wav_path),
                        ],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    if result.returncode != 0:
                        detail = (result.stderr or result.stdout or "").strip()
                        raise StreamingAudioError(detail or "Échec de aplay.")

                    print(
                        f"[STREAM] Lecture : {wav_path.name} "
                        f"({perf_counter() - started:.3f}s)"
                    )
                    wav_path.unlink(missing_ok=True)
                finally:
                    self._audio_queue.task_done()
        except BaseException as exc:
            self._errors.put(exc)

    def _raise_worker_error(self) -> None:
        try:
            error = self._errors.get_nowait()
        except queue.Empty:
            return

        if isinstance(error, StreamingAudioError):
            raise error
        raise StreamingAudioError(str(error)) from error
