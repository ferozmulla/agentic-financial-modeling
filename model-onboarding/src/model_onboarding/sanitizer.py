"""Security sanitizer and independent local parity verifier for untrusted sandbox outputs."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

from model_onboarding.models import ParityVerificationReport

_DISALLOWED_SUFFIXES = {
    ".xlsx",
    ".xlsm",
    ".xls",
    ".xlsb",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
}
_SECRET_FILENAME_RE = re.compile(
    r"(^\.env($|\.)|credentials.*\.json$|service[-_]account.*\.json$|id_rsa|id_ed25519)",
    re.IGNORECASE,
)
_PEM_HEADER_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_FORBIDDEN_AST_CALLS = {"eval", "exec", "compile", "__import__"}

_MAX_ARCHIVE_FILES = 250
_MAX_SINGLE_FILE_BYTES = 5 * 1024 * 1024
_MAX_TOTAL_BYTES = 30 * 1024 * 1024


def ensure_contained_path(root_dir: Path, candidate_path: Path) -> Path:
    """Resolve `candidate_path` and verify strict containment within `root_dir`."""
    resolved_root = root_dir.resolve()
    resolved_cand = candidate_path.resolve()
    root_prefix = str(resolved_root) + os.sep
    if resolved_cand != resolved_root and not str(resolved_cand).startswith(root_prefix):
        raise ValueError(f"Path traversal blocked: {candidate_path} escapes {resolved_root}")
    return resolved_cand


def extract_tar_safely(tar_path: Path, dest_dir: Path) -> Path:
    """Safely extract a `.tar.gz` bundle while blocking path traversal, symlinks, and zip bombs."""
    resolved_dest = dest_dir.expanduser().resolve()
    resolved_dest.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    file_count = 0

    with tarfile.open(tar_path, mode="r:*") as tf:
        for member in tf.getmembers():
            file_count += 1
            if file_count > _MAX_ARCHIVE_FILES:
                raise ValueError(f"Sandbox bundle exceeds {_MAX_ARCHIVE_FILES} file count limit.")
            if member.issym() or member.islnk() or member.ischr() or member.isblk() or member.isfifo():
                raise ValueError(f"Disallowed special/symlink tar entry: {member.name!r}")

            rel_parts = Path(member.name).parts
            if not rel_parts or Path(member.name).is_absolute() or ".." in rel_parts:
                raise ValueError(f"Unsafe tar member path: {member.name!r}")

            target = ensure_contained_path(resolved_dest, resolved_dest / member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError(f"Unsupported tar member type for {member.name!r}")
            if member.size > _MAX_SINGLE_FILE_BYTES:
                raise ValueError(f"Tar member {member.name!r} exceeds 5 MB single-file cap.")
            total_bytes += member.size
            if total_bytes > _MAX_TOTAL_BYTES:
                raise ValueError("Sandbox bundle exceeds 30 MB total extracted size cap.")

            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            with extracted, target.open("wb") as out_fh:
                out_fh.write(extracted.read())

    return resolved_dest


def _validate_python_ast(py_path: Path, source_text: str) -> None:
    """Verify valid Python syntax and block dynamic code execution calls (`eval`, `exec`)."""
    try:
        tree = ast.parse(source_text, filename=str(py_path))
    except SyntaxError as exc:
        raise ValueError(f"Syntax error in generated Python file {py_path.name}: {exc}") from exc

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FORBIDDEN_AST_CALLS
        ):
            raise ValueError(
                f"Disallowed dynamic execution call '{node.func.id}()' in {py_path.name}:{node.lineno}"
            )


def audit_generated_package_tree(pkg_dir: Path) -> list[Path]:
    """Audit extracted `<model_slug>-bq-twin/` directory for forbidden binaries, secrets, and unsafe ASTs."""
    resolved_pkg = pkg_dir.expanduser().resolve()
    if not resolved_pkg.exists() or not resolved_pkg.is_dir():
        raise FileNotFoundError(f"Generated package directory not found: {pkg_dir}")

    checked_files: list[Path] = []
    total_bytes = 0

    for entry in sorted(resolved_pkg.rglob("*")):
        if entry.is_symlink():
            raise ValueError(f"Symlink disallowed in generated package: {entry.name}")
        ensure_contained_path(resolved_pkg, entry)
        if entry.is_dir():
            continue
        if any(part in {"__pycache__", ".pytest_cache", ".ruff_cache"} for part in entry.parts):
            continue

        if len(checked_files) >= _MAX_ARCHIVE_FILES:
            raise ValueError(f"Generated package exceeds {_MAX_ARCHIVE_FILES} file limit.")

        size = entry.stat().st_size
        if size > _MAX_SINGLE_FILE_BYTES:
            raise ValueError(f"Generated file {entry.name} ({size} B) exceeds 5 MB cap.")
        total_bytes += size
        if total_bytes > _MAX_TOTAL_BYTES:
            raise ValueError("Generated package exceeds 30 MB total size cap.")

        suffix = entry.suffix.lower()
        if suffix in _DISALLOWED_SUFFIXES:
            raise ValueError(
                f"Disallowed binary or workbook file {entry.name!r} inside generated Git package."
            )
        if _SECRET_FILENAME_RE.search(entry.name) and entry.name != ".env.example":
            raise ValueError(f"Disallowed secret/credential file {entry.name!r} in generated package.")

        text_sample = entry.read_bytes().decode("utf-8", errors="ignore")
        if _PEM_HEADER_RE.search(text_sample):
            raise ValueError(f"Private key PEM block detected inside {entry.name!r}.")

        if suffix == ".py":
            _validate_python_ast(entry, text_sample)

        checked_files.append(entry)

    required_rel = ("Dockerfile", "pyproject.toml", "src", "tests")
    for req in required_rel:
        if not (resolved_pkg / req).exists():
            raise ValueError(f"Generated package {resolved_pkg.name} is missing required '{req}'.")

    dockerfile_txt = (resolved_pkg / "Dockerfile").read_text(encoding="utf-8")
    if ".xlsm" in dockerfile_txt.lower() or ".xlsx" in dockerfile_txt.lower():
        raise ValueError("Generated Dockerfile must not copy .xlsx or .xlsm files into the container image.")

    return checked_files


def run_local_parity_pytest(
    pkg_dir: Path,
    seed_workbook_path: Path,
    parity_report: ParityVerificationReport,
    timeout_sec: float = 120.0,
) -> ParityVerificationReport:
    """Independently execute `pytest` on the sanitized package against the local seed workbook."""
    resolved_pkg = pkg_dir.expanduser().resolve()
    resolved_seed = seed_workbook_path.expanduser().resolve()
    tests_dir = ensure_contained_path(resolved_pkg, resolved_pkg / "tests")
    src_dir = ensure_contained_path(resolved_pkg, resolved_pkg / "src")

    minimal_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONPATH": str(src_dir),
        "ONBOARD_SEED_WORKBOOK_PATH": str(resolved_seed),
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests_dir), "-q", "--tb=short"],
        cwd=str(resolved_pkg),
        env=minimal_env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    if proc.returncode != 0:
        snippet = (proc.stdout + "\n" + proc.stderr).strip()[-1200:]
        raise ValueError(f"Independent local parity pytest failed (exit {proc.returncode}):\n{snippet}")

    return parity_report.model_copy(update={"passed": True, "verified_locally": True})
