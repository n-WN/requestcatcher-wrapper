#!/usr/bin/env python3

import argparse
import asyncio
import json
import random
import string
import sys
from datetime import datetime
from typing import Any, Dict

import websockets


def generate_prefix(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def format_request(req: Dict[str, Any]) -> str:
    time_str = req.get("time") or ""
    try:
        # Normalize time format if possible
        if time_str:
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            time_str = dt.isoformat()
    except Exception:
        pass

    host = req.get("host", "")
    method = req.get("method", "")
    path = req.get("path", "")
    remote = req.get("remote_addr", "")
    content_length = req.get("content_length", 0)

    first_line = f"[{time_str}] {method} {path} (host={host}, from={remote}, len={content_length})"

    headers = req.get("headers") or {}
    headers_lines = []
    for k, v in headers.items():
        # Each header value is a list according to the backend model
        if isinstance(v, list):
            value_str = ", ".join(str(x) for x in v)
        else:
            value_str = str(v)
        headers_lines.append(f"{k}: {value_str}")
    headers_block = "\n".join(headers_lines)

    body = req.get("body") or ""
    # Trim very long bodies for terminal readability
    max_body_len = 2000
    if len(body) > max_body_len:
        body = body[:max_body_len] + "\n...[truncated]..."

    parts = [first_line]
    if headers_block:
        parts.append("Headers:")
        parts.append(headers_block)
    if body:
        parts.append("Body:")
        parts.append(body)
    return "\n".join(parts)


async def watch_catcher(prefix: str) -> None:
    url = f"wss://{prefix}.requestcatcher.com/init-client"
    print(f"Listening on https://{prefix}.requestcatcher.com/")
    print(f"Connecting to {url} for live requests...\n")

    while True:
        try:
            async with websockets.connect(url) as ws:
                print("Connected. Waiting for requests...\n")
                async for message in ws:
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        print(f"[raw] {message}")
                        continue

                    print("=" * 80)
                    print(format_request(data))
                    print("=" * 80 + "\n")
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nInterrupted, exiting.")
            return
        except Exception as exc:
            print(f"Connection error: {exc!r}", file=sys.stderr)
            print("Reconnecting in 3 seconds...\n", file=sys.stderr)
            await asyncio.sleep(3)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CLI wrapper for requestcatcher.com to watch incoming requests reliably."
    )
    parser.add_argument(
        "--prefix",
        "-p",
        help="Subdomain prefix to use (default: random).",
    )
    parser.add_argument(
        "--length",
        "-l",
        type=int,
        default=8,
        help="Random prefix length when not specifying --prefix (default: 8).",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    prefix = args.prefix or generate_prefix(args.length)
    try:
        asyncio.run(watch_catcher(prefix))
    except KeyboardInterrupt:
        print("\nExiting.")


if __name__ == "__main__":
    main()

