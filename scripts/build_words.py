#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCOWL_REPO = "https://github.com/en-wl/wordlist"
SCOWL_BRANCH = "v2"
# Pinned to v2 branch HEAD as of January 17, 2026.
SCOWL_COMMIT = "744c092883db13112f6680892850c1f1b6547b81"
SCOWL_ARCHIVE_URL = f"{SCOWL_REPO}/archive/{SCOWL_COMMIT}.tar.gz"

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCOWL_DIR = DATA_DIR / "scowl"
CACHE_DIR = SCOWL_DIR / "cache"
SRC_DIR = SCOWL_DIR / "src"
LOCK_PATH = SCOWL_DIR / "source.lock.json"
WORDS_RAW_PATH = DATA_DIR / "words_raw.txt"
WORDS_PATH = ROOT / "words.txt"
META_PATH = ROOT / "dict.meta.json"
LICENSES_DIR = ROOT / "licenses"


@dataclass
class SourceLock:
    commit: str
    sha256: str
    archive_url: str


class ProgressTracker:
    def __init__(self, total_steps: int) -> None:
        self.total_steps = total_steps
        self.current_step = 0
        self.process_started_at = time.perf_counter()

    def start(self, title: str, detail: str | None = None) -> float:
        self.current_step += 1
        print(f"[{self.current_step}/{self.total_steps}] {title}", flush=True)
        if detail:
            print(f"    {detail}", flush=True)
        return time.perf_counter()

    def info(self, message: str) -> None:
        print(f"    {message}", flush=True)

    def done(self, started_at: float, detail: str | None = None) -> None:
        elapsed = time.perf_counter() - started_at
        suffix = f" ({detail})" if detail else ""
        print(f"    done in {elapsed:.1f}s{suffix}", flush=True)

    def summary(self) -> None:
        total_elapsed = time.perf_counter() - self.process_started_at
        print(f"[complete] Dictionary words build finished in {total_elapsed:.1f}s", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch SCOWLv2, normalize words to A-Z uppercase, and emit words.txt + dict.meta.json."
    )
    parser.add_argument("--size", type=int, default=80, help="SCOWL size (default: 80)")
    parser.add_argument(
        "--spellings",
        default="A,B,Z,C,D",
        help="SCOWL spellings list (default: A,B,Z,C,D)",
    )
    parser.add_argument(
        "--variant-level",
        type=int,
        default=5,
        help="SCOWL variant level (default: 5)",
    )
    parser.add_argument(
        "--archive-sha256",
        default="",
        help="Expected SHA256 for the archive. If omitted, script uses lock file or records first seen SHA.",
    )
    return parser.parse_args()


