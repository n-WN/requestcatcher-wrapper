import argparse
import asyncio
import json
import os
import random
import re
import string
import sys
from datetime import datetime
from typing import Any, Dict, Optional

import websockets


def generate_prefix(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _highlight_text(text: str, needle: Optional[str]) -> str:
    if not needle or not _supports_color():
        return text

    pattern = re.escape(needle)
    regex = re.compile(pattern, re.IGNORECASE)
    start = "\033[1;31m"
    end = "\033[0m"
    return regex.sub(lambda m: f"{start}{m.group(0)}{end}", text)


def format_request(req: Dict[str, Any]) -> str:
    time_str = req.get("time") or ""
    try:
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
        if isinstance(v, list):
            value_str = ", ".join(str(x) for x in v)
        else:
            value_str = str(v)
        headers_lines.append(f"{k}: {value_str}")
    headers_block = "\n".join(headers_lines)

    body = req.get("body") or ""
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


async def watch_catcher(
    prefix: str,
    highlight: Optional[str] = None,
    log_file: Optional[str] = None,
    quiet: bool = False,
) -> None:
    url = f"wss://{prefix}.requestcatcher.com/init-client"

    log_fp = None
    if log_file:
        log_fp = open(log_file, "a", encoding="utf-8")

    def _stdout(line: str) -> None:
        if not quiet:
            print(line)

    def _log(line: str) -> None:
        if log_fp:
            log_fp.write(line + "\n")
            log_fp.flush()

    def _both(line: str) -> None:
        _stdout(line)
        _log(line)

    _both(f"Listening on https://{prefix}.requestcatcher.com/")
    _both(f"Connecting to {url} for live requests...\n")

    while True:
        try:
            async with websockets.connect(url) as ws:
                _both("Connected. Waiting for requests...\n")
                async for message in ws:
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        _both(f"[raw] {message}")
                        continue

                    plain = format_request(data)
                    block = "=" * 80 + "\n" + plain + "\n" + "=" * 80 + "\n"

                    highlighted = _highlight_text(block, highlight)
                    _stdout(highlighted)
                    _log(block.rstrip("\n"))
        except (KeyboardInterrupt, asyncio.CancelledError):
            _stdout("\nInterrupted, exiting.")
            _log("Interrupted, exiting.")
            break
        except Exception as exc:
            msg = f"Connection error: {exc!r}"
            _stdout(msg)
            _log(msg)
            retry = "Reconnecting in 3 seconds...\n"
            _stdout(retry)
            _log(retry.strip())
            await asyncio.sleep(3)
    if log_fp:
        log_fp.close()


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
    parser.add_argument(
        "--match",
        "-m",
        help="Highlight occurrences of this text in the output (case-insensitive).",
    )
    parser.add_argument(
        "--background",
        "-b",
        action="store_true",
        help=(
            "Background-friendly mode: only print URL and log path; "
            "all request details are written to a log file."
        ),
    )
    parser.add_argument(
        "--log-file",
        help=(
            "Log file path when using --background. "
            "Default: ./rcw-<prefix>.log"
        ),
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    prefix = args.prefix or generate_prefix(args.length)

    log_file: Optional[str] = args.log_file
    if args.background and not log_file:
        log_file = f"rcw-{prefix}.log"

    if args.background:
        pid = os.getpid()
        print(f"Background mode enabled for prefix: {prefix}")
        print(f"Listening on: https://{prefix}.requestcatcher.com/")
        if log_file:
            print(f"Logging all requests to: {log_file}")
            print(f"View logs with: tail -f {log_file}")
        print(f"Process PID: {pid}  (stop with: kill {pid})")
        print()

    try:
        asyncio.run(
            watch_catcher(
                prefix,
                highlight=args.match,
                log_file=log_file,
                quiet=args.background,
            )
        )
    except KeyboardInterrupt:
        print("\nExiting.")
