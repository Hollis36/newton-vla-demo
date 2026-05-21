"""Voice input: microphone capture via sounddevice + Google Web Speech recognition.

Design for a live classroom demo:
  - Record a fixed 4-second clip once the user presses `3`, with a visual
    "Listening…" indicator.
  - Send the WAV to Google's free web recognizer (no API key needed).
  - If recognition fails (network blocked, silence, unclear speech), return a
    helpful error string so the UI can surface it without crashing.
  - Run on a daemon thread so the pygame loop stays at 60 fps.

The transcript then flows into the same `parse_command` pipeline used by the
typed-text path, so speech becomes actions.
"""

from __future__ import annotations

import contextlib
import difflib
import io
import math
import re
import threading
import time
import wave
from collections import Counter, defaultdict
from dataclasses import dataclass
from types import ModuleType

import numpy as np

SAMPLE_RATE = 16000      # Hz, good for speech
CHANNELS = 1
DURATION = 4.0           # seconds of audio captured per recording


# ---------------------------------------------------------------------------
# Fuzzy vocabulary matching
# ---------------------------------------------------------------------------
# Google Speech doesn't know about our tiny demo vocabulary, so it happily
# hands back things like "peter ride" instead of "pick red" or "flower" for
# "tower". We normalize the transcript in two passes:
#
#   1) A hand-tuned phonetic table of known mishears (exact replacements).
#   2) difflib fuzzy matching against the full vocab with a low cutoff, so
#      any near-miss also gets snapped.
#
# Typed-text commands bypass this — only voice transcripts go through it.

_PHONETIC_MAP: dict[str, str] = {
    # pick / grab
    "peter": "pick", "pete": "pick", "peak": "pick", "peaked": "pick",
    "pink": "pick", "picked": "pick", "picks": "pick", "pig": "pick",
    "bic": "pick", "bick": "pick", "beak": "pick",
    "grabbed": "grab", "grab": "grab", "crab": "grab",
    "take": "pick", "taken": "pick", "taker": "pick", "taco": "pick",
    "lift": "pick", "left": "pick",
    # place / put
    "placed": "place", "plays": "place", "plates": "place",
    "putt": "put", "puts": "put", "boot": "put", "put": "put",
    "drop": "put", "dropped": "put",
    # stack
    "stuck": "stack", "stick": "stack", "sack": "stack", "stocks": "stack",
    "tack": "stack", "stacker": "stack", "stacked": "stack",
    "tar": "stack", "star": "stack", "start": "stack", "stark": "stack",
    # tower
    "flower": "tower", "power": "tower", "hour": "tower", "toilet": "tower",
    # build
    "built": "build", "bilt": "build", "bill": "build",
    # home
    "homes": "home", "omg": "home", "own": "home",
    # red
    "ride": "red", "read": "red", "dread": "red", "rad": "red",
    "ready": "red", "reddit": "red", "rate": "red", "head": "red",
    # green
    "grain": "green", "grin": "green", "crane": "green", "queen": "green",
    "clean": "green", "scream": "green", "greens": "green",
    # blue
    "blew": "blue", "glue": "blue", "below": "blue", "clue": "blue",
    "flu": "blue", "true": "blue",
    # yellow
    "yelp": "yellow", "yell": "yellow", "mellow": "yellow", "fellow": "yellow",
    "hello": "yellow", "yall": "yellow",
    # glue words
    "block": "block", "blocks": "block", "cube": "block", "cubes": "block",
    "box": "block", "boxes": "block", "brick": "block",
}

_VOCAB: tuple[str, ...] = (
    "pick", "grab", "take", "lift", "get",
    "put", "place", "drop", "set",
    "stack", "tower", "build", "pile",
    "drive", "move", "go", "roll", "travel",
    "left", "right", "forward", "back", "reverse",
    "home", "rest", "reset",
    "red", "green", "blue", "yellow",
    "up", "the", "on", "at", "a", "an", "of", "with", "and",
    "to", "from", "into", "block", "cube", "meter", "meters",
)

# Disfluencies that natural spoken input peppers between content words.
# Stripping these BEFORE phonetic mapping is a strict Pareto improvement —
# see research/voice_correction/REPORT_W1.md §4.3:
# B5 (filter + learned phonetic) beats B4 (no filter) by +14 pp Command
# Accuracy on the synthetic benchmark and is simultaneously faster because
# stripping tokens shortens the list scanned by `difflib`.
# Intentionally excludes articles (a / an / the) — parser tolerates them and
# they carry domain context (e.g. "the red one" vs "red" as an isolated tag).
_FILLERS: frozenset[str] = frozenset({
    "um", "uh", "uhh", "er", "erm", "ah", "hmm",
    "like", "so", "well", "actually",
})