def run_command(
    cmd: list[str], cwd: Path | None = None, capture_stdout: bool = True
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE if capture_stdout else None,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        stdout_text = proc.stdout or "" if capture_stdout else "<not captured>"
        stderr_text = proc.stderr or ""
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\nSTDOUT:\n{stdout_text}\nSTDERR:\n{stderr_text}"
        )
    return proc


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as infile:
        for chunk in iter(lambda: infile.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_lock() -> SourceLock | None:
    if not LOCK_PATH.exists():
        return None
    data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    required = ("commit", "sha256", "archive_url")
    if not all(key in data for key in required):
        return None
    return SourceLock(
        commit=str(data["commit"]),
        sha256=str(data["sha256"]),
        archive_url=str(data["archive_url"]),
    )


def write_lock(lock: SourceLock) -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(
        json.dumps(
            {
                "commit": lock.commit,
                "sha256": lock.sha256,
                "archive_url": lock.archive_url,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def download_archive(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url) as response, destination.open("wb") as outfile:
            shutil.copyfileobj(response, outfile)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to download archive from {url}: {exc}") from exc


def ensure_archive(url: str, commit: str, expected_sha: str) -> tuple[Path, str, bool]:
    archive_path = CACHE_DIR / f"wordlist-{commit}.tar.gz"
    downloaded = False
    if not archive_path.exists():
        download_archive(url, archive_path)
        downloaded = True

    actual_sha = sha256_file(archive_path)
    if expected_sha and actual_sha != expected_sha:
        raise RuntimeError(
            f"Archive SHA256 mismatch for {archive_path}:\nexpected={expected_sha}\nactual={actual_sha}\n"
            "Delete the archive and retry if the source changed."
        )
    return archive_path, actual_sha, downloaded


def extract_archive(archive_path: Path, commit: str) -> Path:
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = SRC_DIR / f"wordlist-{commit}"
    if target_dir.exists():
        return target_dir

    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        if not members:
            raise RuntimeError("Archive is empty.")
        top_level = members[0].name.split("/", 1)[0]
        tar.extractall(path=SRC_DIR)

    extracted_dir = SRC_DIR / top_level
    if not extracted_dir.exists():
        raise RuntimeError(f"Expected extracted path missing: {extracted_dir}")

    extracted_dir.rename(target_dir)
    return target_dir


def normalize_words(raw_text: str) -> list[str]:
    deduped: set[str] = set()
    for line in raw_text.splitlines():
        word = re.sub(r"[^A-Z]", "", line.upper())
        if word:
            deduped.add(word)
    return sorted(deduped)


def assert_sorted_unique(words: list[str]) -> None:
    for idx in range(1, len(words)):
        if words[idx - 1] >= words[idx]:
            raise RuntimeError(
                f"words.txt invariant failed at index {idx}: '{words[idx - 1]}' >= '{words[idx]}'"
            )


def build_scowl_wordlist(scowl_root: Path, size: int, spellings: str, variant_level: int) -> tuple[str, bool]:
    db_path = scowl_root / "scowl.db"
    built_db = False
    if not db_path.exists():
        run_command(["make"], cwd=scowl_root, capture_stdout=False)
        built_db = True

    cmd = [
        str(scowl_root / "scowl"),
        "--db",
        "scowl.db",
        "word-list",
        str(size),
        spellings,
        str(variant_level),
        "--deaccent",
        "--categories=",
        "--tags=",
        "--wo-poses=abbr",
        "--wo-pos-categories=nonword,special,wordpart",
    ]
    proc = run_command(cmd, cwd=scowl_root)
    return proc.stdout, built_db


def copy_scowl_notices(scowl_root: Path) -> None:
    LICENSES_DIR.mkdir(parents=True, exist_ok=True)

    license_candidates = [
        scowl_root / "LICENSE",
        scowl_root / "License",
        scowl_root / "COPYING",
        scowl_root / "Copyright",
    ]
    copyright_candidates = [
        scowl_root / "Copyright",
        scowl_root / "COPYRIGHT",
        scowl_root / "LICENSE",
        scowl_root / "README.md",
    ]

    license_source = next((path for path in license_candidates if path.exists()), None)
    copyright_source = next((path for path in copyright_candidates if path.exists()), None)

    if license_source is None or copyright_source is None:
        raise RuntimeError(
            "Could not find SCOWL license/copyright files in downloaded source."
        )

    shutil.copyfile(license_source, LICENSES_DIR / "SCOWL-LICENSE.txt")
    shutil.copyfile(copyright_source, LICENSES_DIR / "SCOWL-COPYRIGHTS.txt")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_meta(
    *,
    source_url: str,
    source_commit: str,
    source_sha256: str,
    size: int,
    spellings: str,
    variant_level: int,
    words: list[str],
) -> None:
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    meta = read_json(META_PATH)
    meta["source"] = {
        "repo": SCOWL_REPO,
        "branch": SCOWL_BRANCH,
        "commit": source_commit,
        "archiveUrl": source_url,
        "sha256": source_sha256,
    }
    meta["profile"] = {
        "size": size,
        "spellings": [segment.strip() for segment in spellings.split(",") if segment.strip()],
        "variantLevel": variant_level,
        "classes": "core",
        "normalization": "uppercase-alpha-strip",
    }
    meta["stats"] = {
        "wordCount": len(words),
        "minLength": min((len(word) for word in words), default=0),
        "maxLength": max((len(word) for word in words), default=0),
        "buildTimestamp": datetime.now(timezone.utc).isoformat(),
    }
    artifacts = meta.setdefault("artifacts", {})
    artifacts.setdefault("dawgFile", "dict.dawg")

    META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    progress = ProgressTracker(total_steps=7)
    args = parse_args()
    lock = read_lock()

    commit = SCOWL_COMMIT
    source_url = SCOWL_ARCHIVE_URL

    expected_sha = args.archive_sha256.strip()
    if not expected_sha and lock and lock.commit == commit and lock.archive_url == source_url:
        expected_sha = lock.sha256

    step_started = progress.start(
        "Resolve SCOWLv2 source archive",
        "This can take 15-90s on first run depending on network speed.",
    )
    archive_path, actual_sha, downloaded = ensure_archive(source_url, commit, expected_sha)
    archive_size_mb = archive_path.stat().st_size / (1024 * 1024)
    progress.done(
        step_started,
        f"{'downloaded' if downloaded else 'cache hit'}, {archive_size_mb:.1f} MiB",
    )

    step_started = progress.start("Record source lock/checksum")
    if not expected_sha:
        write_lock(SourceLock(commit=commit, sha256=actual_sha, archive_url=source_url))
        progress.done(step_started, "new source.lock.json written")
    elif expected_sha != actual_sha:
        raise RuntimeError(
            f"Resolved checksum mismatch after download. expected={expected_sha}, actual={actual_sha}"
        )
    else:
        progress.done(step_started, "checksum verified")

    step_started = progress.start("Extract SCOWL archive")
    scowl_root = extract_archive(archive_path, commit)
    progress.done(step_started, str(scowl_root))

    step_started = progress.start(
        "Generate raw SCOWL word list",
        "If SCOWL DB is missing this can take 30-180s on first run.",
    )
    raw_words, built_db = build_scowl_wordlist(
        scowl_root=scowl_root,
        size=args.size,
        spellings=args.spellings,
        variant_level=args.variant_level,
    )
    if not raw_words.strip():
        raise RuntimeError("SCOWL word-list command returned empty output.")
    progress.done(step_started, f"{'built scowl.db + queried' if built_db else 'queried existing scowl.db'}")

    step_started = progress.start("Normalize + write words files")
    WORDS_RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORDS_RAW_PATH.write_text(raw_words, encoding="utf-8")

    words = normalize_words(raw_words)
    assert_sorted_unique(words)
    WORDS_PATH.write_text("\n".join(words) + "\n", encoding="utf-8")
    progress.done(step_started, f"{len(words)} normalized words")

    step_started = progress.start("Copy SCOWL license/copyright notices")
    copy_scowl_notices(scowl_root)
    progress.done(step_started, str(LICENSES_DIR))

    step_started = progress.start("Write dict metadata")
    write_meta(
        source_url=source_url,
        source_commit=commit,
        source_sha256=actual_sha,
        size=args.size,
        spellings=args.spellings,
        variant_level=args.variant_level,
        words=words,
    )
    progress.done(step_started, str(META_PATH))

    print(f"Wrote {WORDS_PATH} ({len(words)} words)")
    print(f"Wrote {META_PATH}")
    print(f"SCOWL source: {commit} ({actual_sha})")
    progress.summary()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1) from exc
