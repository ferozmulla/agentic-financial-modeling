"""Single-pass OpenXML (.xlsx) decompiler for EULR producing BigQuery Digital Twin rows."""

from __future__ import annotations

import colorsys
import json
import posixpath
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpyxl.styles.colors import COLOR_INDEX

from eulr_bq_twin.models import (
    EulrBaselineSnapshot,
    ExternalLinkCell,
    StyleMeta,
    TwinCell,
    WorksheetMeta,
    col_letter_to_index,
    index_to_col_letter,
    split_a1_coord,
)
from eulr_bq_twin.schema_ddl import ACTIVE_19_EULR_TABS

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DRAW_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

_DEFAULT_OFFICE_THEME: tuple[str, ...] = (
    "FFFFFF",
    "000000",
    "EEECE1",
    "1F497D",
    "4F81BD",
    "C0504D",
    "9BBB59",
    "8064A2",
    "4BACC6",
    "F79646",
    "0000FF",
    "800080",
)

_BUILTIN_NUM_FMTS: dict[int, str] = {
    0: "General",
    1: "0",
    2: "0.00",
    3: "#,##0",
    4: "#,##0.00",
    9: "0%",
    10: "0.00%",
    11: "0.00E+00",
    12: "# ?/?",
    13: "# ??/??",
    14: "mm-dd-yy",
    22: "m/d/yy h:mm",
    37: "#,##0 ;(#,##0)",
    38: "#,##0 ;[Red](#,##0)",
    39: "#,##0.00;(#,##0.00)",
    40: "#,##0.00;[Red](#,##0.00)",
    44: '_("$"* #,##0.00_);_("$"* \\(#,##0.00\\);_("$"* "-"??_);_(@_)',
    49: "@",
}

_VALID_DN_NAME_RE = re.compile(r"^(?:_xlnm\.[A-Za-z_]+|[A-Za-z_\\][A-Za-z0-9_.]*)$")
_SHEET_REF_RE = re.compile(r"(?:'([^'\[\]]+)'|([A-Za-z0-9_]+))!")
_CELL_REF_SHIFT_RE = re.compile(
    r"(?<![A-Za-z0-9_!])(\$?)([A-Za-z]{1,3})(\$?)(\d+)(?![A-Za-z0-9_(])"
)
_EXT_INDEX_RE = re.compile(r"\[(\d+)\]")
_EXT_TARGET_RE = re.compile(
    r"'?\[(\d+)\]([^'!]+)'?!\$?([A-Za-z]{1,3})\$?(\d+)"
)
_PURE_SINGLE_EXT_RE = re.compile(r"^\+?'?\[(\d+)\][^'!]+'?!\$?[A-Za-z]{1,3}\$?\d+$")

PEER_WORKBOOK_BY_INDEX: dict[str, str] = {
    "14": "Uslr202409.xlsx",
    "18": "Felr202409.xlsx",
    "19": "Tankerlr202409.xlsx",
}

# 14 Empirical Historical Driver Series (1990..2024 = Col L(12)..Col AT(46)) for BQML ARIMA_PLUS
BQML_DRIVER_SPECS: tuple[tuple[str, str, str, str, str, int], ...] = (
    # (domain_group, series_id, series_label, units, target_sheet, target_row)
    ("MACRO", "US_INFLATION_IDX_2020", "Inflation Forecast Index (2020=1.00)", "Index", "Input", 13),
    ("MACRO", "CE_PLANT_COST_INDEX", "Chemical Engineering Plant Cost Index", "Index", "Input", 17),
    ("MACRO", "NWE_INFLATION_IDX_2001", "NW European Inflation Index (2001=1.00)", "Index", "Input", 20),
    ("MACRO", "EUR_PER_USD_FX", "Euro per US Dollar Exchange Rate", "EUR/USD", "Input", 25),
    ("CRUDES", "DATED_BRENT_FOB", "Dated Brent Spot FOB North Sea", "$/bbl", "Input", 37),
    ("CRUDES", "URALS_CIF_NWE", "Urals CIF Northwest Europe", "$/bbl", "Input", 43),
    ("CRUDES", "AZERI_FOB_CEYHAN", "Azeri Light FOB Ceyhan (23$)", "$/bbl", "Input", 44),
    ("CRUDES", "ARAB_LIGHT_FOB_NWE", "Arab Light FOB Ras Tanura (NWE Formula, 23$)", "$/bbl", "Input", 45),
    ("CRUDES", "ES_SIDER_FOB_MED", "Es Sider Sweet Med FOB (23$)", "$/bbl", "Input", 47),
    ("FREIGHT", "DIRTY_VLCC_DUBAI_NWE", "Dirty Tanker Dubai to NWE", "$/bbl", "Freight", 12),
    ("FREIGHT", "DIRTY_BRENT_NWE", "Dirty Tanker Brent to NWE", "$/bbl", "Freight", 14),
    ("FREIGHT", "CLEAN_LR2_NSEA_USGC_WS", "LR2 North Sea to USGC Rate", "% WS", "Freight", 21),
    ("FREIGHT", "CLEAN_MR_TC2_WS", "MR Clean Tanker Atlantic Rate", "% WS", "Freight", 25),
    ("FREIGHT", "DIRTY_AFRAMAX_UKC_MED_WS", "Dirty Aframax 80kt UKC-Med Rate", "% WS", "Freight", 38),
)


