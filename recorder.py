"""Supervise FFmpeg recording from Android IP Webcam."""
import logging
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import uuid

LOG = logging.getLogger("recorder")


def positive(name, default, kind=int):
    value = kind(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def command(output):
    video = os.environ["VIDEO_URL"]
    audio = os.environ["AUDIO_URL"]
    prefix = os.getenv("FILENAME_PREFIX", "")
    if prefix and not re.fullmatch(r"[A-Za-z0-9_-]+", prefix):
        raise ValueError("FILENAME_PREFIX must contain only ASCII letters, digits, '_' or '-'")
    prefix = prefix + "_" if prefix else ""
    seconds = positive("SEGMENT_SECONDS", 3600)
    timeout = str(int(positive("HTTP_TIMEOUT_SECONDS", 30) * 1_000_000))
    args = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "warning", "-n"]
    args += ["-thread_queue_size", "512", "-rw_timeout", timeout,
             "-use_wallclock_as_timestamps", "1", "-i", video]
    # WAV/PCM timing comes from sample counts. HTTP delivery can arrive in bursts;
    # assigning receive times to audio packets turns jitter into gaps/overlaps.
    args += ["-thread_queue_size", "512", "-rw_timeout", timeout, "-i", audio]
    args += ["-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
             # Clock boundaries can occur anywhere relative to input timestamps.
             # Frequent keyframes limit the delay before a boundary can be cut.
             "-tune", "zerolatency", "-force_key_frames", "expr:gte(t,n_forced*1)",
             "-c:a", "aac", "-b:a", "128k", "-af", "asetpts=N/SR/TB",
             "-f", "segment", "-segment_time", str(seconds),
             "-segment_atclocktime", "1",
             "-segment_format", "matroska", "-reset_timestamps", "1",
             "-strftime", "1",
             str(output / (prefix + "%Y-%m-%d_%H-%M-%S_" + uuid.uuid4().hex[:12] + ".mkv"))]
    return args


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    output = Path(os.getenv("OUTPUT_DIR", "/recordings"))
    retry = positive("RETRY_SECONDS", 10)
    minimum = positive("MIN_FREE_MB", 1024) * 1024 * 1024
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    # Validate before entering the retry loop; never log URLs containing credentials.
    command(output)
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not installed")
    while not stop.is_set():
        process = None
        try:
            output.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(output).free < minimum:
                raise OSError("Insufficient free space on recording volume")
            probe = output / (".write-probe-" + uuid.uuid4().hex)
            probe.write_bytes(b"")
            probe.unlink()
            LOG.info("Starting recording to %s", output)
            # FFmpeg errors can contain credential-bearing URLs; suppress its raw stderr.
            process = subprocess.Popen(command(output), stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while process.poll() is None and not stop.wait(1):
                pass
        except OSError as exc:
            LOG.error("Recording unavailable (%s)", type(exc).__name__)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                LOG.info("FFmpeg stopped (exit code %s)", process.returncode)
        if not stop.is_set():
            LOG.warning("Retrying in %s seconds; check camera, URLs, NFS and free space", retry)
            stop.wait(retry)
    LOG.info("Recorder stopped")


if __name__ == "__main__":
    main()
