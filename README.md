# AI Music Converters (Python)

This project contains two Python converters:

1. `symbols_to_midi.py`  
   Converts symbolic events + affective properties (valence, arousal, tempo, pitch) into a `.mid` file.
2. `midi_to_mp3.py`  
   Converts `.mid` to `.mp3` by synthesizing audio with `pretty_midi` then encoding with `ffmpeg`.

## 1) Symbols/Properties → MIDI

### Input JSON schema

```json
{
  "global": {
    "tempo": 120,
    "valence": 0.6,
    "arousal": 0.7,
    "ticks_per_beat": 480,
    "program": 0,
    "time_signature": [4, 4],
    "velocity": 80
  },
  "events": [
    {"symbol": "C4", "beats": 1, "valence": 0.8, "arousal": 0.6},
    {"symbol": "D4", "beats": 1, "tempo": 128},
    {"symbol": "REST", "beats": 0.5},
    {"symbol": "E4", "beats": 1.5}
  ]
}
```

### Run

```bash
python symbols_to_midi.py --input input.json --output output.mid
```

## 2) MIDI → MP3

### Install deps

```bash
pip install numpy scipy pretty_midi
```

Also install `ffmpeg` and ensure it is on your PATH.

### Run

```bash
python midi_to_mp3.py --input output.mid --output output.mp3
```

## Notes on rules mapping

In `symbols_to_midi.py` the mapping is heuristic and easy to adjust:
- `arousal` increases/decreases velocity strongly.
- `valence` slightly changes velocity and applies up/down semitone shift.
- Per-event `tempo` changes generate MIDI tempo meta events.
