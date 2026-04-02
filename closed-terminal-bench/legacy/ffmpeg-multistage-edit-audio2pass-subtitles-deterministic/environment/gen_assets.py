#!/usr/bin/env python3
"""Download and prepare test assets for the ffmpeg multistage pipeline task.

Downloads real video/audio from samplelib.com (no license restrictions),
generates a small watermark PNG, and writes config files.
"""
import json
import subprocess
import os

os.makedirs("/app", exist_ok=True)

# ---------- Download real video and audio assets ----------
DOWNLOADS = {
    "/app/camA.mp4": "https://download.samplelib.com/mp4/sample-10s.mp4",
    "/app/camB.mp4": "https://download.samplelib.com/mp4/sample-5s.mp4",
    "/app/narration.wav": "https://download.samplelib.com/wav/sample-12s.wav",
}

for dest, url in DOWNLOADS.items():
    print(f"Downloading {dest} ...")
    subprocess.run(
        ["curl", "-sL", "--fail", "-o", dest, url],
        check=True, timeout=120,
    )

# ---------- Generate watermark.png (small utility image) ----------
subprocess.run([
    "ffmpeg", "-y",
    "-f", "lavfi", "-i",
    "color=c=white@0.5:s=120x40:d=1,format=rgba,"
    "drawtext=text='WATERMARK':fontsize=18:fontcolor=black:x=5:y=10",
    "-frames:v", "1",
    "/app/watermark.png"
], check=True, capture_output=True)

# ---------- Write captions.srt ----------
srt = """\
1
00:00:01,000 --> 00:00:03,500
This is the first caption segment.

2
00:00:04,000 --> 00:00:06,500
Here comes the second segment.

3
00:00:07,000 --> 00:00:09,000
And the third, final segment.
"""
with open("/app/captions.srt", "w") as f:
    f.write(srt)

# ---------- Write ffmpeg_spec.json ----------
spec = {
    "normalize": {
        "target_fps": 30,
        "width": 1280,
        "height": 720,
        "pix_fmt": "yuv420p",
        "colorspace": "bt709"
    },
    "segments": [
        {"source": "camA", "start_ms": 500, "end_ms": 4500},
        {"source": "camB", "start_ms": 1000, "end_ms": 4000}
    ],
    "crossfade_duration_s": 0.50,
    "loudnorm": {
        "target_lufs": -16,
        "target_tp": -1.5,
        "target_lra": 11
    },
    "audio_mix": {
        "camera_gain_db": -6,
        "narration_gain_db": 0
    },
    "subtitle": {
        "offset_ms": 0,
        "font_size": 24,
        "margin_v": 30
    },
    "watermark": {
        "x": "W-w-20",
        "y": "20",
        "fade_in_s": 0.5,
        "fade_out_s": 0.5,
        "opacity": 0.7
    },
    "encode": {
        "codec": "libx264",
        "crf": 23,
        "preset": "medium",
        "gop": 60,
        "scenecut": 0,
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "audio_channels": 2
    }
}
with open("/app/ffmpeg_spec.json", "w") as f:
    json.dump(spec, f, indent=2)

print("All assets ready.")
