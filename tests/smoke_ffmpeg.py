"""Run inside the built image: python /tmp/smoke_ffmpeg.py."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

import recorder

os.environ.update(VIDEO_URL="http://unused/video", AUDIO_URL="http://unused/audio.wav",
                  SEGMENT_SECONDS="2")
with tempfile.TemporaryDirectory() as folder:
    args = recorder.command(Path(folder))
    # Use real-time generated inputs; keep the production encoder/muxer options.
    options = args[args.index("-map"):]
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                    "-re", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10",
                    "-re", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                    "-t", "5", *options], check=True, timeout=30)
    files = sorted(Path(folder).glob("*.mkv"))
    # Start phase relative to wall-clock boundaries changes the first/last lengths.
    assert 3 <= len(files) <= 4, files
    for path in files:
        data = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]))
        assert {s["codec_name"] for s in data["streams"]} == {"h264", "aac"}, data
        assert 0 < float(data["format"]["duration"]) < 3.5, data
    print("PASS: playable H.264/AAC segments cut at wall-clock intervals")