# ---------------------------------------------------------------------------
# Bigram language model for context-aware reranking
# ---------------------------------------------------------------------------
# Trained on the 49 canonical demo command templates. When a noisy token has
# multiple close edit-distance matches in vocab, the bigram context picks the
# one that fits the surrounding sentence — replacing the previous "first
# difflib match wins" tiebreaker. This is the B6/B7 reranking from the
# voice-correction research.
#
# Why this matters operationally: a non-native speaker who says "the rate
# block" gets difflib candidates {red, reset, rest} for "rate"; under the
# bigram LM, "the red block" outscores "the reset block" because the LM has
# only seen the former in training.

_DEMO_TEMPLATES: tuple[str, ...] = (
    "build a tower from blue green and yellow",
    "build a tower from green yellow and blue",
    "drive forward", "drive left", "drive to the red cube",
    "drop it back", "drop it right",
    "go home",
    "go to the green block", "go to the red block", "go to the yellow block",
    "grab the green cube", "grab the red cube",
    "lift the blue block", "lift the green block",
    "lift the red block", "lift the yellow block",
    "move back", "move right",
    "pick blue", "pick green", "pick red", "pick yellow",
    "pick up the green block", "pick up the red block",
    "place green", "place red", "place yellow",
    "place the green block right", "place the red block left",
    "place the yellow block forward", "place the yellow block right",
    "put it on the back", "put it on the forward",
    "reset the scene",
    "stack blue and green", "stack blue green and red",
    "stack blue green and yellow", "stack green and yellow",
    "stack green red", "stack red yellow",
    "stack yellow and blue", "stack yellow blue",
    "stack yellow blue and green", "stack yellow red and blue",
    "take the blue one", "take the green one",
    "take the red one", "take the yellow one",
)


class _BigramLM:
    """Additive-smoothed bigram model over demo vocab + sentence boundaries.

    Provides log P(word | prev) for reranking edit-distance candidates.
    """

    BOS = "<s>"
    EOS = "</s>"
    SMOOTHING_K = 0.5

    def __init__(self, vocab: tuple[str, ...]) -> None:
        self._vocab_set: frozenset[str] = frozenset(vocab) | {self.BOS, self.EOS}
        self._v: int = len(self._vocab_set)
        self._uni: Counter[str] = Counter()
        self._bi: dict[str, Counter[str]] = defaultdict(Counter)

    def fit(self, sentences: tuple[str, ...]) -> _BigramLM:
        for sent in sentences:
            toks = [self.BOS] + [w for w in sent.lower().split()
                                 if w in self._vocab_set] + [self.EOS]
            for a, b in zip(toks[:-1], toks[1:], strict=True):
                self._uni[a] += 1
                self._bi[a][b] += 1
            self._uni[toks[-1]] += 1
        return self

    def log_p_cond(self, word: str, prev: str) -> float:
        if word not in self._vocab_set:
            word = self.EOS
        if prev not in self._vocab_set:
            prev = self.BOS
        numer = self._bi[prev][word] + self.SMOOTHING_K
        denom = self._uni[prev] + self.SMOOTHING_K * self._v
        return math.log(numer / denom)


_LM: _BigramLM | None = None


def _get_lm() -> _BigramLM:
    """Lazily build the bigram LM on first use (avoids module-import cost)."""
    global _LM
    if _LM is None:
        _LM = _BigramLM(_VOCAB).fit(_DEMO_TEMPLATES)
    return _LM


def fuzzy_snap(text: str, cutoff: float = 0.5) -> str:
    """Post-process a noisy voice transcript into something the parser likes.

    Pipeline (vocab-first dispatch with bigram LM rerank — the B7 method
    from the voice-correction research, which reaches phys_acc=0.733 on
    Newton physics validation vs the previous B3-style production at 0.633):

      1. Lowercase + strip punctuation.
      2. Drop pure disfluencies (um / uh / like / …).
      3. For each token:
         a. If in vocab, pass through. This trusts the ASR's already-correct
            tokens — and fixes a real bug in the prior dispatch where
            "drive left" became "drive pick" because the phonetic table
            mapped "left" → "pick" before the vocab check ran.
         b. If in the hand phonetic table, use that mapping (handles known
            mishears: peter→pick, ride→red, flower→tower, …).
         c. Else: difflib top-5 close matches against vocab, then rerank by
            bigram LM score against the previous chosen token. Picks the
            candidate that best fits the sentence context.
      4. Always emits the closest vocab match for OOV tokens — never
         rejects, because the demo target is non-native speakers whose
         pronunciation rarely yields exact ASR hits.
    """
    clean = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE).lower()
    lm = _get_lm()
    out: list[str] = []
    prev = _BigramLM.BOS

    for word in clean.split():
        if word in _FILLERS:
            continue
        if word in _VOCAB:
            chosen = word
        elif word in _PHONETIC_MAP:
            chosen = _PHONETIC_MAP[word]
        else:
            # Aggressive matching: every OOV token gets snapped to its
            # closest vocab member. The demo target is non-native speakers
            # whose pronunciation rarely yields exact ASR hits, so we'd
            # rather over-correct a stray "one"→"on" (parser ignores
            # short noise words anyway) than under-correct a mispronounced
            # action verb. Newton physics validation: the unguarded
            # version reaches phys_acc=0.733 vs guarded 0.700.
            candidates = difflib.get_close_matches(word, _VOCAB, n=5, cutoff=cutoff)
            if not candidates:
                chosen = word
            elif len(candidates) == 1:
                chosen = candidates[0]
            else:
                best_score = -math.inf
                chosen = candidates[0]
                for cand in candidates:
                    ratio = difflib.SequenceMatcher(None, word, cand).ratio()
                    score = ratio + lm.log_p_cond(cand, prev)
                    if score > best_score:
                        best_score = score
                        chosen = cand
        out.append(chosen)
        prev = chosen
    return " ".join(out)


