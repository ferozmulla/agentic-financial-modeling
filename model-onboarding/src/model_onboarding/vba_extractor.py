"""Safe pure-Python MS-OVBA LZNT1 decompressor & procedural source extractor for `.xlsm` macros."""

from __future__ import annotations

import json
import math
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from model_onboarding.hygiene_gate import validate_workbook_file

_MAX_VBA_BIN_BYTES = 16 * 1024 * 1024
_MAX_DECOMPRESSED_BYTES = 32 * 1024 * 1024
_ASCII_RUN_RE = re.compile(rb"[\x09\x0a\x0d\x20-\x7e]{6,}")
_ATTR_VB_NAME_RE = re.compile(r'Attribute\s+VB_Name\s*=\s*"([A-Za-z0-9_]+)"', re.IGNORECASE)
_PROC_HEADER_RE = re.compile(
    r"\b(?:Sub|Function)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.IGNORECASE,
)
_GOALSEEK_OR_SOLVER_RE = re.compile(r"\b(GoalSeek|SolverOk|SolverSolve)\b", re.IGNORECASE)
_SAFE_MOD_NAME_RE = re.compile(r"[^A-Za-z0-9_]+")


@dataclass(frozen=True)
class ExtractedVbaModule:
    """Single extracted VBA module with procedure names and solver/GoalSeek indicators."""

    module_name: str
    procedures: list[str]
    has_goalseek_or_solver: bool
    line_count: int
    source_text: str


def _try_decompress_ovba_at(data: bytes, start: int) -> bytes | None:
    """Attempt MS-OVBA 2.4.1 LZNT1 container decompression starting at `data[start] == 0x01`."""
    n = len(data)
    if start >= n or data[start] != 0x01:
        return None

    pos = start + 1
    out = bytearray()
    while pos + 2 <= n and len(out) < _MAX_DECOMPRESSED_BYTES:
        header = int.from_bytes(data[pos : pos + 2], "little")
        sig = (header >> 12) & 0x07
        if sig != 0b011:
            break
        chunk_size = (header & 0x0FFF) + 3
        is_compressed = (header >> 15) & 0x01
        chunk_end = pos + chunk_size
        if chunk_end > n:
            break

        pos += 2
        if not is_compressed:
            raw_len = min(4096, chunk_end - pos)
            out.extend(data[pos : pos + raw_len])
            pos = chunk_end
            continue

        chunk_out_start = len(out)
        while pos < chunk_end and len(out) < _MAX_DECOMPRESSED_BYTES:
            flags = data[pos]
            pos += 1
            for bit_idx in range(8):
                if pos >= chunk_end:
                    break
                if ((flags >> bit_idx) & 1) == 0:
                    out.append(data[pos])
                    pos += 1
                else:
                    if pos + 2 > chunk_end:
                        pos = chunk_end
                        break
                    token = int.from_bytes(data[pos : pos + 2], "little")
                    pos += 2
                    decompressed_chunk_len = max(len(out) - chunk_out_start, 1)
                    bit_count = max(4, math.ceil(math.log2(max(decompressed_chunk_len, 2))))
                    length_mask = 0xFFFF >> bit_count
                    copy_len = (token & length_mask) + 3
                    offset = (token >> (16 - bit_count)) + 1
                    if offset > len(out):
                        return bytes(out) if b"Attribute VB_Name" in out else None
                    for _ in range(copy_len):
                        out.append(out[-offset])
        pos = chunk_end

    return bytes(out) if b"Attribute VB_Name" in out else None


