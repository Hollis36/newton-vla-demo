"""Procedurally-synthesized sound effects for the classroom demo.

No audio assets shipped — every cue is built from a handful of NumPy arrays at
startup. Keeps the project self-contained and avoids copyright/asset issues.

Usage:
    sfx.init()
    sfx.play("pop")
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
import pygame

_SR = 22050
_INITIALIZED = False
_SOUNDS: dict[str, pygame.mixer.Sound] = {}


def _envelope_decay(n: int, tau: float) -> np.ndarray:
    """Exponential decay 1 → 0 over `n` samples with given e-fold time in seconds."""
    t = np.arange(n) / _SR
    return np.exp(-t / max(1e-3, tau))


def _envelope_attack_decay(n: int, attack_ms: float, decay_tau: float) -> np.ndarray:
    t = np.arange(n) / _SR
    a = np.clip(t / (attack_ms / 1000), 0.0, 1.0)
    d = np.exp(-t / max(1e-3, decay_tau))
    return a * d


def _tone(
    freqs: Iterable[float],
    duration_ms: float,
    envelope: str = "decay",
    decay_tau: float = 0.08,
    attack_ms: float = 3.0,
    volume: float = 0.35,
    waveform: str = "sine",
) -> pygame.mixer.Sound:
    n = int(_SR * duration_ms / 1000)
    t = np.arange(n) / _SR
    signal = np.zeros(n, dtype=np.float32)
    freqs = list(freqs)
    for f in freqs:
        if waveform == "sine":
            signal += np.sin(2 * math.pi * f * t)
        elif waveform == "square":
            signal += np.sign(np.sin(2 * math.pi * f * t))
        elif waveform == "triangle":
            signal += 2 * np.abs(2 * (f * t - np.floor(f * t + 0.5))) - 1
    signal /= max(1, len(freqs))

    if envelope == "decay":
        env = _envelope_decay(n, decay_tau)
    elif envelope == "ad":
        env = _envelope_attack_decay(n, attack_ms, decay_tau)
    else:
        env = np.ones(n)
    signal = signal * env * volume

    samples = np.clip(signal * 32767, -32767, 32767).astype(np.int16)
    stereo = np.stack([samples, samples], axis=1)
    return pygame.sndarray.make_sound(stereo.copy(order="C"))


def _chirp(
    f_start: float,
    f_end: float,
    duration_ms: float,
    decay_tau: float = 0.1,
    volume: float = 0.3,
) -> pygame.mixer.Sound:
    n = int(_SR * duration_ms / 1000)
    t = np.arange(n) / _SR
    freq = f_start + (f_end - f_start) * (t / max(1e-3, duration_ms / 1000))
    phase = 2 * math.pi * np.cumsum(freq) / _SR
    signal = np.sin(phase) * _envelope_decay(n, decay_tau) * volume
    samples = np.clip(signal * 32767, -32767, 32767).astype(np.int16)
    stereo = np.stack([samples, samples], axis=1)
    return pygame.sndarray.make_sound(stereo.copy(order="C"))


def init() -> None:
    """Call once after pygame.init(). Safe to call multiple times."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    try:
        pygame.mixer.init(frequency=_SR, size=-16, channels=2, buffer=256)
    except pygame.error:
        _INITIALIZED = False
        return
    _build_library()
    _INITIALIZED = True


def _build_library() -> None:
    _SOUNDS.clear()
    # Ball caught — bright, rising bell
    _SOUNDS["pop"] = _chirp(600, 1200, 140, decay_tau=0.06, volume=0.32)
    # Block placed — low thud
    _SOUNDS["thud"] = _tone([150, 90], 180, envelope="decay",
                            decay_tau=0.07, volume=0.45, waveform="sine")
    # Gripper closes — sharp click
    _SOUNDS["click"] = _tone([1800, 2600], 40, envelope="ad",
                             attack_ms=2, decay_tau=0.02, volume=0.28)
    # Voice recognized — friendly ding
    _SOUNDS["ding"] = _tone([1200, 1800], 180, envelope="decay",
                            decay_tau=0.10, volume=0.30)
    # Mode changed — two-note accent
    _SOUNDS["mode"] = _chirp(440, 880, 120, decay_tau=0.07, volume=0.28)
    # Task completed / stack done — triumphant arpeggio
    _SOUNDS["success"] = _tone([523, 659, 784], 350, envelope="decay",
                               decay_tau=0.18, volume=0.30, waveform="triangle")
    # Error / miss — short buzz
    _SOUNDS["miss"] = _tone([220], 140, envelope="decay",
                            decay_tau=0.06, volume=0.22, waveform="triangle")


def play(name: str) -> None:
    """Play a cached sound. No-op if mixer didn't init (e.g., headless tests)."""
    if not _INITIALIZED:
        return
    s = _SOUNDS.get(name)
    if s is not None:
        s.play()
