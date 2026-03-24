#!/usr/bin/env python3
"""Convert symbolic music events + affective properties to a MIDI file.

Input format (JSON):
{
  "global": {
    "tempo": 120,
    "valence": 0.6,
    "arousal": 0.7,
    "ticks_per_beat": 480,
    "program": 0,
    "time_signature": [4, 4]
  },
  "events": [
    {
      "symbol": "C4",
      "beats": 1,
      "valence": 0.8,
      "arousal": 0.4,
      "tempo": 128,
      "velocity": 90
    },
    {
      "symbol": "REST",
      "beats": 0.5
    }
  ]
}

Notes:
- valence and arousal are expected in [0.0, 1.0]
- symbol can be NOTE name (e.g. C4, D#3, Bb5), MIDI number (0..127), or REST
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


NOTE_BASE = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}


@dataclass
class MidiEvent:
    delta_ticks: int
    payload: bytes


def encode_variable_length(value: int) -> bytes:
    """Encode MIDI variable length quantity."""
    if value < 0:
        raise ValueError("Variable length value cannot be negative")
    buffer = [value & 0x7F]
    value >>= 7
    while value:
        buffer.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(buffer)


def parse_pitch(symbol: str | int) -> int:
    """Parse note symbol or MIDI number into MIDI pitch."""
    if isinstance(symbol, int):
        if 0 <= symbol <= 127:
            return symbol
        raise ValueError(f"MIDI note out of range: {symbol}")

    token = str(symbol).strip().upper()
    if token.isdigit() or (token.startswith("-") and token[1:].isdigit()):
        value = int(token)
        if 0 <= value <= 127:
            return value
        raise ValueError(f"MIDI note out of range: {value}")

    if len(token) < 2:
        raise ValueError(f"Invalid symbol: {symbol}")

    if token[1] in {"#", "B"}:
        name = token[:2]
        octave_part = token[2:]
    else:
        name = token[:1]
        octave_part = token[1:]

    if name not in NOTE_BASE:
        raise ValueError(f"Invalid note name: {symbol}")
    if not octave_part or not octave_part.lstrip("-").isdigit():
        raise ValueError(f"Invalid octave in symbol: {symbol}")

    octave = int(octave_part)
    midi_note = (octave + 1) * 12 + NOTE_BASE[name]
    if 0 <= midi_note <= 127:
        return midi_note
    raise ValueError(f"Converted note out of MIDI range: {symbol} -> {midi_note}")


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def valence_arousal_to_velocity(base_velocity: int, valence: float, arousal: float) -> int:
    """Map affective properties to note velocity.

    Heuristic:
    - arousal drives intensity strongly
    - valence adds a mild brightness/lift
    """
    arousal_gain = (arousal - 0.5) * 50
    valence_gain = (valence - 0.5) * 20
    velocity = round(base_velocity + arousal_gain + valence_gain)
    return int(clamp(velocity, 20, 127))


def valence_to_scale_shift(valence: float) -> int:
    """Map valence to ±2 semitone transposition."""
    return int(round((clamp(valence, 0.0, 1.0) - 0.5) * 4))


def build_track(events: Iterable[dict[str, Any]], ticks_per_beat: int, defaults: dict[str, Any]) -> bytes:
    """Build a single MIDI track chunk from event dictionaries."""
    midi_events: list[MidiEvent] = []

    tempo_bpm = float(defaults.get("tempo", 120))
    tempo_us_per_qn = int(60_000_000 / max(1.0, tempo_bpm))

    time_sig = defaults.get("time_signature", [4, 4])
    numerator = int(time_sig[0]) if isinstance(time_sig, list) and len(time_sig) == 2 else 4
    denominator = int(time_sig[1]) if isinstance(time_sig, list) and len(time_sig) == 2 else 4
    denominator_power = 0
    while (1 << denominator_power) < denominator and denominator_power < 8:
        denominator_power += 1

    program = int(defaults.get("program", 0))

    # Meta events at beginning of track.
    midi_events.append(MidiEvent(0, b"\xFF\x51\x03" + tempo_us_per_qn.to_bytes(3, "big")))
    midi_events.append(MidiEvent(0, bytes([0xFF, 0x58, 0x04, numerator, denominator_power, 24, 8])))
    midi_events.append(MidiEvent(0, bytes([0xC0, program & 0x7F])))

    pending_delta = 0

    for event in events:
        symbol = event.get("symbol", "REST")
        beats = float(event.get("beats", 1.0))
        beats = max(0.0, beats)
        duration_ticks = int(round(beats * ticks_per_beat))

        event_valence = clamp(float(event.get("valence", defaults.get("valence", 0.5))), 0.0, 1.0)
        event_arousal = clamp(float(event.get("arousal", defaults.get("arousal", 0.5))), 0.0, 1.0)

        if "tempo" in event:
            event_tempo = max(1.0, float(event["tempo"]))
            us_per_qn = int(60_000_000 / event_tempo)
            midi_events.append(MidiEvent(pending_delta, b"\xFF\x51\x03" + us_per_qn.to_bytes(3, "big")))
            pending_delta = 0

        if str(symbol).upper() == "REST":
            pending_delta += duration_ticks
            continue

        pitch = parse_pitch(symbol)
        pitch += valence_to_scale_shift(event_valence)
        pitch = int(clamp(pitch, 0, 127))

        base_velocity = int(event.get("velocity", defaults.get("velocity", 80)))
        velocity = valence_arousal_to_velocity(base_velocity, event_valence, event_arousal)

        note_on = bytes([0x90, pitch & 0x7F, velocity & 0x7F])
        note_off = bytes([0x80, pitch & 0x7F, 0x00])

        midi_events.append(MidiEvent(pending_delta, note_on))
        midi_events.append(MidiEvent(max(1, duration_ticks), note_off))
        pending_delta = 0

    midi_events.append(MidiEvent(pending_delta, b"\xFF\x2F\x00"))

    track_data = bytearray()
    for e in midi_events:
        track_data.extend(encode_variable_length(e.delta_ticks))
        track_data.extend(e.payload)

    return b"MTrk" + len(track_data).to_bytes(4, "big") + bytes(track_data)


def write_midi(data: dict[str, Any], output_path: Path) -> None:
    defaults = data.get("global", {})
    events = data.get("events", [])
    if not isinstance(events, list):
        raise ValueError("`events` must be a list")

    ticks_per_beat = int(defaults.get("ticks_per_beat", 480))
    if ticks_per_beat <= 0:
        raise ValueError("ticks_per_beat must be > 0")

    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + ticks_per_beat.to_bytes(2, "big")
    track = build_track(events, ticks_per_beat, defaults)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(header + track)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert symbols+properties JSON into MIDI")
    parser.add_argument("--input", required=True, help="Path to JSON input")
    parser.add_argument("--output", required=True, help="Output .mid path")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    write_midi(payload, Path(args.output))
    print(f"MIDI generated: {args.output}")


if __name__ == "__main__":
    main()
