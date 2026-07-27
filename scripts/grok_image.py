#!/usr/bin/env python3
"""Generate an image through Grok Build's grok.com OAuth session."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional
from urllib.parse import quote

SUPPORTED_ASPECT_RATIOS = ("auto", "1:1", "16:9", "9:16", "4:3", "3:4")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class GenerationError(RuntimeError):
    pass


def build_agent_prompt(prompt: str, aspect_ratio: str) -> str:
    tool_args = json.dumps(
        {"prompt": prompt, "aspect_ratio": aspect_ratio},
        ensure_ascii=False,
    )
    return (
        "Use image_gen exactly once with these JSON arguments: "
        f"{tool_args}. Do not use web search or any other tool. "
        "After generation, return the generated image path."
    )


def build_command(prompt: str, aspect_ratio: str) -> list:
    return [
        "grok",
        "-p",
        build_agent_prompt(prompt, aspect_ratio),
        "--tools",
        "image_gen",
        "--disable-web-search",
        "--always-approve",
        "--output-format",
        "streaming-json",
    ]


def final_event(events_text: str) -> Dict[str, object]:
    result: Optional[Dict[str, object]] = None
    for line in events_text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "end":
            result = event
    if result is None:
        raise GenerationError("Grok returned no final JSON event")
    return result


def encoded_cwd(cwd: Path) -> str:
    return quote(str(cwd.resolve()), safe="")


def session_image_dir(cwd: Path, session_id: str, home: Optional[Path] = None) -> Path:
    base = home or Path.home()
    return base / ".grok" / "sessions" / encoded_cwd(cwd) / session_id / "images"


def image_files(directory: Path) -> Iterable[Path]:
    if not directory.is_dir():
        return []
    return (
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def newest_image(directory: Path) -> Path:
    images = list(image_files(directory))
    if not images:
        raise GenerationError(f"No generated image found in {directory}")
    return max(images, key=lambda path: (path.stat().st_mtime_ns, path.name))


def default_output() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / f"grok-image-{stamp}.jpg"


def generate(prompt: str, aspect_ratio: str, output: Path) -> Dict[str, object]:
    cwd = Path.cwd().resolve()
    env = os.environ.copy()
    env.pop("XAI_API_KEY", None)

    try:
        process = subprocess.run(
            build_command(prompt, aspect_ratio),
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise GenerationError("Grok Build CLI is not installed or not on PATH") from error

    event = final_event(process.stdout)
    if process.returncode != 0:
        detail = process.stderr.strip() or f"exit code {process.returncode}"
        raise GenerationError(f"Grok CLI failed: {detail}")
    if event.get("stopReason") != "EndTurn":
        raise GenerationError(f"Grok generation stopped: {event.get('stopReason', 'unknown')}")

    session_id = event.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        raise GenerationError("Grok returned no session ID")

    source = newest_image(session_image_dir(cwd, session_id))
    destination = output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination:
        shutil.copy2(source, destination)

    if not destination.is_file() or destination.stat().st_size == 0:
        raise GenerationError(f"Generated image was not saved to {destination}")

    return {
        "ok": True,
        "provider": "grok-build-oauth",
        "action": "generate",
        "output": str(destination),
        "session_id": session_id,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an image with Grok Build image_gen and grok.com OAuth."
    )
    parser.add_argument("prompt", help="Image prompt")
    parser.add_argument(
        "--aspect-ratio",
        default="auto",
        choices=SUPPORTED_ASPECT_RATIOS,
        help="Output aspect ratio (default: auto)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Destination image path (default: timestamped JPEG in the current directory)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.prompt.strip():
        print("Prompt must not be empty", file=sys.stderr)
        return 2

    try:
        result = generate(
            prompt=args.prompt,
            aspect_ratio=args.aspect_ratio,
            output=args.output or default_output(),
        )
    except GenerationError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
