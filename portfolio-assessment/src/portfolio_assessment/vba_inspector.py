"""Pure-Python MS-OVBA binary container inspector for xl/vbaProject.bin."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VBAInspectionSummary:
    has_executable_vba: bool
    is_locked: bool
    procedural_lines: int
    has_win32_or_shell: bool
    has_com_or_db: bool
    module_names: list[str]


_ASCII_RUN_RE = re.compile(rb"[\x09\x0a\x0d\x20-\x7e]{6,}")
_MOD_NAME_RE = re.compile(r'Attribute\s+VB_Name\s*=\s*"([A-Za-z0-9_]+)"', re.IGNORECASE)
_PROC_TOKEN_RE = re.compile(r"\b(Sub|Function|Property\s+Get|Property\s+Let)\b", re.IGNORECASE)
_WIN32_RE = re.compile(
    r"\b(Declare\s+(?:PtrSafe\s+)?(?:Function|Sub)|(?:Call\s+)?Shell\s*\(|WScript\.Shell|URLDownloadToFile)",
    re.IGNORECASE,
)
_COM_DB_RE = re.compile(
    r'(CreateObject\s*\(\s*"(?:ADODB|DAO|Scripting\.FileSystemObject|Excel\.Application)|Workbooks\.Open)',
    re.IGNORECASE,
)


def inspect_vba_project_bytes(data: bytes) -> VBAInspectionSummary:
    """Extract readable ASCII/MS-OVBA fragments and procedural tokens without executing code."""
    if not data or len(data) < 16:
        return VBAInspectionSummary(False, False, 0, False, False, [])

    # Strip MS-OVBA LZNT1 single-byte compression flag bytes between printable ASCII bytes
    deflagged = re.sub(rb"(?<=[\x20-\x7e])[\x00-\x08\x0b\x0c\x0e-\x1f\x80-\xff](?=[\x20-\x7e])", b"", data)
    chunks = [m.group(0).decode("latin-1", errors="ignore") for m in _ASCII_RUN_RE.finditer(deflagged)]
    stripped = re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]+", b" ", deflagged).decode(
        "latin-1", errors="ignore"
    )
    combined_text = "\n".join(chunks)

    module_names = sorted(set(_MOD_NAME_RE.findall(combined_text)) | set(_MOD_NAME_RE.findall(stripped)))
    lines = [
        ln.strip()
        for ln in combined_text.splitlines()
        if ln.strip() and not ln.strip().startswith(("Attribute VB_", "'"))
    ]
    has_proc = bool(_PROC_TOKEN_RE.search(combined_text) or _PROC_TOKEN_RE.search(stripped))
    proc_lines = len(lines) if has_proc else 0

    has_dpb_lock = b'DPB="' in data and not has_proc and len(data) > 4096
    has_win32 = bool(_WIN32_RE.search(combined_text) or _WIN32_RE.search(stripped))
    has_com = bool(_COM_DB_RE.search(combined_text) or _COM_DB_RE.search(stripped))

    return VBAInspectionSummary(
        has_executable_vba=proc_lines > 0,
        is_locked=has_dpb_lock,
        procedural_lines=proc_lines,
        has_win32_or_shell=has_win32,
        has_com_or_db=has_com,
        module_names=module_names,
    )