@dataclass
class CompiledEulrPayload:
    """Complete BigQuery batch-load payload extracted from Eulr202409.xlsx + optional peers."""

    version_row: dict[str, Any]
    worksheet_rows: list[dict[str, Any]]
    style_rows: list[dict[str, Any]]
    cell_rows: list[dict[str, Any]]
    external_link_rows: list[dict[str, Any]]
    driver_trajectory_rows: list[dict[str, Any]]
    snapshot: EulrBaselineSnapshot


def _apply_ooxml_tint(rgb6: str, tint: float) -> str:
    if abs(tint) <= 1e-6:
        return f"FF{rgb6.upper()}"
    r = int(rgb6[0:2], 16) / 255.0
    g = int(rgb6[2:4], 16) / 255.0
    b = int(rgb6[4:6], 16) / 255.0
    h, lum, sat = colorsys.rgb_to_hls(r, g, b)
    if tint < 0.0:
        lum = lum * (1.0 + tint)
    else:
        lum = lum * (1.0 - tint) + tint
    lum = min(1.0, max(0.0, lum))
    nr, ng, nb = colorsys.hls_to_rgb(h, lum, sat)
    return f"FF{int(round(nr * 255)):02X}{int(round(ng * 255)):02X}{int(round(nb * 255)):02X}"


def _parse_theme_palette(zf: zipfile.ZipFile) -> tuple[str, ...]:
    if "xl/theme/theme1.xml" not in zf.namelist():
        return _DEFAULT_OFFICE_THEME
    try:
        root = ET.fromstring(zf.read("xl/theme/theme1.xml"))
        ns = {"a": _DRAW_NS}
        scheme = root.find(".//a:clrScheme", ns)
        if scheme is None:
            return _DEFAULT_OFFICE_THEME
        by_tag: dict[str, str] = {}
        for child in list(scheme):
            tag = child.tag.split("}")[-1]
            srgb = child.find("a:srgbClr", ns)
            sys_c = child.find("a:sysClr", ns)
            hex6 = (
                srgb.attrib.get("val")
                if srgb is not None
                else (
                    sys_c.attrib.get("lastClr") or sys_c.attrib.get("val")
                    if sys_c is not None
                    else None
                )
            )
            if hex6 and len(hex6) == 6:
                by_tag[tag] = hex6.upper()
        ordered = (
            "lt1",
            "dk1",
            "lt2",
            "dk2",
            "accent1",
            "accent2",
            "accent3",
            "accent4",
            "accent5",
            "accent6",
            "hlink",
            "folHlink",
        )
        return tuple(by_tag.get(t, _DEFAULT_OFFICE_THEME[i]) for i, t in enumerate(ordered))
    except Exception:
        return _DEFAULT_OFFICE_THEME


def _resolve_color_elem(elem: ET.Element | None, palette: tuple[str, ...]) -> str | None:
    if elem is None:
        return None
    rgb = elem.attrib.get("rgb")
    tint = float(elem.attrib.get("tint", "0.0") or 0.0)
    if rgb:
        clean = rgb.strip().upper()
        if len(clean) == 6:
            return _apply_ooxml_tint(clean, tint)
        if len(clean) == 8:
            if clean == "00000000":
                return None
            hex6 = clean[2:]
            return _apply_ooxml_tint(hex6, tint) if abs(tint) > 1e-6 else f"FF{hex6}"
    theme_attr = elem.attrib.get("theme")
    if theme_attr is not None:
        idx = int(theme_attr)
        if 0 <= idx < len(palette):
            return _apply_ooxml_tint(palette[idx], tint)
    idx_attr = elem.attrib.get("indexed")
    if idx_attr is not None:
        idx = int(idx_attr)
        if idx in (64, 65):
            return None
        if 0 <= idx < len(COLOR_INDEX):
            raw = str(COLOR_INDEX[idx]).strip().upper()
            hex6 = raw[-6:] if len(raw) >= 6 else ""
            if len(hex6) == 6 and all(c in "0123456789ABCDEF" for c in hex6):
                return f"FF{hex6}"
    return None