@dataclass
class VoiceResult:
    ok: bool
    transcript: str = ""       # post-fuzzy-snap, what gets sent to the parser
    raw_transcript: str = ""   # exactly what the speech recognizer returned
    error: str = ""
    latency_ms: float = 0.0
    language_used: str = ""


def _sounddevice() -> ModuleType:
    """Import sounddevice only when microphone capture is requested."""
    try:
        import sounddevice as sd_mod
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Microphone input requires the demo extra: "
            "`uv run --extra demo python -m demo_live`."
        ) from e
    return sd_mod


def record_audio(duration: float = DURATION) -> np.ndarray:
    """Block on the calling thread for `duration` seconds while capturing mic audio."""
    sd = _sounddevice()
    audio = sd.rec(
        frames=int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
    )
    sd.wait()
    return audio


def _audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)                 # int16 → 2 bytes/sample
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


# Maximum seconds we'll wait for Google Web Speech to respond before
# treating the request as failed. 5 s is plenty on a healthy network and
# short enough that classroom WiFi hiccups don't freeze the UI.
TRANSCRIBE_TIMEOUT_S = 5.0


def transcribe(wav_bytes: bytes, preferred_language: str = "zh-CN") -> tuple[str, str, str]:
    """Send WAV bytes to Google Web Speech. Returns (transcript, language_used, error).

    Tries BOTH languages and keeps the one whose transcript hits more of
    our demo vocabulary. This makes '3' work for a bilingual audience:
    an English speaker and a Chinese speaker can take turns without
    pressing any extra key. If neither recognizer extracts anything, we
    return an empty transcript.

    Each recognize_google() call is bounded by TRANSCRIBE_TIMEOUT_S via
    `recognizer.operation_timeout`, which is per-recognizer and DOES NOT
    mutate the process-wide socket default (the previous implementation
    using `socket.setdefaulttimeout` leaked the 5 s limit to anything else
    making sockets during the transcription window). Older versions of
    speech_recognition silently ignore the attribute, so as a fall-back we
    still wrap the call in a TimeoutError-catching handler.
    """
    import speech_recognition as sr_mod  # lazy so main loop boots fast
    recognizer = sr_mod.Recognizer()
    # Per-recognizer timeout; safe to set unconditionally — older versions
    # ignore unknown attributes on Recognizer rather than erroring.
    with contextlib.suppress(AttributeError):
        recognizer.operation_timeout = TRANSCRIBE_TIMEOUT_S
    audio_data = sr_mod.AudioData(wav_bytes[44:], SAMPLE_RATE, 2)

    # Chinese first for the classroom context — flip order via
    # `preferred_language` kwarg if a mostly-English audience is expected.
    langs = ("zh-CN", "en-US") if preferred_language.startswith("zh") else ("en-US", "zh-CN")
    best_text = ""
    best_lang = preferred_language
    best_score = -1
    err_msg = ""
    for lang in langs:
        try:
            text = recognizer.recognize_google(audio_data, language=lang).strip()
        except sr_mod.UnknownValueError:
            continue
        except sr_mod.RequestError as e:
            err_msg = f"speech service error: {e}"
            continue
        except (TimeoutError, OSError) as e:
            err_msg = f"speech service timed out: {e}"
            continue
        if not text:
            continue
        score = _vocab_hit_score(text, lang)
        if score > best_score:
            best_score = score
            best_text = text
            best_lang = lang
    if best_text:
        return best_text, best_lang, ""
    return "", preferred_language, err_msg or "no speech detected"