def _extract_vba_text_streams(raw_bytes: bytes) -> str:
    """Decompress MS-OVBA module containers from `vbaProject.bin`, with ASCII fallback."""
    decoded_streams: list[str] = []
    idx = 0
    n = len(raw_bytes)
    while idx < n - 16:
        pos = raw_bytes.find(b"\x01", idx)
        if pos == -1 or pos + 3 >= n:
            break
        hdr = int.from_bytes(raw_bytes[pos + 1 : pos + 3], "little")
        if ((hdr >> 12) & 0x07) == 0b011 and ((hdr >> 15) & 0x01) == 1:
            decomp = _try_decompress_ovba_at(raw_bytes, pos)
            if decomp:
                decoded_streams.append(decomp.decode("latin-1", errors="ignore"))
                idx = pos + 16
                continue
        idx = pos + 1

    if decoded_streams:
        return "\n".join(decoded_streams)

    deflagged = re.sub(
        rb"(?<=[\x20-\x7e])[\x00-\x08\x0b\x0c\x0e-\x1f\x80-\xff](?=[\x20-\x7e])",
        b"",
        raw_bytes,
    )
    chunks = [m.group(0).decode("latin-1", errors="ignore") for m in _ASCII_RUN_RE.finditer(deflagged)]
    return "\n".join(chunks)


def extract_vba_modules(xlsx_path: Path, max_size_mb: float = 100.0) -> list[ExtractedVbaModule]:
    """Extract readable VBA modules from `xl/vbaProject.bin` without executing macros."""
    resolved = validate_workbook_file(xlsx_path, max_size_mb=max_size_mb)
    if resolved.suffix.lower() != ".xlsm":
        return []

    with zipfile.ZipFile(resolved, mode="r") as zf:
        if "xl/vbaProject.bin" not in zf.namelist():
            return []
        info = zf.getinfo("xl/vbaProject.bin")
        if info.file_size > _MAX_VBA_BIN_BYTES:
            raise ValueError(f"xl/vbaProject.bin exceeds {_MAX_VBA_BIN_BYTES} byte safety cap.")
        raw_bytes = zf.read("xl/vbaProject.bin")

    combined = _extract_vba_text_streams(raw_bytes)
    matches = list(_ATTR_VB_NAME_RE.finditer(combined))
    if not matches:
        return []

    modules_by_name: dict[str, ExtractedVbaModule] = {}
    for idx, match in enumerate(matches):
        raw_mod_name = match.group(1)
        safe_name = _SAFE_MOD_NAME_RE.sub("_", raw_mod_name).strip("_") or f"Module_{idx + 1}"
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(combined)
        segment = combined[start:end]

        clean_lines: list[str] = []
        procedures: list[str] = []
        for raw_ln in segment.splitlines():
            ln = raw_ln.rstrip()
            if not ln.strip() or ln.lstrip().startswith("Attribute VB_"):
                continue
            clean_lines.append(ln)
            for pm in _PROC_HEADER_RE.finditer(ln):
                proc_name = pm.group(1)
                if proc_name not in procedures:
                    procedures.append(proc_name)

        if not clean_lines:
            continue

        body = "\n".join(clean_lines)
        has_gs = bool(_GOALSEEK_OR_SOLVER_RE.search(body))
        prev = modules_by_name.get(safe_name)
        if prev is None or len(clean_lines) > prev.line_count:
            modules_by_name[safe_name] = ExtractedVbaModule(
                module_name=safe_name,
                procedures=procedures,
                has_goalseek_or_solver=has_gs,
                line_count=len(clean_lines),
                source_text=body,
            )

    return sorted(modules_by_name.values(), key=lambda m: m.module_name.lower())


def stage_extracted_vba_modules(xlsx_path: Path, target_dir: Path) -> list[Path]:
    """Write extracted `.vba.txt` files and `vba_manifest.json` into `target_dir`."""
    resolved_root = target_dir.expanduser().resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)
    modules = extract_vba_modules(xlsx_path)
    written: list[Path] = []

    manifest: list[dict[str, object]] = []
    for mod in modules:
        out_file = (resolved_root / f"{mod.module_name}.vba.txt").resolve()
        if out_file.parent != resolved_root:
            raise ValueError("VBA staging path escaped target directory.")
        out_file.write_text(mod.source_text + "\n", encoding="utf-8")
        written.append(out_file)
        row = asdict(mod)
        row.pop("source_text", None)
        row["staged_file"] = out_file.name
        manifest.append(row)

    manifest_path = resolved_root / "vba_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written.append(manifest_path)
    return written