def _parse_styles_xml(zf: zipfile.ZipFile, palette: tuple[str, ...]) -> dict[int, StyleMeta]:
    if "xl/styles.xml" not in zf.namelist():
        return {
            0: StyleMeta(
                style_id=0,
                number_format="General",
                font={"name": "Calibri", "size": 10.0, "bold": False, "italic": False, "color": None},
                fill={"fill_type": None, "fg_color": None},
                border={},
                alignment={},
            )
        }
    root = ET.fromstring(zf.read("xl/styles.xml"))
    ns = {"s": _MAIN_NS}

    num_fmts = dict(_BUILTIN_NUM_FMTS)
    nf_parent = root.find("s:numFmts", ns)
    if nf_parent is not None:
        for nf in nf_parent.findall("s:numFmt", ns):
            nf_id = int(nf.attrib.get("numFmtId", "0"))
            num_fmts[nf_id] = nf.attrib.get("formatCode", "General")

    fonts: list[dict[str, Any]] = []
    f_parent = root.find("s:fonts", ns)
    if f_parent is not None:
        for f_el in f_parent.findall("s:font", ns):
            name_el = f_el.find("s:name", ns)
            sz_el = f_el.find("s:sz", ns)
            b_el = f_el.find("s:b", ns)
            i_el = f_el.find("s:i", ns)
            c_el = f_el.find("s:color", ns)
            fonts.append(
                {
                    "name": name_el.attrib.get("val", "Arial") if name_el is not None else "Arial",
                    "size": float(sz_el.attrib.get("val", "10")) if sz_el is not None else 10.0,
                    "bold": b_el is not None and b_el.attrib.get("val", "1") != "0",
                    "italic": i_el is not None and i_el.attrib.get("val", "1") != "0",
                    "color": _resolve_color_elem(c_el, palette),
                }
            )

    fills: list[dict[str, Any]] = []
    fl_parent = root.find("s:fills", ns)
    if fl_parent is not None:
        for fl_el in fl_parent.findall("s:fill", ns):
            pat = fl_el.find("s:patternFill", ns)
            if pat is None:
                fills.append({"fill_type": None, "fg_color": None})
                continue
            ptype = pat.attrib.get("patternType")
            fg = _resolve_color_elem(pat.find("s:fgColor", ns), palette)
            bg = _resolve_color_elem(pat.find("s:bgColor", ns), palette)
            if ptype in (None, "none"):
                fills.append({"fill_type": None, "fg_color": None})
            else:
                fills.append({"fill_type": ptype, "fg_color": fg or bg})

    borders: list[dict[str, Any]] = []
    bd_parent = root.find("s:borders", ns)
    if bd_parent is not None:
        for bd_el in bd_parent.findall("s:border", ns):
            bdict: dict[str, Any] = {}
            for side in ("left", "right", "top", "bottom"):
                s_el = bd_el.find(f"s:{side}", ns)
                if s_el is not None and s_el.attrib.get("style"):
                    bdict[side] = {
                        "style": s_el.attrib["style"],
                        "color": _resolve_color_elem(s_el.find("s:color", ns), palette),
                    }
            borders.append(bdict)

    styles: dict[int, StyleMeta] = {}
    xfs_parent = root.find("s:cellXfs", ns)
    if xfs_parent is not None:
        for idx, xf in enumerate(xfs_parent.findall("s:xf", ns)):
            nf_id = int(xf.attrib.get("numFmtId", "0"))
            font_id = int(xf.attrib.get("fontId", "0"))
            fill_id = int(xf.attrib.get("fillId", "0"))
            border_id = int(xf.attrib.get("borderId", "0"))
            al_el = xf.find("s:alignment", ns)
            align_dict: dict[str, Any] = {}
            if al_el is not None:
                if al_el.attrib.get("horizontal"):
                    align_dict["horizontal"] = al_el.attrib["horizontal"]
                if al_el.attrib.get("vertical"):
                    align_dict["vertical"] = al_el.attrib["vertical"]
                if al_el.attrib.get("wrapText") in ("1", "true"):
                    align_dict["wrap_text"] = True
            styles[idx] = StyleMeta(
                style_id=idx,
                number_format=num_fmts.get(nf_id, "General"),
                font=fonts[font_id] if 0 <= font_id < len(fonts) else {"name": "Arial", "size": 10.0},
                fill=fills[fill_id] if 0 <= fill_id < len(fills) else {"fill_type": None, "fg_color": None},
                border=borders[border_id] if 0 <= border_id < len(borders) else {},
                alignment=align_dict,
            )
    return styles


def _parse_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    strings: list[str] = []
    si_tag = f"{{{_MAIN_NS}}}si"
    t_tag = f"{{{_MAIN_NS}}}t"
    with zf.open("xl/sharedStrings.xml") as fp:
        for _, elem in ET.iterparse(fp, events=("end",)):
            if elem.tag == si_tag:
                parts = [t.text or "" for t in elem.iter(t_tag)]
                strings.append("".join(parts))
                elem.clear()
    return strings


def _shift_formula(master_formula: str, d_row: int, d_col: int) -> str:
    """Shift non-anchored A1 coordinates inside an Excel shared formula."""
    if d_row == 0 and d_col == 0:
        return master_formula

    def _repl(match: re.Match[str]) -> str:
        col_abs, col_letters, row_abs, row_digits = match.groups()
        c_idx = col_letter_to_index(col_letters)
        r_idx = int(row_digits)
        if not col_abs:
            c_idx = max(1, c_idx + d_col)
        if not row_abs:
            r_idx = max(1, r_idx + d_row)
        return f"{col_abs}{index_to_col_letter(c_idx)}{row_abs}{r_idx}"

    # Avoid shifting inside quoted string literals
    parts = master_formula.split('"')
    for i in range(0, len(parts), 2):
        parts[i] = _CELL_REF_SHIFT_RE.sub(_repl, parts[i])
    return '"'.join(parts)