def _vocab_hit_score(text: str, lang: str) -> int:
    """Quick heuristic: how many demo keywords does this transcript touch?
    Higher is better. Used to pick between en-US vs zh-CN recognizers."""
    t = text.lower()
    english_hits = sum(1 for w in (
        "pick", "grab", "take", "put", "place", "drop",
        "stack", "tower", "build", "drive", "move", "go",
        "home", "left", "right", "red", "green", "blue", "yellow",
        "the", "a",
    ) if w in t)
    chinese_hits = sum(1 for w in (
        "拿", "抓", "取", "放", "搁", "堆", "塔", "搭",
        "走", "开", "移动", "回", "归", "家",
        "左", "右", "前", "后",
        "红", "绿", "蓝", "黄",
        "方块", "立方", "盒子",
    ) if w in text)
    return english_hits + chinese_hits


def capture_once(duration: float = DURATION,
                 preferred_language: str = "zh-CN") -> VoiceResult:
    """Full blocking capture → transcribe cycle. Call from a background thread."""
    start = time.perf_counter()
    try:
        audio = record_audio(duration)
    except Exception as e:
        return VoiceResult(False, error=f"mic error: {e}",
                           latency_ms=(time.perf_counter() - start) * 1000)

    wav = _audio_to_wav_bytes(audio)
    try:
        text, lang, err = transcribe(wav, preferred_language=preferred_language)
    except Exception as e:
        return VoiceResult(False, error=f"stt error: {e}",
                           latency_ms=(time.perf_counter() - start) * 1000)

    ms = (time.perf_counter() - start) * 1000
    if not text:
        return VoiceResult(False, error=err or "empty transcript",
                           latency_ms=ms, language_used=lang)
    snapped = fuzzy_snap(text) if lang.startswith("en") else text
    return VoiceResult(True, transcript=snapped, raw_transcript=text,
                       latency_ms=ms, language_used=lang)


class VoiceRecorder:
    """Toggle-based recorder: call start() to begin listening, stop() to
    finalize the clip and kick off transcription on a background thread.

    Lets the presenter hit '3' once to speak a long sentence and '3' again
    when done, instead of racing a fixed 4-second window.
    """

    def __init__(
        self,
        max_duration: float = 10.0,
        preferred_language: str = "zh-CN",
    ) -> None:
        self.max_duration = max_duration
        self.preferred_language = preferred_language
        self.audio: np.ndarray | None = None
        self.recording: bool = False
        self.start_time: float = 0.0
        self.result: VoiceResult | None = None
        self._transcribe_thread: threading.Thread | None = None

    # ---------------------------------------------------- state transitions

    def start(self) -> None:
        try:
            sd = _sounddevice()
            self.audio = sd.rec(
                int(self.max_duration * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
            )
        except Exception as e:
            self.result = VoiceResult(False, error=f"mic error: {e}")
            return
        self.recording = True
        self.start_time = time.perf_counter()

    def stop(self) -> None:
        if not self.recording:
            return
        with contextlib.suppress(Exception):
            sd = _sounddevice()
            sd.stop()
        elapsed = time.perf_counter() - self.start_time
        samples = max(int(0.2 * SAMPLE_RATE),
                      min(self.audio.shape[0], int(elapsed * SAMPLE_RATE)))
        truncated = self.audio[:samples]
        self.recording = False
        self._transcribe_thread = threading.Thread(
            target=self._run_transcribe, args=(truncated,), daemon=True,
        )
        self._transcribe_thread.start()

    # ---------------------------------------------------- workers

    def _run_transcribe(self, audio: np.ndarray) -> None:
        start = time.perf_counter()
        try:
            wav = _audio_to_wav_bytes(audio)
            text, lang, err = transcribe(wav, preferred_language=self.preferred_language)
        except Exception as e:
            self.result = VoiceResult(
                False, error=f"stt error: {e}",
                latency_ms=(time.perf_counter() - start) * 1000,
            )
            return
        ms = (time.perf_counter() - start) * 1000
        if not text:
            self.result = VoiceResult(
                False, error=err or "empty transcript",
                latency_ms=ms, language_used=lang,
            )
            return
        # Chinese passes through untouched (tokens are already semantic);
        # English gets vocab-snapping to fix common mishears.
        snapped = fuzzy_snap(text) if lang.startswith("en") else text
        self.result = VoiceResult(
            True, transcript=snapped, raw_transcript=text,
            latency_ms=ms, language_used=lang,
        )

    # ---------------------------------------------------- observers

    @property
    def is_transcribing(self) -> bool:
        return self._transcribe_thread is not None and self._transcribe_thread.is_alive()

    @property
    def is_busy(self) -> bool:
        return self.recording or self.is_transcribing

    def elapsed(self) -> float:
        if not self.recording:
            return 0.0
        return max(0.0, time.perf_counter() - self.start_time)
