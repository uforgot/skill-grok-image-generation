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
LOGIN_CONFIRMATION = "You are logged in with grok.com."
IMAGE_PATH_PATTERN = re.compile(
    r"(?<![\w./-])(images/[A-Za-z0-9._/-]+\.(?:jpe?g|png|webp))",
    re.IGNORECASE,
)
MODERATION_MARKERS = (
    "moderation",
    "content policy",
    "safety policy",
    "safety block",
    "request blocked",
    "respect_moderation=false",
)
FAILURE_REASON_LABELS = {
    "oauth_invalid": "인증 만료",
    "permission_cancelled": "권한 취소",
    "timeout": "timeout",
    "moderation_blocked": "moderation",
}


def user_failure_message(code: str, next_action: str, action: str) -> str:
    activity = "편집" if action == "edit" else "생성"
    reason = FAILURE_REASON_LABELS.get(code, "기타")
    return (
        f"Grok OAuth 이미지 {activity} 실패 — 원인: {reason}. "
        f"자동 fallback은 실행하지 않았어. 다음 행동: {next_action}"
    )


class GenerationError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        next_action: str,
        exit_code: int,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_action = next_action
        self.exit_code = exit_code

    def payload(self, action: str = "generate") -> Dict[str, object]:
        return {
            "ok": False,
            "provider": "grok-build-oauth",
            "action": action,
            "error": self.code,
            "message": self.message,
            "fallback_used": False,
            "next_action": self.next_action,
            "user_message": user_failure_message(
                self.code, self.next_action, action
            ),
        }


def error(
    code: str,
    message: str,
    next_action: str,
    exit_code: int,
) -> GenerationError:
    return GenerationError(code, message, next_action, exit_code)


def oauth_environment() -> Dict[str, str]:
    env = os.environ.copy()
    env.pop("XAI_API_KEY", None)
    return env


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


def build_edit_agent_prompt(
    prompt: str,
    image: Path,
    aspect_ratio: Optional[str] = None,
) -> str:
    tool_args = {"prompt": prompt, "image": str(image.resolve())}
    if aspect_ratio is not None:
        tool_args["aspect_ratio"] = aspect_ratio
    encoded_args = json.dumps(tool_args, ensure_ascii=False)
    return (
        "Use image_edit exactly once with these JSON arguments: "
        f"{encoded_args}. Use the image as the source reference, apply only the "
        "requested change, and preserve everything the prompt does not ask to change. "
        "Do not use web search or any other tool. After editing, return the edited image path."
    )


def tool_command(tool: str, agent_prompt: str) -> list:
    return [
        "grok",
        "-p",
        agent_prompt,
        "--tools",
        tool,
        "--disable-web-search",
        "--always-approve",
        "--output-format",
        "streaming-json",
    ]


def build_command(prompt: str, aspect_ratio: str) -> list:
    return tool_command("image_gen", build_agent_prompt(prompt, aspect_ratio))