def _classify_link_health_tier(link_idx: str, raw_url: str) -> str:
    idx_num = int(link_idx)
    low = raw_url.lower()
    if idx_num <= 13 and ("file:///" in low or "gpmo" in low or "2000" in low):
        return "FROZEN_LEGACY_PATH"
    if "new lpd" in low or "sr_model" in low or "mnemonics" in low or "rpline" in low:
        return "SHARED_REFERENCE_DB"
    return "ACTIVE_PEER_MODEL"


def _parse_external_link_targets(zf: zipfile.ZipFile) -> dict[str, str]:
    targets: dict[str, str] = {}
    for name in zf.namelist():
        m = re.match(r"^xl/externalLinks/_rels/externalLink(\d+)\.xml\.rels$", name)
        if not m:
            continue
        idx = m.group(1)
        root = ET.fromstring(zf.read(name))
        for rel in root.findall(f"{{{_PKG_REL_NS}}}Relationship"):
            raw_t = rel.attrib.get("Target", "")
            if raw_t:
                targets[idx] = urllib.parse.unquote(raw_t)
                break
    return targets


def _extract_peer_numeric_values(
    peer_xlsx: Path, target_sheets_lower: set[str]
) -> dict[str, dict[str, float]]:
    """Fast streaming read of cached numeric values from a peer .xlsx file."""
    out: dict[str, dict[str, float]] = {}
    if not peer_xlsx.exists() or not target_sheets_lower:
        return out
    with zipfile.ZipFile(peer_xlsx, "r") as zf:
        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rid_to_path: dict[str, str] = {}
        for rel in rels_root.findall(f"{{{_PKG_REL_NS}}}Relationship"):
            rid = rel.attrib.get("Id", "")
            tgt = rel.attrib.get("Target", "").lstrip("/")
            if not tgt.startswith("xl/"):
                tgt = f"xl/{tgt}"
            rid_to_path[rid] = tgt

        for sh_el in wb_root.findall(f".//{{{_MAIN_NS}}}sheet"):
            sname = sh_el.attrib.get("name", "")
            if sname.lower() not in target_sheets_lower:
                continue
            rid = sh_el.attrib.get(f"{{{_REL_NS}}}id", "")
            sh_path = rid_to_path.get(rid, "")
            if sh_path not in zf.namelist():
                continue
            vals: dict[str, float] = {}
            c_tag = f"{{{_MAIN_NS}}}c"
            v_tag = f"{{{_MAIN_NS}}}v"
            with zf.open(sh_path) as fp:
                for _, elem in ET.iterparse(fp, events=("end",)):
                    if elem.tag == c_tag:
                        coord = elem.attrib.get("r", "")
                        ctype = elem.attrib.get("t", "")
                        if coord and ctype not in ("s", "str", "e", "inlineStr"):
                            vel = elem.find(v_tag)
                            if vel is not None and vel.text is not None:
                                try:
                                    vals[coord.replace("$", "").upper()] = float(vel.text)
                                except ValueError:
                                    pass
                        elem.clear()
            out[sname.lower()] = vals
    return out


def _classify_eulr_semantic_role(
    sheet_name: str, coord: str, row_num: int, col_num: int, formula: str | None, has_ext: bool
) -> str:
    if (sheet_name == "KeyInputs" and row_num == 10 and col_num >= 14) or (
        sheet_name == "Carbon" and coord in ("A5", "A6")
    ):
        return "SCENARIO_SWITCH"
    if formula is not None:
        if has_ext:
            return "EXTERNAL_LINK_FORMULA"
        if sheet_name in ("KeyInputs", "Yields", "Info", "Checks"):
            return "ACYCLIC_LIVE_FORMULA"
        return "EQUILIBRIUM_FORMULA"
    if sheet_name in ("Input", "Crudes", "Freight", "KeyInputs", "Yields") and col_num >= 12:
        return "INPUT_ASSUMPTION"
    return "STATIC_LABEL_OR_VALUE"


def _is_valid_defined_name(name: str, attr_text: str, valid_sheets: set[str]) -> bool:
    clean_name = name.strip()
    clean_attr = attr_text.strip()
    if not clean_name or not clean_attr or clean_name.endswith("."):
        return False
    if not _VALID_DN_NAME_RE.match(clean_name):
        return False
    if "[" in clean_attr or "]" in clean_attr or "#REF!" in clean_attr or "#N/A" in clean_attr:
        return False
    if "!" in clean_attr:
        matches = _SHEET_REF_RE.findall(clean_attr)
        if not matches:
            return False
        for quoted_s, bare_s in matches:
            if (quoted_s or bare_s) not in valid_sheets:
                return False
    return True


