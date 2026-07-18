"""
Offline voice I/O for Ledgr. This is what the track brief actually means
by "through conversational AI" — a text box satisfies the letter of it,
but a shop owner talking to their phone and hearing an answer back is the
real thing, and it's a strong live-demo moment precisely because it makes
the "fully offline" claim visibly, audibly true (record with wifi off,
still works).

STT: faster-whisper. Downloads a small model once on first run (needs
internet that one time), fully offline after that — same "nothing leaves
the device" story as everything else here, since transcription then runs
locally with no API calls.

TTS: pyttsx3, which wraps the OS's own speech engine. Chosen over a neural
TTS like Piper specifically for demo-day reliability — zero model
download, works out of the box on Windows/Mac/Linux. Swap in Piper later
for higher-quality voice output, but only after confirming it actually
works on the exact machine you're demoing on.
"""

import os
import uuid

_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        # "base" balances speed and accuracy for short voice queries on CPU.
        # Drop to "tiny" if transcription feels slow on the demo machine.
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


def transcribe_audio(audio_path: str) -> str:
    """Returns transcribed text from a local audio file (wav/mp3/webm/m4a)."""
    model = _get_whisper_model()
    segments, _ = model.transcribe(audio_path)
    return " ".join(segment.text.strip() for segment in segments).strip()


AUDIO_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "audio_out")
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)


def speak_text(text: str) -> str:
    """
    Synthesizes `text` to a wav file on disk and returns its path. Spins up
    a fresh pyttsx3 engine per call rather than reusing one across
    requests — the library isn't reliably reusable across repeated calls
    in the same long-running process on every platform, and a live demo
    needs this to just work every single time, not be clever about reuse.
    """
    import pyttsx3

    filename = f"{uuid.uuid4().hex}.wav"
    path = os.path.join(AUDIO_OUTPUT_DIR, filename)

    engine = pyttsx3.init()
    engine.setProperty("rate", 175)
    engine.save_to_file(text, path)
    engine.runAndWait()
    engine.stop()

    return path
