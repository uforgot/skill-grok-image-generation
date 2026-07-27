#!/usr/bin/env python3
"""Generate an image through Grok Build's grok.com OAuth session."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote

SUPPORTED_ASPECT_RATIOS = ("auto", "1:1", "16:9", "9:16", "4:3", "3:4")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_PATH_PATTERN = re.compile(
    r"(?<![\w./-])(images/[A-Za-z0-9._/-]+\.(?:jpe?g|png|webp))",
    re.IGNORECASE,
)


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


def parsed_events(events_text: str) -> Iterable[Dict[str, object]]:
    for line in events_text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def final_event(events_text: str) -> Dict[str, object]:
    result: Optional[Dict[str, object]] = None
    for event in parsed_events(events_text):
        if event.get("type") == "end":
            result = event
    if result is None:
        raise GenerationError("Grok returned no final JSON event")
    return result


def event_image_paths(events_text: str) -> List[PurePosixPath]:
    output_text = "".join(
        str(event.get("data", ""))
        for event in parsed_events(events_text)
        if event.get("type") == "text"
    )
    paths: List[PurePosixPath] = []
    for match in IMAGE_PATH_PATTERN.finditer(output_text):
        candidate = PurePosixPath(match.group(1))
        if candidate.is_absolute() or ".." in candidate.parts:
            continue
        if not candidate.parts or candidate.parts[0] != "images":
            continue
        if candidate not in paths:
            paths.append(candidate)
    return paths


def encoded_cwd(cwd: Path) -> str:
    return quote(str(cwd.resolve()), safe="")


def session_dir(cwd: Path, session_id: str, home: Optional[Path] = None) -> Path:
    base = home or Path.home()
    return base / ".grok" / "sessions" / encoded_cwd(cwd) / session_id


def session_image_dir(cwd: Path, session_id: str, home: Optional[Path] = None) -> Path:
    return session_dir(cwd, session_id, home) / "images"


def image_files(directory: Path) -> Iterable[Path]:
    if not directory.is_dir():
        return []
    return (
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def resolve_source_image(
    cwd: Path,
    session_id: str,
    events_text: str,
    home: Optional[Path] = None,
) -> Path:
    root = session_dir(cwd, session_id, home).resolve()
    event_matches: List[Path] = []

    for relative in event_image_paths(events_text):
        candidate = root.joinpath(*relative.parts).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES:
            event_matches.append(candidate)

    unique_matches = list(dict.fromkeys(event_matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    if len(unique_matches) > 1:
        raise GenerationError(
            f"Grok reported multiple generated images for session {session_id}"
        )

    session_matches = list(image_files(root / "images"))
    if len(session_matches) == 1:
        return session_matches[0]
    if not session_matches:
        raise GenerationError(f"No generated image found for session {session_id}")
    raise GenerationError(
        f"Generated image is ambiguous for session {session_id}: "
        f"{len(session_matches)} files"
    )


def output_path_for_source(requested: Path, source: Path) -> Path:
    destination = requested.expanduser().resolve()
    if destination.suffix.lower() != source.suffix.lower():
        destination = (
            destination.with_suffix(source.suffix)
            if destination.suffix
            else Path(f"{destination}{source.suffix}")
        )
    return destination


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_verified(source: Path, requested: Path) -> Dict[str, object]:
    destination = output_path_for_source(requested, source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_hash = sha256_file(source)

    if source.resolve() != destination:
        temporary: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=str(destination.parent),
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temporary = Path(temp_file.name)
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
            temporary = None
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    if not destination.is_file() or destination.stat().st_size == 0:
        raise GenerationError(f"Generated image was not saved to {destination}")
    destination_hash = sha256_file(destination)
    if source_hash != destination_hash:
        raise GenerationError(f"Generated image hash mismatch at {destination}")

    return {
        "output": str(destination),
        "extension": source.suffix.lower(),
        "sha256": destination_hash,
        "bytes": destination.stat().st_size,
    }


def default_output() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / f"grok-image-{stamp}"


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

    source = resolve_source_image(cwd, session_id, process.stdout)
    copied = copy_verified(source, output)

    return {
        "ok": True,
        "provider": "grok-build-oauth",
        "action": "generate",
        **copied,
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
        help=(
            "Destination path; the generated format's extension is preserved "
            "(default: timestamped file in the current directory)"
        ),
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
