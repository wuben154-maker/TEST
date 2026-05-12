"""run_ooxml_structure.py — OOXML container structure fallback worker.

This worker parses only ZIP metadata, content types, and relationship files.
It does not expose raw sample bytes or macro source. It is used when Office
macro extraction is incomplete so the parent tool can still report structural
facts such as macro-enabled declarations, missing vbaProject.bin, external
relationships, and embedded OLE objects.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import zipfile
from pathlib import Path
from xml.etree import ElementTree

_MAX_PARTS = 200
_MAX_RELATIONSHIPS = 100


def _empty_result(error: str | None = None) -> dict:
    result: dict = {
        "document_metadata": {},
        "ooxml_parts": [],
        "remote_templates": [],
        "embedded_objects": [],
        "warnings": [],
    }
    if error is not None:
        result["error"] = error
    return result


def _read_zip_text(zf: zipfile.ZipFile, name: str) -> str:
    try:
        return zf.read(name).decode("utf-8", errors="replace")
    except KeyError:
        return ""


def _content_types(zf: zipfile.ZipFile) -> tuple[list[str], dict[str, str]]:
    text = _read_zip_text(zf, "[Content_Types].xml")
    if not text:
        return [], {}
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return [], {}

    types: list[str] = []
    part_types: dict[str, str] = {}
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "Override":
            part = str(elem.attrib.get("PartName", "")).lstrip("/")
            ctype = str(elem.attrib.get("ContentType", ""))
            if ctype:
                types.append(ctype)
            if part:
                part_types[part] = ctype
        elif tag == "Default":
            ctype = str(elem.attrib.get("ContentType", ""))
            if ctype:
                types.append(ctype)
    return types, part_types


def _relationship_source(rels_name: str) -> str:
    if not rels_name.endswith(".rels"):
        return rels_name
    dirname = posixpath.dirname(rels_name)
    filename = posixpath.basename(rels_name)[:-5]
    if dirname.endswith("_rels"):
        base = posixpath.dirname(dirname)
        return posixpath.join(base, filename) if base else filename
    return rels_name


def _relationships(zf: zipfile.ZipFile) -> list[dict]:
    out: list[dict] = []
    rel_names = [
        name
        for name in zf.namelist()
        if name.lower().endswith(".rels") and "_rels/" in name.lower()
    ]
    for rel_name in sorted(rel_names)[:_MAX_RELATIONSHIPS]:
        text = _read_zip_text(zf, rel_name)
        if not text:
            continue
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            continue
        source = _relationship_source(rel_name)
        for elem in root.iter():
            if elem.tag.rsplit("}", 1)[-1] != "Relationship":
                continue
            target = str(elem.attrib.get("Target", ""))
            rel_type = str(elem.attrib.get("Type", ""))
            mode = str(elem.attrib.get("TargetMode", ""))
            if not target:
                continue
            out.append(
                {
                    "source": source,
                    "target": target,
                    "relationship_type": rel_type,
                    "target_mode": mode,
                }
            )
    return out


def _part_tag(name: str, part_type: str) -> str:
    lower_name = name.lower()
    lower_type = part_type.lower()
    if name == "[Content_Types].xml":
        return "content_types"
    if lower_name.endswith(".rels"):
        return "relationship"
    if "vbaproject.bin" in lower_name:
        return "vba_project"
    if lower_name.startswith("word/embeddings/"):
        return "embedded_object"
    if lower_name.startswith("word/activex/"):
        return "activex"
    if lower_name.startswith("word/"):
        return "word_part"
    if "macroenabled" in lower_type:
        return "macro_enabled_part"
    return "part"


def _run(sample_path: str) -> dict:
    path = Path(sample_path)
    if not path.exists():
        return _empty_result(f"sample not found: {sample_path}")

    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            lower_names = {name.lower() for name in names}
            content_type_values, part_types = _content_types(zf)
            rels = _relationships(zf)
    except zipfile.BadZipFile as exc:
        return _empty_result(f"OOXML ZIP parse failed: {exc}")
    except Exception as exc:  # noqa: BLE001
        return _empty_result(f"OOXML structure parse failed: {exc}")

    lower_types = [ctype.lower() for ctype in content_type_values]
    macro_enabled_declared = any("macroenabled" in ctype for ctype in lower_types)
    has_vba_project = any(name.endswith("vbaproject.bin") for name in lower_names)

    parts = []
    for name in sorted(names)[:_MAX_PARTS]:
        part_type = part_types.get(name, "")
        parts.append(
            {
                "name": name,
                "tag": _part_tag(name, part_type),
                "content_type": part_type,
            }
        )

    remote_templates = []
    for rel in rels:
        rel_type = str(rel.get("relationship_type", "")).lower()
        target = str(rel.get("target", ""))
        mode = str(rel.get("target_mode", ""))
        if mode.lower() == "external" or target.lower().startswith(("http://", "https://")):
            remote_templates.append({**rel, "tag": "external_relationship"})
        elif "attachedtemplate" in rel_type:
            remote_templates.append({**rel, "tag": "attached_template"})

    embedded_objects = [
        {
            "name": name,
            "container_path": name,
            "suggested_format": "ole_object",
            "source": "ooxml_structure",
        }
        for name in sorted(names)
        if name.lower().startswith("word/embeddings/")
    ]

    warnings: list[str] = []
    if macro_enabled_declared and not has_vba_project:
        warnings.append(
            "macro-enabled OOXML declares VBA content type but vbaProject.bin is missing"
        )

    return {
        "document_metadata": {
            "container": "ooxml",
            "macro_enabled_declared": macro_enabled_declared,
            "has_vba_project": has_vba_project,
            "content_type_count": len(content_type_values),
            "part_count": len(names),
        },
        "ooxml_parts": parts,
        "remote_templates": remote_templates,
        "embedded_objects": embedded_objects,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OOXML structure fallback worker")
    parser.add_argument("--input", required=True, help="Path to JSON input file")
    args = parser.parse_args()

    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps(_empty_result(f"bad input: {exc}")))
        raise SystemExit(1) from exc

    result = _run(sample_path=payload.get("sample_path", ""))
    print(json.dumps(result))
    if "error" in result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
