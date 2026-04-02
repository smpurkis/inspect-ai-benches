#!/usr/bin/env python3
"""Generate test fixtures for the Whisper forced-alignment task.

Downloads the JFK inaugural address clip from the OpenAI Whisper test suite
(MIT licence) and creates two test cases with deliberately wrong timestamps.

Creates:
  - /app/test1.wav  — full JFK clip   (~11 s, 22 words, 16 kHz mono)
  - /app/test1_transcript.json         — transcript shifted +1.5 s
  - /app/test2.wav  — first sentence   (~8.3 s, 14 words, 16 kHz mono)
  - /app/test2_transcript.json         — transcript scaled 1.3× + shifted +0.5 s
  - /app/whisper_tiny.pt               — symlink to pre-downloaded model
"""
import json
import os
import subprocess

import librosa
import soundfile as sf

os.makedirs("/app", exist_ok=True)

SR = 16000

# ── Download JFK clip from Whisper's own test suite ──────────────────────
JFK_URL = "https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac"
subprocess.run(["curl", "-sL", "-o", "/tmp/jfk.flac", JFK_URL], check=True)

audio_full, _ = librosa.load("/tmp/jfk.flac", sr=SR, mono=True)

# ── Test case 1: full clip (~11 s, 22 words) ─────────────────────────────
sf.write("/app/test1.wav", audio_full, SR, subtype="PCM_16")

actual_times1 = [
    {"word": "And",       "start": 0.00, "end": 0.74},
    {"word": "so",        "start": 0.74, "end": 1.06},
    {"word": "my",        "start": 1.06, "end": 1.34},
    {"word": "fellow",    "start": 1.34, "end": 1.68},
    {"word": "Americans", "start": 1.68, "end": 2.30},
    {"word": "ask",       "start": 2.30, "end": 3.78},
    {"word": "not",       "start": 3.78, "end": 4.70},
    {"word": "what",      "start": 4.70, "end": 5.70},
    {"word": "your",      "start": 5.70, "end": 5.98},
    {"word": "country",   "start": 5.98, "end": 6.42},
    {"word": "can",       "start": 6.42, "end": 6.72},
    {"word": "do",        "start": 6.72, "end": 6.96},
    {"word": "for",       "start": 6.96, "end": 7.22},
    {"word": "you",       "start": 7.22, "end": 8.24},
    {"word": "ask",       "start": 8.24, "end": 8.62},
    {"word": "what",      "start": 8.62, "end": 8.98},
    {"word": "you",       "start": 8.98, "end": 9.22},
    {"word": "can",       "start": 9.22, "end": 9.42},
    {"word": "do",        "start": 9.42, "end": 9.70},
    {"word": "for",       "start": 9.70, "end": 9.88},
    {"word": "your",      "start": 9.88, "end": 10.12},
    {"word": "country",   "start": 10.12, "end": 10.52},
]

transcript1 = {
    "words": [
        {"word": w["word"], "start": round(w["start"] + 1.5, 3),
         "end": round(w["end"] + 1.5, 3)}
        for w in actual_times1
    ]
}
with open("/app/test1_transcript.json", "w") as f:
    json.dump(transcript1, f, indent=2)
with open("/app/.ground_truth_1.json", "w") as f:
    json.dump({"words": actual_times1}, f, indent=2)

# ── Test case 2: first sentence (~8.3 s, 14 words) ──────────────────────
cut_sample = int(8.3 * SR)
audio_part = audio_full[:cut_sample]
sf.write("/app/test2.wav", audio_part, SR, subtype="PCM_16")

actual_times2 = actual_times1[:14]   # "And" … "you"

transcript2 = {
    "words": [
        {"word": w["word"], "start": round(w["start"] * 1.3 + 0.5, 3),
         "end": round(w["end"] * 1.3 + 0.5, 3)}
        for w in actual_times2
    ]
}
with open("/app/test2_transcript.json", "w") as f:
    json.dump(transcript2, f, indent=2)
with open("/app/.ground_truth_2.json", "w") as f:
    json.dump({"words": actual_times2}, f, indent=2)

# ── Symlink model ────────────────────────────────────────────────────────
model_dir = "/app/whisper_models"
if os.path.isdir(model_dir):
    for fname in os.listdir(model_dir):
        if fname.endswith(".pt"):
            os.symlink(os.path.join(model_dir, fname), "/app/whisper_tiny.pt")
            break

os.remove("/tmp/jfk.flac")
print("Whisper fixtures generated (JFK inaugural address).")
