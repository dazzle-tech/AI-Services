"""Play a WAV file into LiveVisitScribe like a browser microphone and print what comes back.

    python scripts/stream_wav.py ../ConvoVoiceAgent/services/ConvoScribe/samples/visit_sample.wav
    python scripts/stream_wav.py visit.wav --url ws://localhost:8037/api/v1/live --speed 2
    python scripts/stream_wav.py visit.wav --context '{"active_medications":["Lisinopril 10 mg"]}'

The file must be 16-bit PCM (mono or stereo, any sample rate). Needs the `websockets` package, which
`uvicorn[standard]` already installs. This script only talks to the live socket; it does not call
ConvoVoiceAgent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import wave

import websockets

CHUNK_SECONDS = 0.1


async def stream(args: argparse.Namespace) -> int:
    with wave.open(args.wav, "rb") as wav:
        if wav.getsampwidth() != 2:
            print("The WAV must be 16-bit PCM.", file=sys.stderr)
            return 2
        rate, channels = wav.getframerate(), wav.getnchannels()
        frames_per_chunk = int(rate * CHUNK_SECONDS)

        async with websockets.connect(args.url, max_size=None) as socket:
            start = {"type": "start", "sample_rate": rate, "channels": channels}
            if args.context:
                start["patient_context"] = json.loads(args.context)
            await socket.send(json.dumps(start))

            async def receive() -> None:
                async for raw in socket:
                    message = json.loads(raw)
                    kind = message["type"]
                    if kind == "segment":
                        mark = "final  " if message["final"] else "partial"
                        print(f"[{mark}] {message['id']} {message['speaker']:<7} {message['lang']:<5} "
                              f"{message['start_ms'] / 1000:6.1f}s  {message['text']}")
                    elif kind == "picked_up":
                        print("[picked up]", json.dumps({k: v for k, v in message.items() if k != "type"},
                                                        ensure_ascii=False))
                    elif kind == "final":
                        print(f"[final] {len(message['segments'])} lines, {message['audio_ms'] / 1000:.1f}s of audio")
                        picked = message.get("picked_up")
                        if picked is None:
                            print("[final] ERROR: picked_up missing from final payload", file=sys.stderr)
                        else:
                            print("[final picked_up]", json.dumps(picked, ensure_ascii=False))
                    else:
                        print(f"[{kind}]", json.dumps({k: v for k, v in message.items() if k != "type"},
                                                      ensure_ascii=False))

            reader = asyncio.create_task(receive())
            while True:
                chunk = wav.readframes(frames_per_chunk)
                if not chunk:
                    break
                await socket.send(chunk)
                if args.speed > 0:
                    await asyncio.sleep(CHUNK_SECONDS / args.speed)
            # a second of silence so the last line ends, then Stop like the UI does
            await socket.send(b"\x00\x00" * channels * rate)
            await socket.send(json.dumps({"type": "stop"}))
            await reader
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wav", help="16-bit PCM WAV file")
    parser.add_argument("--url", default="ws://localhost:8037/api/v1/live")
    parser.add_argument("--speed", type=float, default=1.0, help="1 = real time, 2 = twice as fast, 0 = no pacing")
    parser.add_argument("--context", help="patient_context as a JSON string")
    return asyncio.run(stream(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