def build_edit_command(
    prompt: str,
    image: Path,
    aspect_ratio: Optional[str] = None,
) -> list:
    return tool_command(
        "image_edit",
        build_edit_agent_prompt(prompt, image, aspect_ratio),
    )


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
        raise error(
            "empty_response",
            "Grok OAuth 이미지 생성 응답이 비어 있거나 완료 이벤트가 없어.",
            "잠시 후 다시 시도하고, 반복되면 Grok Build 상태를 확인해 줘.",
            5,
        )
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
        raise error(
            "ambiguous_output",
            f"Grok 세션 {session_id}에 생성 결과가 여러 개라 하나를 고를 수 없어.",
            "한 번에 이미지 하나만 생성하도록 다시 요청해 줘.",
            7,
        )

    session_matches = list(image_files(root / "images"))
    if len(session_matches) == 1:
        return session_matches[0]
    if not session_matches:
        raise error(
            "output_missing",
            f"Grok 세션 {session_id}에서 생성된 이미지 파일을 찾지 못했어.",
            "다시 시도하고, 반복되면 Grok Build 세션 디렉터리를 확인해 줘.",
            7,
        )
    raise error(
        "ambiguous_output",
        f"Grok 세션 {session_id}에 이미지가 {len(session_matches)}개 있어 결과가 모호해.",
        "한 번에 이미지 하나만 생성하도록 다시 요청해 줘.",
        7,
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
        except OSError as copy_error:
            raise error(
                "copy_failed",
                f"생성 이미지를 요청 경로로 복사하지 못했어: {copy_error}",
                "출력 디렉터리의 쓰기 권한과 남은 용량을 확인해 줘.",
                7,
            ) from copy_error
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    if not destination.is_file() or destination.stat().st_size == 0:
        raise error(
            "output_missing",
            f"복사된 이미지가 없거나 비어 있어: {destination}",
            "출력 경로의 쓰기 권한과 남은 용량을 확인해 줘.",
            7,
        )
    destination_hash = sha256_file(destination)
    if source_hash != destination_hash:
        destination.unlink(missing_ok=True)
        raise error(
            "hash_mismatch",
            f"복사된 이미지의 hash가 원본과 달라: {destination}",
            "파일 시스템 상태를 확인한 뒤 다시 시도해 줘.",
            7,
        )

    return {
        "output": str(destination),
        "extension": source.suffix.lower(),
        "sha256": destination_hash,
        "bytes": destination.stat().st_size,
    }


def validate_source_image(image: Path) -> Path:
    source = image.expanduser().resolve()
    if not source.is_file():
        raise error(
            "invalid_source",
            f"편집할 source image를 찾지 못했어: {source}",
            "읽을 수 있는 로컬 이미지 경로를 `--image`로 지정해 줘.",
            2,
        )
    if source.suffix.lower() not in IMAGE_SUFFIXES or source.stat().st_size == 0:
        raise error(
            "invalid_source",
            f"지원하지 않거나 비어 있는 source image야: {source}",
            "JPEG, PNG, WebP 형식의 이미지 한 개를 지정해 줘.",
            2,
        )
    try:
        with source.open("rb") as source_file:
            header = source_file.read(12)
    except OSError as read_error:
        raise error(
            "invalid_source",
            f"source image를 읽지 못했어: {read_error}",
            "파일 읽기 권한을 확인해 줘.",
            2,
        ) from read_error
    valid_signature = (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    )
    if not valid_signature:
        raise error(
            "invalid_source",
            f"source file이 유효한 JPEG, PNG, WebP 이미지가 아니야: {source}",
            "손상되지 않은 이미지 파일을 지정해 줘.",
            2,
        )
    return source


def default_output(action: str = "generate") -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = "grok-edit" if action == "edit" else "grok-image"
    return Path.cwd() / f"{prefix}-{stamp}"


def activity_name(action: str) -> str:
    return "편집" if action == "edit" else "생성"


def run_command(
    command: List[str],
    cwd: Path,
    env: Dict[str, str],
    timeout: int,
    action: str = "generate",
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as timeout_error:
        raise error(
            "timeout",
            f"Grok OAuth 이미지 {activity_name(action)}이 {timeout}초 안에 끝나지 않았어.",
            "잠시 후 다시 시도하거나 `--timeout` 값을 늘려 줘.",
            6,
        ) from timeout_error


def preflight_oauth(
    cwd: Path,
    env: Dict[str, str],
    timeout: int,
    action: str = "generate",
) -> None:
    if shutil.which("grok") is None:
        raise error(
            "grok_not_installed",
            "Grok Build CLI를 찾지 못했어.",
            "Grok Build를 설치하고 `grok --version`을 확인해 줘.",
            3,
        )
    process = run_command(
        ["grok", "models"], cwd, env, min(timeout, 15), action
    )
    output = f"{process.stdout}\n{process.stderr}"
    if process.returncode != 0 or LOGIN_CONFIRMATION not in output:
        raise error(
            "oauth_invalid",
            "Grok OAuth 로그인이 없거나 만료됐어.",
            "`grok login`으로 로그인한 뒤 다시 요청해 줘.",
            3,
        )


def moderation_detected(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in MODERATION_MARKERS)


def process_failure(
    process: subprocess.CompletedProcess,
    action: str = "generate",
) -> GenerationError:
    combined = f"{process.stdout}\n{process.stderr}"
    if moderation_detected(combined):
        return error(
            "moderation_blocked",
            f"Grok 안전 정책 때문에 이미지 {activity_name(action)}이 차단됐어.",
            "차단을 우회하지 말고 다른 안전한 방향으로 프롬프트를 수정해 줘.",
            5,
        )
    detail = process.stderr.strip() or f"exit code {process.returncode}"
    return error(
        "provider_error",
        f"Grok 이미지 {activity_name(action)} 요청이 실패했어: {detail}",
        "Grok Build 상태를 확인하고 다시 시도해 줘.",
        5,
    )


def execute_image_action(
    action: str,
    command: List[str],
    output: Path,
    timeout: int,
) -> Dict[str, object]:
    cwd = Path.cwd().resolve()
    env = oauth_environment()
    preflight_oauth(cwd, env, timeout, action)

    process = run_command(command, cwd, env, timeout, action)
    if process.returncode != 0:
        raise process_failure(process, action)
    if moderation_detected(f"{process.stdout}\n{process.stderr}"):
        raise process_failure(process, action)

    event = final_event(process.stdout)
    stop_reason = event.get("stopReason")
    if stop_reason == "Cancelled":
        raise error(
            "permission_cancelled",
            "Grok 이미지 도구 실행이 취소됐어. 권한 승인이 실패했을 가능성이 있어.",
            "headless 실행의 승인 설정을 확인한 뒤 다시 시도해 줘.",
            4,
        )
    if stop_reason != "EndTurn":
        raise error(
            "provider_error",
            f"Grok 이미지 {activity_name(action)}이 비정상 종료됐어: "
            f"{stop_reason or 'unknown'}.",
            "Grok Build 상태를 확인하고 다시 시도해 줘.",
            5,
        )

    session_id = event.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        raise error(
            "empty_response",
            "Grok 응답에 session ID가 없어 결과를 확인할 수 없어.",
            "다시 시도하고, 반복되면 Grok Build를 업데이트해 줘.",
            5,
        )

    source = resolve_source_image(cwd, session_id, process.stdout)
    copied = copy_verified(source, output)

    return {
        "ok": True,
        "provider": "grok-build-oauth",
        "action": action,
        **copied,
        "session_id": session_id,
    }


def generate(
    prompt: str,
    aspect_ratio: str,
    output: Path,
    timeout: int = 180,
) -> Dict[str, object]:
    return execute_image_action(
        "generate",
        build_command(prompt, aspect_ratio),
        output,
        timeout,
    )


def edit_image(
    prompt: str,
    image: Path,
    output: Path,
    aspect_ratio: Optional[str] = None,
    timeout: int = 180,
) -> Dict[str, object]:
    source = validate_source_image(image)
    requested = output.expanduser().resolve()
    possible_outputs = {requested}
    for suffix in IMAGE_SUFFIXES:
        possible_outputs.add(
            requested.with_suffix(suffix)
            if requested.suffix
            else Path(f"{requested}{suffix}")
        )
    if source in possible_outputs:
        raise error(
            "invalid_output",
            "편집 결과 경로가 source image와 같아 원본을 덮어쓸 수 있어.",
            "원본과 다른 `--output` 경로를 지정해 줘.",
            2,
        )
    return execute_image_action(
        "edit",
        build_edit_command(prompt, source, aspect_ratio),
        output,
        timeout,
    )


def aspect_ratio(value: str) -> str:
    if value not in SUPPORTED_ASPECT_RATIOS:
        supported = ", ".join(SUPPORTED_ASPECT_RATIOS)
        raise argparse.ArgumentTypeError(
            f"지원하지 않는 aspect ratio '{value}'. 지원 값: {supported}"
        )
    return value


def positive_timeout(value: str) -> int:
    try:
        timeout = int(value)
    except ValueError as value_error:
        raise argparse.ArgumentTypeError("timeout은 초 단위 정수여야 해") from value_error
    if timeout < 1:
        raise argparse.ArgumentTypeError("timeout은 1초 이상이어야 해")
    return timeout


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("prompt", help="Image prompt")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Destination path; the generated format's extension is preserved",
    )
    parser.add_argument(
        "--timeout",
        type=positive_timeout,
        default=180,
        help="Maximum Grok execution time in seconds (default: 180)",
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] not in {"generate", "edit", "-h", "--help"}:
        arguments.insert(0, "generate")

    parser = argparse.ArgumentParser(
        description="Generate or edit images with Grok Build and grok.com OAuth."
    )
    commands = parser.add_subparsers(dest="action", required=True)

    generate_parser = commands.add_parser("generate", help="Generate a new image")
    add_common_arguments(generate_parser)
    generate_parser.add_argument(
        "--aspect-ratio",
        default="auto",
        type=aspect_ratio,
        help="Output aspect ratio (default: auto)",
    )

    edit_parser = commands.add_parser("edit", help="Edit one local source image")
    add_common_arguments(edit_parser)
    edit_parser.add_argument(
        "--image",
        type=Path,
        required=True,
        help="One local JPEG, PNG, or WebP source image",
    )
    edit_parser.add_argument(
        "--aspect-ratio",
        type=aspect_ratio,
        help="Optional output ratio; omit to preserve the source ratio",
    )
    return parser.parse_args(arguments)


def emit_error(generation_error: GenerationError, action: str) -> None:
    print(
        json.dumps(generation_error.payload(action), ensure_ascii=False),
        file=sys.stderr,
    )


def main() -> int:
    args = parse_args()
    if not args.prompt.strip():
        prompt_error = error(
            "invalid_prompt",
            "이미지 prompt가 비어 있어.",
            "적용할 장면이나 변경 내용을 prompt로 입력해 줘.",
            2,
        )
        emit_error(prompt_error, args.action)
        return prompt_error.exit_code

    try:
        if args.action == "edit":
            result = edit_image(
                prompt=args.prompt,
                image=args.image,
                output=args.output or default_output("edit"),
                aspect_ratio=args.aspect_ratio,
                timeout=args.timeout,
            )
        else:
            result = generate(
                prompt=args.prompt,
                aspect_ratio=args.aspect_ratio,
                output=args.output or default_output(),
                timeout=args.timeout,
            )
    except GenerationError as generation_error:
        emit_error(generation_error, args.action)
        return generation_error.exit_code

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
