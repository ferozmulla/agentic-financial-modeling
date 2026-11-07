"""Streaming OpenXML extractor for Eulr202409.xlsx and peer reference workbooks."""

from __future__ import annotations

import functools
import io
import re
import urllib.parse
import xml.etree.ElementTree as CElementTree
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    import defusedxml.ElementTree as SafeET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as SafeET

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"

_COORD_RE = re.compile(r"^([A-Z]+)(\d+)$")
_A1_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])(\$?)([A-Z]{1,3})(\$?)(\d+)(?![A-Za-z0-9_(!])")
_EXT_REF_RE = re.compile(
    r"(?:'\[(\d+)\]([^']+)'!|\[(\d+)\]([A-Za-z0-9_ -]+)!)\$?([A-Z]{1,3})\$?(\d+)"
)
_EXT_IDX_RE = re.compile(r"\[(\d+)\]")
_VINTAGE_RE = re.compile(r"(20\d{4})")
_MAX_XML_MEMBER_BYTES = 512 * 1024 * 1024  # 512 MB zip-bomb safety cap


def col_to_idx(col_str: str) -> int:
    n = 0
    for ch in col_str:
        n = n * 26 + (ord(ch) - 64)
    return n


def idx_to_col(idx: int) -> str:
    out: list[str] = []
    n = max(idx, 1)
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out.append(chr(65 + rem))
    return "".join(reversed(out))


def split_coord(coord: str) -> tuple[int, int]:
    m = _COORD_RE.match(coord)
    if not m:
        return (1, 1)
    return (int(m.group(2)), col_to_idx(m.group(1)))


def shift_formula_a1(formula: str, d_row: int, d_col: int) -> str:
    if d_row == 0 and d_col == 0:
        return formula

    def _repl(m: re.Match[str]) -> str:
        c_lock, col_s, r_lock, row_s = m.groups()
        c_num = col_to_idx(col_s)
        r_num = int(row_s)
        if c_num > 16384 or r_num > 1048576:
            return m.group(0)
        new_col = col_s if c_lock else idx_to_col(max(1, c_num + d_col))
        new_row = r_num if r_lock else max(1, r_num + d_row)
        return f"{c_lock}{new_col}{r_lock}{new_row}"

    return _A1_TOKEN_RE.sub(_repl, formula)


def normalize_formula_to_r1c1(formula: str, base_row: int, base_col: int) -> str:
    """Convert A1 references inside formula to row/col-relative R1C1 signature."""

    def _repl(m: re.Match[str]) -> str:
        c_lock, col_s, r_lock, row_s = m.groups()
        c_num = col_to_idx(col_s)
        r_num = int(row_s)
        if c_num > 16384 or r_num > 1048576:
            return m.group(0)
        r_part = f"R{r_num}" if r_lock else f"R[{r_num - base_row}]"
        c_part = f"C{c_num}" if c_lock else f"C[{c_num - base_col}]"
        return f"{r_part}{c_part}"

    return _A1_TOKEN_RE.sub(_repl, formula.strip().lstrip("="))


def _resolve_xl_target(raw_target: str) -> str:
    cleaned = raw_target.replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        return ""
    return cleaned if cleaned.startswith("xl/") else f"xl/{cleaned}"


def _safe_xml_stream(zf: zipfile.ZipFile, member: str) -> io.BytesIO:
    raw = zf.read(member)
    head = raw[:8192].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError(f"Disallowed XML DTD/ENTITY declaration in {member}")
    return io.BytesIO(raw)


@dataclass(frozen=True)
class CellRecord:
    coord: str
    row: int
    col: int
    ctype: str
    value: str | None
    numeric_value: float | None
    formula: str | None
    r1c1_sig: str | None
    is_array_cse: bool
    ext_indices: tuple[str, ...]


@dataclass(frozen=True)
class ExternalLinkCellRef:
    sheet_name: str
    cell_coord: str
    link_index: str
    ext_sheet: str
    ext_cell: str
    cached_value: str | None
    numeric_value: float | None
    formula_text: str


@dataclass(frozen=True)
class SheetExtract:
    name: str
    state: str
    total_c_tags: int
    empty_styled_c_tags: int
    populated_cells: int
    formula_cells: int
    cse_formula_cells: int
    ext_link_cells: int
    max_row: int
    max_col: int
    cells_by_coord: dict[str, CellRecord]
    cells_by_row: dict[int, list[CellRecord]]


@dataclass(frozen=True)
class WorkbookExtract:
    path: Path
    file_size_mb: float
    vintage_tag: str
    calc_pr: dict[str, str]
    sheet_names: list[str]
    active_sheet_names: list[str]
    retired_hidden_sheets: list[str]
    defined_names: list[tuple[str, str]]
    valid_defined_names: list[tuple[str, str]]
    broken_defined_names: list[tuple[str, str]]
    declared_external_links: dict[str, str]
    active_ext_refs: list[ExternalLinkCellRef]
    ext_formula_cell_count: int
    ext_formula_valid_cache_count: int
    sheets: dict[str, SheetExtract]
    total_c_tags: int
    total_populated_cells: int
    total_formula_cells: int
    total_cse_cells: int


@functools.lru_cache(maxsize=4)
def extract_workbook_openxml(xlsx_path: Path) -> WorkbookExtract:
    """Stream-parse an OpenXML workbook and expand shared formulas."""
    resolved = xlsx_path.resolve()
    file_size_mb = round(resolved.stat().st_size / (1024 * 1024), 2)
    vm = _VINTAGE_RE.search(resolved.stem)
    vintage_tag = vm.group(1) if vm else "202409"

    with zipfile.ZipFile(resolved, mode="r") as zf:
        for zinfo in zf.infolist():
            if ".." in zinfo.filename.replace("\\", "/").split("/"):
                raise ValueError(f"Unsafe zip member path in {resolved.name}: {zinfo.filename}")
            if zinfo.file_size > _MAX_XML_MEMBER_BYTES:
                raise ValueError(f"Zip member exceeds size cap in {resolved.name}: {zinfo.filename}")

        namelist = set(zf.namelist())
        wb_root = SafeET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = SafeET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rid_map = {
            r.attrib["Id"]: r.attrib["Target"]
            for r in rels_root.findall(f"{{{NS_REL_PKG}}}Relationship")
        }

        sst: list[str] = []
        if "xl/sharedStrings.xml" in namelist:
            with _safe_xml_stream(zf, "xl/sharedStrings.xml") as sfp:
                si_tag = f"{{{NS_MAIN}}}si"
                t_tag = f"{{{NS_MAIN}}}t"
                for _, elem in CElementTree.iterparse(sfp, events=("end",)):
                    if elem.tag == si_tag:
                        sst.append("".join(t.text or "" for t in elem.iter(t_tag)))
                        elem.clear()

        calc_el = wb_root.find(f"{{{NS_MAIN}}}calcPr")
        calc_pr = dict(calc_el.attrib) if calc_el is not None else {}

        defined_names: list[tuple[str, str]] = []
        valid_dnames: list[tuple[str, str]] = []
        broken_dnames: list[tuple[str, str]] = []
        for dn in wb_root.findall(f".//{{{NS_MAIN}}}definedNames/{{{NS_MAIN}}}definedName"):
            dname = dn.attrib.get("name", "")
            dbody = (dn.text or "").strip()
            if dname.startswith("_xlnm.") and "#REF!" not in dbody:
                continue
            defined_names.append((dname, dbody))
            if "#REF!" in dbody:
                broken_dnames.append((dname, dbody))
            else:
                valid_dnames.append((dname, dbody))

        declared_ext: dict[str, str] = {}
        for idx_i, ext_el in enumerate(
            wb_root.findall(f".//{{{NS_MAIN}}}externalReferences/{{{NS_MAIN}}}externalReference"),
            start=1,
        ):
            rid = ext_el.attrib.get(f"{{{NS_REL_DOC}}}id", "")
            tfile = rid_map.get(rid, "").replace("\\", "/").split("/")[-1]
            rel_file = f"xl/externalLinks/_rels/{tfile}.rels"
            target_url = ""
            if rel_file in namelist and ".." not in tfile:
                rxml = SafeET.fromstring(zf.read(rel_file))
                urls = [
                    urllib.parse.unquote(x.attrib.get("Target", ""))
                    for x in rxml.findall(f"{{{NS_REL_PKG}}}Relationship")
                ]
                target_url = urls[0] if urls else ""
            declared_ext[str(idx_i)] = target_url

        sheet_names: list[str] = []
        active_sheet_names: list[str] = []
        retired_hidden_sheets: list[str] = []
        sheets_extract: dict[str, SheetExtract] = {}
        active_ext_refs: list[ExternalLinkCellRef] = []
        ext_f_cells = 0
        ext_f_valid_cache = 0
        total_c = total_pop = total_f = total_cse = 0

        c_tag = f"{{{NS_MAIN}}}c"
        f_tag = f"{{{NS_MAIN}}}f"
        v_tag = f"{{{NS_MAIN}}}v"

        for sh_el in wb_root.findall(f".//{{{NS_MAIN}}}sheets/{{{NS_MAIN}}}sheet"):
            sname = sh_el.attrib["name"]
            sstate = sh_el.attrib.get("state", "visible")
            rid = sh_el.attrib.get(f"{{{NS_REL_DOC}}}id", "")
            s_target = _resolve_xl_target(rid_map.get(rid, ""))
            sheet_names.append(sname)
            if sstate != "visible" or sname.lower() == "shooju_addin":
                retired_hidden_sheets.append(sname)
            else:
                active_sheet_names.append(sname)

            if not s_target or s_target not in namelist:
                continue

            sh_c_tags = sh_empty_styled = sh_pop = sh_f = sh_cse = sh_ext = 0
            max_r = max_c = 1
            shared_masters: dict[str, tuple[int, int, str]] = {}
            shared_r1c1: dict[str, str] = {}
            by_coord: dict[str, CellRecord] = {}
            by_row: dict[int, list[CellRecord]] = defaultdict(list)

            with _safe_xml_stream(zf, s_target) as wfp:
                for _, elem in CElementTree.iterparse(wfp, events=("end",)):
                    if elem.tag != c_tag:
                        continue
                    sh_c_tags += 1
                    coord = elem.attrib.get("r", "A1")
                    r_idx, c_idx = split_coord(coord)
                    max_r = max(max_r, r_idx)
                    max_c = max(max_c, c_idx)
                    ctype = elem.attrib.get("t", "")
                    f_el = elem.find(f_tag)
                    v_el = elem.find(v_tag)

                    if f_el is None and v_el is None:
                        if "s" in elem.attrib:
                            sh_empty_styled += 1
                        elem.clear()
                        continue

                    sh_pop += 1
                    raw_v = v_el.text if v_el is not None else None
                    num_v: float | None = None
                    if ctype == "s" and raw_v is not None and raw_v.isdigit():
                        s_i = int(raw_v)
                        val = sst[s_i] if 0 <= s_i < len(sst) else raw_v
                    else:
                        val = raw_v
                        if val is not None and ctype not in ("s", "e", "str"):
                            try:
                                num_v = float(val)
                            except ValueError:
                                num_v = None

                    formula_str: str | None = None
                    r1c1_sig: str | None = None
                    is_cse = False
                    ext_idxs: tuple[str, ...] = ()

                    if f_el is not None:
                        sh_f += 1
                        f_type = f_el.attrib.get("t", "")
                        is_cse = f_type == "array"
                        if is_cse:
                            sh_cse += 1
                        raw_f = f_el.text or ""
                        if f_type == "shared":
                            si = f_el.attrib.get("si", "")
                            if raw_f:
                                shared_masters[si] = (r_idx, c_idx, raw_f)
                                formula_str = raw_f
                                r1c1_sig = normalize_formula_to_r1c1(formula_str, r_idx, c_idx)
                                shared_r1c1[si] = r1c1_sig
                            elif si in shared_masters:
                                mr, mc, mf = shared_masters[si]
                                r1c1_sig = shared_r1c1[si]
                                if "[" in mf or ctype == "e" or "#REF!" in mf or sname in ("KeyInputs", "Carbon", "NWE Cif", "MED Cif", "Yields", "Checks"):
                                    formula_str = shift_formula_a1(mf, r_idx - mr, c_idx - mc)
                                else:
                                    formula_str = mf
                            else:
                                formula_str = raw_f
                                r1c1_sig = normalize_formula_to_r1c1(formula_str, r_idx, c_idx)
                        else:
                            formula_str = raw_f
                            r1c1_sig = normalize_formula_to_r1c1(formula_str, r_idx, c_idx)

                        if "[" in formula_str:
                            found_idxs = tuple(sorted(set(_EXT_IDX_RE.findall(formula_str))))
                            if found_idxs:
                                ext_idxs = found_idxs
                                sh_ext += 1
                                ext_f_cells += 1
                                if val is not None and val not in ("#REF!", "#NAME?"):
                                    ext_f_valid_cache += 1
                                for em in _EXT_REF_RE.finditer(formula_str):
                                    l_idx = em.group(1) or em.group(3)
                                    e_sh = em.group(2) or em.group(4)
                                    e_cell = f"{em.group(5)}{em.group(6)}"
                                    active_ext_refs.append(
                                        ExternalLinkCellRef(
                                            sheet_name=sname,
                                            cell_coord=coord,
                                            link_index=l_idx,
                                            ext_sheet=e_sh,
                                            ext_cell=e_cell,
                                            cached_value=val,
                                            numeric_value=num_v,
                                            formula_text=formula_str,
                                        )
                                    )

                    crec = CellRecord(
                        coord=coord,
                        row=r_idx,
                        col=c_idx,
                        ctype=ctype,
                        value=val,
                        numeric_value=num_v,
                        formula=formula_str,
                        r1c1_sig=r1c1_sig,
                        is_array_cse=is_cse,
                        ext_indices=ext_idxs,
                    )
                    by_coord[coord] = crec
                    by_row[r_idx].append(crec)
                    elem.clear()

            total_c += sh_c_tags
            total_pop += sh_pop
            total_f += sh_f
            total_cse += sh_cse

            sheets_extract[sname] = SheetExtract(
                name=sname,
                state=sstate,
                total_c_tags=sh_c_tags,
                empty_styled_c_tags=sh_empty_styled,
                populated_cells=sh_pop,
                formula_cells=sh_f,
                cse_formula_cells=sh_cse,
                ext_link_cells=sh_ext,
                max_row=max_r,
                max_col=max_c,
                cells_by_coord=by_coord,
                cells_by_row=dict(by_row),
            )

    return WorkbookExtract(
        path=resolved,
        file_size_mb=file_size_mb,
        vintage_tag=vintage_tag,
        calc_pr=calc_pr,
        sheet_names=sheet_names,
        active_sheet_names=active_sheet_names,
        retired_hidden_sheets=retired_hidden_sheets,
        defined_names=defined_names,
        valid_defined_names=valid_dnames,
        broken_defined_names=broken_dnames,
        declared_external_links=declared_ext,
        active_ext_refs=active_ext_refs,
        ext_formula_cell_count=ext_f_cells,
        ext_formula_valid_cache_count=ext_f_valid_cache,
        sheets=sheets_extract,
        total_c_tags=total_c,
        total_populated_cells=total_pop,
        total_formula_cells=total_f,
        total_cse_cells=total_cse,
    )


@functools.lru_cache(maxsize=16)
def extract_peer_sheet_values(xlsx_path: Path, target_sheets_lower: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """Fast targeted value extraction for specific sheets in a peer .xlsx file (e.g. 'Links Out')."""
    resolved = xlsx_path.resolve()
    result: dict[str, dict[str, float]] = {}
    target_set = {s.lower() for s in target_sheets_lower}

    with zipfile.ZipFile(resolved, mode="r") as zf:
        namelist = set(zf.namelist())
        wb_root = SafeET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = SafeET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rid_map = {
            r.attrib["Id"]: r.attrib["Target"]
            for r in rels_root.findall(f"{{{NS_REL_PKG}}}Relationship")
        }

        c_tag = f"{{{NS_MAIN}}}c"
        v_tag = f"{{{NS_MAIN}}}v"

        for sh_el in wb_root.findall(f".//{{{NS_MAIN}}}sheets/{{{NS_MAIN}}}sheet"):
            sname = sh_el.attrib["name"]
            if sname.lower() not in target_set:
                continue
            rid = sh_el.attrib.get(f"{{{NS_REL_DOC}}}id", "")
            s_target = _resolve_xl_target(rid_map.get(rid, ""))
            if not s_target or s_target not in namelist:
                continue

            smap: dict[str, float] = {}
            with _safe_xml_stream(zf, s_target) as wfp:
                for _, elem in CElementTree.iterparse(wfp, events=("end",)):
                    if elem.tag != c_tag:
                        continue
                    ctype = elem.attrib.get("t", "")
                    if ctype in ("s", "e", "str"):
                        elem.clear()
                        continue
                    v_el = elem.find(v_tag)
                    if v_el is not None and v_el.text is not None:
                        try:
                            smap[elem.attrib.get("r", "A1")] = float(v_el.text)
                        except ValueError:
                            pass
                    elem.clear()
            result[sname.lower()] = smap

    return result
