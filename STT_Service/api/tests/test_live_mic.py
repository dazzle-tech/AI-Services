"""Manual test/debug client for the Radiology STT service.

Three modes:

  file        Send an existing audio file to /api/v1/transcribe.
  record      Record N seconds from the default microphone, save a WAV, then upload it.
  stream      Open the /api/v1/ws/transcribe WebSocket, stream live mic audio, print partials,
              and a final result.

Requires:
    pip install sounddevice soundfile websockets requests numpy

Examples:
    python test_live_mic.py file --path sample_audio/chest_ct.wav
    python test_live_mic.py record --seconds 12 --out my_recording.wav
    python test_live_mic.py stream --seconds 20

Override server location with --base-url / --ws-url.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import numpy as np
import requests

try:
    import sounddevice as sd
except ImportError:
    sd = None
try:
    import soundfile as sf
except ImportError:
    sf = None

DEFAULT_BASE = "http://localhost:8027"
DEFAULT_WS = "ws://localhost:8027/api/v1/ws/transcribe"
SR = 16000


def _need(module, name):
    if module is None:
        sys.exit(f"This mode requires `{name}`. Install with: pip install {name}")


# ---------------- file upload ---------------------------------------------

def cmd_file(args: argparse.Namespace) -> None:
    p = Path(args.path)
    if not p.exists():
        sys.exit(f"File not found: {p}")
    url = f"{args.base_url.rstrip('/')}/api/v1/transcribe"
    print(f"[file] POST {url}  ({p.name}, {p.stat().st_size} bytes)")
    with p.open("rb") as f:
        files = {"file": (p.name, f, "application/octet-stream")}
        data = {"language": args.language, "include_raw_text": "true", "beam_size": str(args.beam_size)}
        if args.extra_prompt:
            data["extra_prompt"] = args.extra_prompt
        t0 = time.perf_counter()
        r = requests.post(url, files=files, data=data, timeout=600)
    print(f"[file] status={r.status_code}  elapsed={time.perf_counter()-t0:.2f}s")
    try:
        j = r.json()
    except Exception:
        print(r.text)
        return
    _print_result(j)


# ---------------- record + upload -----------------------------------------

def cmd_record(args: argparse.Namespace) -> None:
    _need(sd, "sounddevice")
    _need(sf, "soundfile")
    out = Path(args.out)
    print(f"[record] Recording {args.seconds}s @ {SR} Hz mono... speak now.")
    audio = sd.rec(int(args.seconds * SR), samplerate=SR, channels=1, dtype="int16")
    sd.wait()
    sf.write(str(out), audio, SR, subtype="PCM_16")
    print(f"[record] Saved {out} ({out.stat().st_size} bytes). Uploading...")
    args.path = str(out)
    cmd_file(args)


# ---------------- WS streaming --------------------------------------------

async def _stream(args: argparse.Namespace) -> None:
    _need(sd, "sounddevice")
    try:
        import websockets
    except ImportError:
        sys.exit("This mode requires `websockets`. Install with: pip install websockets")

    queue: asyncio.Queue[bytes] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _callback(indata, frames, time_info, status):
        if status:
            print(f"[stream] sounddevice status: {status}", file=sys.stderr)
        # indata is int16 since we set dtype below
        loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

    print(f"[stream] Connecting to {args.ws_url}")
    async with websockets.connect(args.ws_url, max_size=None) as ws:
        # Drain server hello
        try:
            hello = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f"[stream] <- {hello}")
        except asyncio.TimeoutError:
            pass

        start_msg = {"type": "start", "sample_rate": SR, "channels": 1, "language": args.language}
        if args.extra_prompt:
            start_msg["extra_prompt"] = args.extra_prompt
        await ws.send(json.dumps(start_msg))
        ready = await ws.recv()
        print(f"[stream] <- {ready}")

        stream_obj = sd.RawInputStream(
            samplerate=SR, channels=1, dtype="int16",
            blocksize=int(SR * 0.2),  # 200 ms frames
            callback=_callback,
        )
        stop_at = time.monotonic() + args.seconds
        print(f"[stream] Recording + streaming for {args.seconds}s... speak now.")
        with stream_obj:
            async def _sender():
                while time.monotonic() < stop_at:
                    try:
                        buf = await asyncio.wait_for(queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    await ws.send(buf)

            async def _receiver():
                while True:
                    msg = await ws.recv()
                    try:
                        j = json.loads(msg)
                    except Exception:
                        print(f"[stream] <- {msg}")
                        continue
                    t = j.get("type")
                    if t == "partial":
                        print(f"[partial @ {j.get('audio_seconds_processed', 0):.1f}s] {j.get('text','')}")
                    elif t == "final":
                        print("\n========== FINAL ==========")
                        print(j.get("text", ""))
                        print("===========================\n")
                        return
                    elif t == "error":
                        print(f"[stream][error] {j.get('detail')}")
                        return
                    else:
                        print(f"[stream] <- {j}")

            sender_task = asyncio.create_task(_sender())
            receiver_task = asyncio.create_task(_receiver())
            await sender_task
            await ws.send(json.dumps({"type": "stop"}))
            try:
                await asyncio.wait_for(receiver_task, timeout=120)
            except asyncio.TimeoutError:
                print("[stream] Timed out waiting for final result.")


def cmd_stream(args: argparse.Namespace) -> None:
    asyncio.run(_stream(args))


# ---------------- utils ---------------------------------------------------

def _print_result(j: dict) -> None:
    if "text" in j:
        print("---- transcription ----")
        print(j["text"])
        print("-----------------------")
        if j.get("raw_text") and j["raw_text"] != j["text"]:
            print("(raw, pre-postprocess):")
            print(j["raw_text"])
            print("-----------------------")
        print(f"language={j.get('language')}  prob={j.get('language_probability')}  "
              f"audio={j.get('audio_duration_seconds')}s  inference={j.get('inference_seconds')}s  "
              f"model={j.get('model')}  device={j.get('device')}")
    else:
        print(json.dumps(j, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=DEFAULT_BASE, help=f"REST base URL (default: {DEFAULT_BASE})")
    ap.add_argument("--ws-url", default=DEFAULT_WS, help=f"WebSocket URL (default: {DEFAULT_WS})")
    ap.add_argument("--language", default="en")
    ap.add_argument("--extra-prompt", default=None,
                    help='Optional case context, e.g. "Chest CT in a 58M with smoking history."')
    ap.add_argument("--beam-size", type=int, default=5)

    sub = ap.add_subparsers(dest="mode", required=True)

    sp = sub.add_parser("file", help="Upload an existing audio file.")
    sp.add_argument("--path", required=True, help="Path to audio file (wav/mp3/m4a/webm/ogg/flac).")
    sp.set_defaults(func=cmd_file)

    sp = sub.add_parser("record", help="Record from mic to WAV, then upload.")
    sp.add_argument("--seconds", type=float, default=10.0)
    sp.add_argument("--out", default="recorded.wav")
    sp.set_defaults(func=cmd_record)

    sp = sub.add_parser("stream", help="Live mic -> WebSocket streaming.")
    sp.add_argument("--seconds", type=float, default=15.0)
    sp.set_defaults(func=cmd_stream)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
