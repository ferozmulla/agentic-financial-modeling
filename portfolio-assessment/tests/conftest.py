from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any


def build_synthetic_xlsx(
    target_path: Path,
    sheets: dict[str, list[dict[str, Any]]],
    calc_pr_attrs: dict[str, str] | None = None,
    defined_names: list[tuple[str, str]] | None = None,
    external_links: list[str] | None = None,
    connections_xml: bool = False,
    vba_payload: bytes | None = None,
    hidden_sheets: set[str] | None = None,
) -> Path:
    """Create a minimal valid OpenXML .xlsx/.xlsm archive for deterministic unit tests."""
    hidden = hidden_sheets or set()
    calc_attrs = " ".join(f'{k}="{v}"' for k, v in (calc_pr_attrs or {"calcId": "191029"}).items())

    sheet_entries = []
    wb_rels = []
    for idx, sname in enumerate(sheets, start=1):
        state_attr = ' state="veryHidden"' if sname in hidden else ""
        sheet_entries.append(f'<sheet name="{sname}" sheetId="{idx}" r:id="rId{idx}"{state_attr}/>')
        wb_rels.append(
            f'<Relationship Id="rId{idx}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
        )

    ext_refs_xml = []
    for e_idx, _ in enumerate(external_links or [], start=1):
        rid = f"rIdExt{e_idx}"
        ext_refs_xml.append(f'<externalReference r:id="{rid}"/>')
        wb_rels.append(
            f'<Relationship Id="{rid}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" '
            f'Target="externalLinks/externalLink{e_idx}.xml"/>'
        )

    dnames_xml = "".join(
        f'<definedName name="{n}">{body}</definedName>' for n, body in (defined_names or [])
    )
    ext_block = f"<externalReferences>{''.join(ext_refs_xml)}</externalReferences>" if ext_refs_xml else ""
    dn_block = f"<definedNames>{dnames_xml}</definedNames>" if dnames_xml else ""

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{''.join(sheet_entries)}</sheets>"
        f"{ext_block}{dn_block}"
        f"<calcPr {calc_attrs}/>"
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(wb_rels)}"
        "</Relationships>"
    )

    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)

        for e_idx, url in enumerate(external_links or [], start=1):
            zf.writestr(
                f"xl/externalLinks/externalLink{e_idx}.xml",
                '<externalLink xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<externalBook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId1"/>'
                "</externalLink>",
            )
            zf.writestr(
                f"xl/externalLinks/_rels/externalLink{e_idx}.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rId1" Type="externalLinkPath" Target="{url}" TargetMode="External"/>'
                "</Relationships>",
            )

        if connections_xml:
            zf.writestr(
                "xl/connections.xml",
                '<connections xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<connection id="1" name="ODBC_Feed"/></connections>',
            )

        if vba_payload is not None:
            zf.writestr("xl/vbaProject.bin", vba_payload)

        for idx, (_, cell_list) in enumerate(sheets.items(), start=1):
            c_tags = []
            for item in cell_list:
                r = item["r"]
                t_attr = f' t="{item["t"]}"' if item.get("t") else ""
                s_attr = f' s="{item["s"]}"' if item.get("s") else ""
                inner = ""
                if "f" in item and item["f"] is not None:
                    f_attrs = item.get("f_attrs", "")
                    sp = f" {f_attrs}" if f_attrs else ""
                    inner += f"<f{sp}>{item['f']}</f>" if item["f"] != "" else f"<f{sp}/>"
                if "v" in item and item["v"] is not None:
                    inner += f"<v>{item['v']}</v>"
                if inner:
                    c_tags.append(f'<c r="{r}"{t_attr}{s_attr}>{inner}</c>')
                else:
                    c_tags.append(f'<c r="{r}"{t_attr}{s_attr}/>')
            sheet_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData><row r="1">{"".join(c_tags)}</row></sheetData>'
                "</worksheet>"
            )
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", sheet_xml)

    return target_path