def compile_eulr_workbook(
    xlsx_path: Path,
    workbook_id: str,
    version_id: str,
    version_label: str = "EULR European Refining Equilibrium LR202409 Golden Baseline",
    references_dir: Path | None = None,
) -> CompiledEulrPayload:
    """Decompile `Eulr202409.xlsx` (and optional 3 active peer .xlsx files) in a single OpenXML pass."""
    created_ts = datetime.now(UTC).isoformat()
    active_set = set(ACTIVE_19_EULR_TABS)

    with zipfile.ZipFile(xlsx_path, "r") as zf:
        palette = _parse_theme_palette(zf)
        styles = _parse_styles_xml(zf, palette)
        shared_strings = _parse_shared_strings(zf)
        ext_targets = _parse_external_link_targets(zf)

        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rid_to_path: dict[str, str] = {}
        for rel in rels_root.findall(f"{{{_PKG_REL_NS}}}Relationship"):
            rid = rel.attrib.get("Id", "")
            tgt = rel.attrib.get("Target", "").lstrip("/")
            if not tgt.startswith("xl/"):
                tgt = f"xl/{tgt}"
            rid_to_path[rid] = tgt

        # Calc properties
        calc_el = wb_root.find(f"{{{_MAIN_NS}}}calcPr")
        calc_props: dict[str, Any] = {
            "iterate": calc_el.attrib.get("iterate", "1") == "1" if calc_el is not None else True,
            "iterateCount": int(calc_el.attrib.get("iterateCount", "10")) if calc_el is not None else 10,
            "iterateDelta": float(calc_el.attrib.get("iterateDelta", "0.001")) if calc_el is not None else 0.001,
        }

        # Sheet order & paths (retire hidden shooju_addin)
        ordered_sheet_entries: list[tuple[int, str, str, str]] = []
        raw_sheets_by_idx: dict[int, str] = {}
        for raw_idx, sh_el in enumerate(wb_root.findall(f".//{{{_MAIN_NS}}}sheet")):
            sname = sh_el.attrib.get("name", "")
            raw_sheets_by_idx[raw_idx] = sname
            state = sh_el.attrib.get("state", "visible")
            rid = sh_el.attrib.get(f"{{{_REL_NS}}}id", "")
            if sname not in active_set:
                continue
            ordered_sheet_entries.append(
                (len(ordered_sheet_entries), sname, state, rid_to_path[rid])
            )

        # Sanitized DefinedNames
        named_ranges: list[dict[str, Any]] = []
        dn_parent = wb_root.find(f"{{{_MAIN_NS}}}definedNames")
        if dn_parent is not None:
            for dn_el in dn_parent.findall(f"{{{_MAIN_NS}}}definedName"):
                dn_name = dn_el.attrib.get("name", "")
                dn_val = (dn_el.text or "").strip()
                local_id = dn_el.attrib.get("localSheetId")
                scope_sheet: str | None = None
                if local_id is not None:
                    scope_sheet = raw_sheets_by_idx.get(int(local_id))
                    if scope_sheet not in active_set:
                        continue
                if _is_valid_defined_name(dn_name, dn_val, active_set):
                    named_ranges.append(
                        {"name": dn_name.strip(), "attr_text": dn_val, "scope_sheet": scope_sheet}
                    )

        worksheets_meta: dict[str, WorksheetMeta] = {}
        cells_by_sheet: dict[str, dict[tuple[int, int], TwinCell]] = {}
        raw_ext_candidates: list[tuple[str, str, int, int, str, float]] = []

        for sh_idx, sname, visibility, sh_xml_path in ordered_sheet_entries:
            sh_root = ET.fromstring(zf.read(sh_xml_path))
            ns = {"s": _MAIN_NS}

            # Tab color
            pr_el = sh_root.find("s:sheetPr/s:tabColor", ns)
            tab_rgb = _resolve_color_elem(pr_el, palette)

            # SheetView (zoom, gridlines, freeze panes)
            sv_el = sh_root.find("s:sheetViews/s:sheetView", ns)
            zoom_scale = int(sv_el.attrib.get("zoomScale", "100")) if sv_el is not None else 100
            show_grid = (
                sv_el.attrib.get("showGridLines", "1") not in ("0", "false")
                if sv_el is not None
                else True
            )
            freeze_coord: str | None = None
            if sv_el is not None:
                pane_el = sv_el.find("s:pane", ns)
                if pane_el is not None and pane_el.attrib.get("state", "").startswith("frozen"):
                    freeze_coord = pane_el.attrib.get("topLeftCell")

            # Columns (expanding min..max spans!)
            col_widths: dict[str, float] = {}
            hidden_cols: list[str] = []
            cols_el = sh_root.find("s:cols", ns)
            if cols_el is not None:
                for col_el in cols_el.findall("s:col", ns):
                    c_min = int(col_el.attrib.get("min", "1"))
                    c_max = min(int(col_el.attrib.get("max", str(c_min))), 300)
                    w_str = col_el.attrib.get("width")
                    is_hidden = col_el.attrib.get("hidden") in ("1", "true")
                    w_val = round(float(w_str), 4) if w_str is not None else None
                    for c_i in range(c_min, c_max + 1):
                        col_let = index_to_col_letter(c_i)
                        if w_val is not None:
                            col_widths[col_let] = w_val
                        if is_hidden:
                            hidden_cols.append(col_let)

            # Merged ranges
            merged_ranges: list[str] = []
            mc_parent = sh_root.find("s:mergeCells", ns)
            if mc_parent is not None:
                for mc_el in mc_parent.findall("s:mergeCell", ns):
                    ref = mc_el.attrib.get("ref")
                    if ref:
                        merged_ranges.append(ref)

            # Rows & Cells
            row_heights: dict[int, float] = {}
            hidden_rows: list[int] = []
            shared_masters: dict[str, tuple[int, int, str]] = {}
            cse_ranges: list[tuple[int, int, int, int]] = []
            sh_cells: dict[tuple[int, int], TwinCell] = {}
            max_r = 1
            max_c = 1

            sdata = sh_root.find("s:sheetData", ns)
            if sdata is not None:
                for row_el in sdata.findall("s:row", ns):
                    r_num = int(row_el.attrib.get("r", "0") or 0)
                    ht_str = row_el.attrib.get("ht")
                    if ht_str is not None and r_num > 0:
                        row_heights[r_num] = round(float(ht_str), 3)
                    if row_el.attrib.get("hidden") in ("1", "true") and r_num > 0:
                        hidden_rows.append(r_num)

                    for c_el in row_el.findall("s:c", ns):
                        coord = c_el.attrib.get("r", "")
                        if not coord:
                            continue
                        r_idx, c_idx = split_a1_coord(coord)
                        style_id = int(c_el.attrib.get("s", "0") or 0)
                        ctype = c_el.attrib.get("t", "")

                        f_el = c_el.find("s:f", ns)
                        v_el = c_el.find("s:v", ns)
                        is_el = c_el.find("s:is", ns)

                        raw_formula: str | None = None
                        is_cse = False
                        if f_el is not None:
                            ftype = f_el.attrib.get("t", "")
                            ftext = (f_el.text or "").strip()
                            if ftype == "shared":
                                si = f_el.attrib.get("si", "")
                                if ftext:
                                    shared_masters[si] = (r_idx, c_idx, ftext)
                                    raw_formula = f"={ftext}"
                                elif si in shared_masters:
                                    mr, mc, mf = shared_masters[si]
                                    raw_formula = f"={_shift_formula(mf, r_idx - mr, c_idx - mc)}"
                            elif ftype == "array":
                                is_cse = True
                                ref_span = f_el.attrib.get("ref", "")
                                if ref_span and ":" in ref_span:
                                    p1, p2 = ref_span.split(":", 1)
                                    r1, c1 = split_a1_coord(p1)
                                    r2, c2 = split_a1_coord(p2)
                                    cse_ranges.append((r1, c1, r2, c2))
                                if ftext:
                                    raw_formula = f"={ftext}"
                            else:
                                if ftext:
                                    raw_formula = f"={ftext}"

                        num_val: float | None = None
                        str_val: str | None = None
                        dtype = "NUMERIC"

                        v_raw = v_el.text if v_el is not None else None
                        if ctype == "s":
                            dtype = "STRING"
                            if v_raw is not None:
                                s_idx = int(v_raw)
                                str_val = shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else ""
                        elif ctype == "str":
                            dtype = "FORMULA" if raw_formula else "STRING"
                            str_val = v_raw or ""
                        elif ctype == "inlineStr":
                            dtype = "STRING"
                            if is_el is not None:
                                str_val = "".join(t.text or "" for t in is_el.iter(f"{{{_MAIN_NS}}}t"))
                        elif ctype == "b":
                            dtype = "FORMULA" if raw_formula else "BOOL"
                            bool_bool = v_raw == "1"
                            num_val = 1.0 if bool_bool else 0.0
                            str_val = "TRUE" if bool_bool else "FALSE"
                        elif ctype == "e":
                            dtype = "ERROR"
                            str_val = v_raw or "#VALUE!"
                        else:
                            if v_raw is not None:
                                try:
                                    num_val = float(v_raw)
                                except ValueError:
                                    str_val = v_raw
                                    dtype = "STRING"

                        if raw_formula is not None and dtype != "ERROR":
                            dtype = "FORMULA"

                        # Skip empty formatting bloat unless it carries fill or border
                        if raw_formula is None and num_val is None and str_val is None:
                            st_meta = styles.get(style_id)
                            has_visual_box = bool(
                                st_meta
                                and (
                                    st_meta.fill.get("fg_color") is not None
                                    or bool(st_meta.border)
                                )
                            )
                            if not has_visual_box:
                                continue
                            dtype = "MERGED_STYLE"

                        if r_idx > max_r:
                            max_r = r_idx
                        if c_idx > max_c:
                            max_c = c_idx

                        has_ext = bool(raw_formula and _EXT_INDEX_RE.search(raw_formula))
                        if has_ext and raw_formula:
                            raw_ext_candidates.append(
                                (sname, coord, r_idx, c_idx, raw_formula, num_val or 0.0)
                            )

                        role = _classify_eulr_semantic_role(
                            sname, coord, r_idx, c_idx, raw_formula, has_ext
                        )
                        sh_cells[(r_idx, c_idx)] = TwinCell(
                            sheet_name=sname,
                            cell_coord=coord,
                            row_num=r_idx,
                            col_num=c_idx,
                            data_type=dtype,
                            numeric_value=num_val,
                            string_value=str_val,
                            raw_formula=raw_formula,
                            is_array_cse=is_cse,
                            has_external_link=has_ext,
                            style_id=style_id,
                            semantic_role=role,
                        )

            # Propagate CSE flag to slave cells inside multi-cell array spans
            for r1, c1, r2, c2 in cse_ranges:
                master_cell = sh_cells.get((r1, c1))
                mf = master_cell.raw_formula if master_cell else None
                for rr in range(r1, r2 + 1):
                    for cc in range(c1, c2 + 1):
                        tc = sh_cells.get((rr, cc))
                        if tc is not None:
                            tc.is_array_cse = True
                            if tc.raw_formula is None and mf is not None:
                                tc.raw_formula = mf
                                tc.data_type = "FORMULA"

            sheet_view = {
                "zoom_scale": zoom_scale,
                "show_grid_lines": show_grid,
                "hidden_cols": hidden_cols,
                "hidden_rows": hidden_rows,
            }
            worksheets_meta[sname] = WorksheetMeta(
                sheet_index=sh_idx,
                sheet_name=sname,
                visibility=visibility,
                tab_color_rgb=tab_rgb,
                max_row=max_r,
                max_col=max_c,
                merged_ranges=merged_ranges,
                col_widths=col_widths,
                row_heights=row_heights,
                freeze_panes_coord=freeze_coord,
                sheet_view=sheet_view,
            )
            cells_by_sheet[sname] = sh_cells

    # Resolve optional 3-peer live values (Uslr, Felr, Tankerlr)
    peer_sheet_requests: dict[str, set[str]] = {"14": set(), "18": set(), "19": set()}
    parsed_ext_tuples: list[
        tuple[str, str, int, int, str, float, str, str | None, str | None]
    ] = []
    for sname, coord, r_idx, c_idx, rf, base_v in raw_ext_candidates:
        body = rf.lstrip("=")
        m_tgt = _EXT_TARGET_RE.search(body)
        if m_tgt:
            l_idx = m_tgt.group(1)
            src_sh = (m_tgt.group(2) or "").strip()
            src_cell = f"{m_tgt.group(3).upper()}{m_tgt.group(4)}"
            if l_idx in peer_sheet_requests and src_sh:
                peer_sheet_requests[l_idx].add(src_sh.lower())
        else:
            m_any = _EXT_INDEX_RE.search(body)
            l_idx = m_any.group(1) if m_any else "0"
            src_sh = None
            src_cell = None
        parsed_ext_tuples.append(
            (sname, coord, r_idx, c_idx, rf, base_v, l_idx, src_sh, src_cell)
        )

    peer_caches: dict[str, dict[str, dict[str, float]]] = {}
    if references_dir is not None and references_dir.exists():
        for l_idx, peer_fname in PEER_WORKBOOK_BY_INDEX.items():
            if peer_sheet_requests[l_idx]:
                peer_caches[l_idx] = _extract_peer_numeric_values(
                    references_dir / peer_fname, peer_sheet_requests[l_idx]
                )

    external_links_map: dict[tuple[str, int, int], ExternalLinkCell] = {}
    external_link_rows: list[dict[str, Any]] = []
    for sname, coord, r_idx, c_idx, rf, base_v, l_idx, src_sh, src_cell in parsed_ext_tuples:
        raw_url = ext_targets.get(l_idx, f"externalLink{l_idx}.xlsx")
        wb_name = posixpath.basename(raw_url.replace("\\", "/")) or f"externalLink{l_idx}.xlsx"
        tier = _classify_link_health_tier(l_idx, raw_url)

        peer_val: float | None = None
        is_updated = False
        if (
            l_idx in peer_caches
            and src_sh
            and src_cell
            and _PURE_SINGLE_EXT_RE.match(rf.lstrip("=").strip())
        ):
            pv = peer_caches[l_idx].get(src_sh.lower(), {}).get(src_cell)
            if pv is not None:
                peer_val = float(pv)
                if abs(peer_val - base_v) / max(abs(base_v), 1e-12) > 1e-8:
                    is_updated = True

        ext_rec = ExternalLinkCell(
            vintage_tag="202409",
            link_health_tier=tier,
            external_link_idx=l_idx,
            sharepoint_url=raw_url,
            external_workbook_name=wb_name,
            source_sheet=src_sh,
            source_cell_a1=src_cell,
            target_sheet=sname,
            target_coord=coord,
            target_row=r_idx,
            target_col=c_idx,
            baseline_cached_value=float(base_v),
            peer_live_value=peer_val,
            is_peer_updated=is_updated,
            raw_formula=rf,
        )
        external_links_map[(sname, r_idx, c_idx)] = ext_rec
        external_link_rows.append(
            {
                "workbook_id": workbook_id,
                "version_id": version_id,
                "vintage_tag": ext_rec.vintage_tag,
                "link_health_tier": ext_rec.link_health_tier,
                "external_link_idx": ext_rec.external_link_idx,
                "sharepoint_url": ext_rec.sharepoint_url,
                "external_workbook_name": ext_rec.external_workbook_name,
                "source_sheet": ext_rec.source_sheet,
                "source_cell_a1": ext_rec.source_cell_a1,
                "target_sheet": ext_rec.target_sheet,
                "target_coord": ext_rec.target_coord,
                "target_row": ext_rec.target_row,
                "target_col": ext_rec.target_col,
                "baseline_cached_value": ext_rec.baseline_cached_value,
                "peer_live_value": ext_rec.peer_live_value,
                "is_peer_updated": ext_rec.is_peer_updated,
                "raw_formula": ext_rec.raw_formula,
            }
        )

    # Extract 1990..2024 (Col L=12 .. Col AT=46) empirical driver actuals for BQML ARIMA_PLUS
    driver_rows: list[dict[str, Any]] = []
    for domain, sid, slabel, units, t_sheet, t_row in BQML_DRIVER_SPECS:
        sh_map = cells_by_sheet.get(t_sheet, {})
        for col_i in range(12, 47):  # 1990..2024 inclusive (35 annual points)
            yr = 1990 + (col_i - 12)
            cell = sh_map.get((t_row, col_i))
            if cell is not None and cell.numeric_value is not None:
                driver_rows.append(
                    {
                        "domain_group": domain,
                        "series_id": sid,
                        "series_label": slabel,
                        "units": units,
                        "target_sheet": t_sheet,
                        "target_row": t_row,
                        "forecast_year": yr,
                        "series_date": f"{yr:04d}-01-01",
                        "actual_value": round(float(cell.numeric_value), 6),
                    }
                )

    # Serialize BigQuery table rows
    worksheet_rows: list[dict[str, Any]] = []
    for sname in ACTIVE_19_EULR_TABS:
        wm = worksheets_meta[sname]
        worksheet_rows.append(
            {
                "workbook_id": workbook_id,
                "version_id": version_id,
                "sheet_index": wm.sheet_index,
                "sheet_name": wm.sheet_name,
                "visibility": wm.visibility,
                "tab_color_rgb": wm.tab_color_rgb,
                "max_row": wm.max_row,
                "max_col": wm.max_col,
                "merged_ranges_json": json.dumps(wm.merged_ranges),
                "col_widths_json": json.dumps(wm.col_widths),
                "row_heights_json": json.dumps({str(k): v for k, v in wm.row_heights.items()}),
                "freeze_panes_coord": wm.freeze_panes_coord,
                "sheet_view_json": json.dumps(wm.sheet_view),
            }
        )

    style_rows: list[dict[str, Any]] = []
    for sid, sm in sorted(styles.items()):
        style_rows.append(
            {
                "workbook_id": workbook_id,
                "version_id": version_id,
                "style_id": sm.style_id,
                "number_format": sm.number_format,
                "font_json": json.dumps(sm.font),
                "fill_json": json.dumps(sm.fill),
                "border_json": json.dumps(sm.border),
                "alignment_json": json.dumps(sm.alignment),
            }
        )

    cell_rows: list[dict[str, Any]] = []
    total_formulas = 0
    for sname in ACTIVE_19_EULR_TABS:
        for (_, _), tc in sorted(cells_by_sheet[sname].items()):
            if tc.raw_formula is not None:
                total_formulas += 1
            cell_rows.append(
                {
                    "workbook_id": workbook_id,
                    "version_id": version_id,
                    "sheet_name": tc.sheet_name,
                    "cell_coord": tc.cell_coord,
                    "row_num": tc.row_num,
                    "col_num": tc.col_num,
                    "data_type": tc.data_type,
                    "numeric_value": tc.numeric_value,
                    "string_value": tc.string_value,
                    "raw_formula": tc.raw_formula,
                    "is_array_cse": tc.is_array_cse,
                    "has_external_link": tc.has_external_link,
                    "style_id": tc.style_id,
                    "semantic_role": tc.semantic_role,
                }
            )

    version_row = {
        "workbook_id": workbook_id,
        "version_id": version_id,
        "version_label": version_label,
        "total_sheets": len(ACTIVE_19_EULR_TABS),
        "total_cells": len(cell_rows),
        "total_formulas": total_formulas,
        "total_external_links": len(external_link_rows),
        "named_ranges_json": json.dumps(named_ranges),
        "calc_properties_json": json.dumps(calc_props),
        "created_at": created_ts,
    }

    snapshot = EulrBaselineSnapshot(
        workbook_id=workbook_id,
        version_id=version_id,
        worksheets=worksheets_meta,
        styles=styles,
        cells_by_sheet=cells_by_sheet,
        external_links=external_links_map,
        named_ranges=named_ranges,
        calc_properties=calc_props,
    )

    return CompiledEulrPayload(
        version_row=version_row,
        worksheet_rows=worksheet_rows,
        style_rows=style_rows,
        cell_rows=cell_rows,
        external_link_rows=external_link_rows,
        driver_trajectory_rows=driver_rows,
        snapshot=snapshot,
    )
