#!/usr/bin/env python3
"""Convert a MIDI file to MP3.

Implementation details:
1) Tries to synthesize MIDI to WAV using `pretty_midi` (Python package).
2) Encodes WAV to MP3 by calling `ffmpeg` from Python subprocess.

This keeps orchestration in Python while remaining easy to integrate.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _require_module(name: str) -> None:
    try:
        __import__(name)
    except ImportError as exc:
        raise SystemExit(
            f"Missing dependency: {name}. Install with: pip install {name}"
        ) from exc


def midi_to_wav(midi_path: Path, wav_path: Path, sample_rate: int = 44100) -> None:
    _require_module("numpy")
    _require_module("scipy")
    _require_module("pretty_midi")

    import numpy as np
    from scipy.io import wavfile
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    audio = pm.synthesize(fs=sample_rate)

    # Convert float waveform [-1,1] to int16 PCM
    audio = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio * 32767).astype(np.int16)
    wavfile.write(str(wav_path), sample_rate, audio_int16)


def wav_to_mp3(wav_path: Path, mp3_path: Path, bitrate_kbps: int = 192) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit(
            "ffmpeg is required for MP3 encoding but was not found in PATH. "
            "Install ffmpeg and retry."
        )

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate_kbps}k",
        str(mp3_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"ffmpeg failed:\n{result.stderr}")


def convert_midi_to_mp3(midi_path: Path, mp3_path: Path, sample_rate: int, bitrate_kbps: int) -> None:
    if not midi_path.exists():
        raise SystemExit(f"Input MIDI not found: {midi_path}")

    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="midi_render_") as tmpdir:
        wav_path = Path(tmpdir) / "render.wav"
        midi_to_wav(midi_path, wav_path, sample_rate=sample_rate)
        wav_to_mp3(wav_path, mp3_path, bitrate_kbps=bitrate_kbps)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert MIDI to MP3")
    parser.add_argument("--input", required=True, help="Input .mid file")
    parser.add_argument("--output", required=True, help="Output .mp3 file")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--bitrate", type=int, default=192, help="MP3 bitrate kbps")
    args = parser.parse_args()

    convert_midi_to_mp3(
        midi_path=Path(args.input),
        mp3_path=Path(args.output),
        sample_rate=max(8000, args.sample_rate),
        bitrate_kbps=max(32, args.bitrate),
    )
    print(f"MP3 generated: {args.output}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
