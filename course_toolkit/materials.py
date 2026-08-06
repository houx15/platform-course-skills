import hashlib
import re
import zipfile
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Sequence, Tuple
from xml.etree import ElementTree


@dataclass(frozen=True)
class MaterialItem:
    source_id: str
    source_file: str
    location: str
    kind: str
    text: str

    def as_dict(self) -> dict:
        return {
            "sourceId": self.source_id,
            "sourceFile": self.source_file,
            "location": self.location,
            "kind": self.kind,
            "text": self.text,
        }


@dataclass(frozen=True)
class ExtractionResult:
    items: Tuple[MaterialItem, ...]
    ignored: Tuple[Path, ...]
    unsupported: Tuple[Path, ...]
    errors: Tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "items": [item.as_dict() for item in self.items],
            "ignored": [str(path) for path in self.ignored],
            "unsupported": [str(path) for path in self.unsupported],
            "errors": list(self.errors),
        }


def _source_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def _make_item(
    path: Path,
    location: str,
    kind: str,
    text: str,
) -> MaterialItem:
    normalized = " ".join(text.split())
    source_file = _source_label(path)
    digest_input = "\n".join((source_file, location, kind, normalized))
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]
    return MaterialItem(
        source_id=f"source-{digest}",
        source_file=source_file,
        location=location,
        kind=kind,
        text=normalized,
    )


def _markdown_items(path: Path) -> List[MaterialItem]:
    lines = path.read_text(encoding="utf-8").splitlines()
    items: List[MaterialItem] = []
    paragraph: List[str] = []
    paragraph_start = 0

    def flush() -> None:
        nonlocal paragraph, paragraph_start
        if paragraph:
            items.append(
                _make_item(
                    path,
                    f"line:{paragraph_start}",
                    "paragraph",
                    " ".join(paragraph),
                )
            )
            paragraph = []

    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            flush()
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        list_item = re.match(r"^(?:[-*+]|\d+[.)])\s+(.+)$", line)
        if heading:
            flush()
            items.append(
                _make_item(path, f"line:{line_number}", "heading", heading.group(2))
            )
        elif list_item:
            flush()
            items.append(
                _make_item(
                    path,
                    f"line:{line_number}",
                    "list-item",
                    list_item.group(1),
                )
            )
        else:
            if not paragraph:
                paragraph_start = line_number
            paragraph.append(line)
    flush()
    return items


class _MaterialHtmlParser(HTMLParser):
    CAPTURE = {
        "h1": "heading",
        "h2": "heading",
        "h3": "heading",
        "h4": "heading",
        "h5": "heading",
        "h6": "heading",
        "li": "list-item",
        "p": "paragraph",
        "td": "table-cell",
        "th": "table-cell",
    }

    def __init__(self, path: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.path = path
        self.items: List[MaterialItem] = []
        self._captures: List[Tuple[str, str, int, List[str]]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        kind = self.CAPTURE.get(tag)
        if kind:
            line, _ = self.getpos()
            self._captures.append((tag, kind, line, []))

    def handle_data(self, data: str) -> None:
        if self._captures:
            self._captures[-1][3].append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._captures:
            return
        start_tag, kind, line, parts = self._captures[-1]
        if start_tag != tag:
            return
        self._captures.pop()
        text = " ".join("".join(parts).split())
        if text:
            self.items.append(
                _make_item(self.path, f"line:{line}", kind, text)
            )


def _html_items(path: Path) -> List[MaterialItem]:
    parser = _MaterialHtmlParser(path)
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.items


def _docx_items(path: Path) -> List[MaterialItem]:
    namespace = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    }
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
        try:
            styles_xml = archive.read("word/styles.xml")
        except KeyError:
            styles_xml = None
    root = ElementTree.fromstring(xml)
    style_names = {}
    if styles_xml is not None:
        styles_root = ElementTree.fromstring(styles_xml)
        for style in styles_root.findall("w:style", namespace):
            style_id = style.get(f"{{{namespace['w']}}}styleId", "")
            name = style.find("w:name", namespace)
            if style_id and name is not None:
                style_names[style_id] = name.get(
                    f"{{{namespace['w']}}}val",
                    "",
                )

    def paragraph_text(paragraph: ElementTree.Element) -> str:
        return "".join(
            node.text or "" for node in paragraph.findall(".//w:t", namespace)
        ).strip()

    def paragraph_kind(paragraph: ElementTree.Element) -> str:
        style = paragraph.find("./w:pPr/w:pStyle", namespace)
        style_value = ""
        if style is not None:
            style_value = style.get(f"{{{namespace['w']}}}val", "")
        style_name = style_names.get(style_value, "")
        outline = paragraph.find("./w:pPr/w:outlineLvl", namespace)
        if (
            style_value.lower().startswith("heading")
            or style_name.lower().startswith("heading")
            or outline is not None
        ):
            return "heading"
        return "paragraph"

    body = root.find("w:body", namespace)
    if body is None:
        return []
    items: List[MaterialItem] = []
    paragraph_index = 0
    table_index = 0
    for child in body:
        local_name = child.tag.rsplit("}", 1)[-1]
        if local_name == "p":
            paragraph_index += 1
            text = paragraph_text(child)
            if text:
                items.append(
                    _make_item(
                        path,
                        f"paragraph:{paragraph_index}",
                        paragraph_kind(child),
                        text,
                    )
                )
            continue
        if local_name != "tbl":
            continue
        table_index += 1
        for row_index, row in enumerate(
            child.findall("./w:tr", namespace),
            start=1,
        ):
            for cell_index, cell in enumerate(
                row.findall("./w:tc", namespace),
                start=1,
            ):
                for cell_paragraph_index, paragraph in enumerate(
                    cell.findall("./w:p", namespace),
                    start=1,
                ):
                    text = paragraph_text(paragraph)
                    if text:
                        location = (
                            f"table:{table_index}/row:{row_index}/cell:{cell_index}"
                            f"/paragraph:{cell_paragraph_index}"
                        )
                        items.append(
                            _make_item(path, location, "table-cell", text)
                        )
    return items


def _text_items(path: Path) -> List[MaterialItem]:
    lines = path.read_text(encoding="utf-8").splitlines()
    items: List[MaterialItem] = []
    paragraph: List[str] = []
    start = 0
    for line_number, raw in enumerate(lines + [""], start=1):
        line = raw.strip()
        if line:
            if not paragraph:
                start = line_number
            paragraph.append(line)
        elif paragraph:
            items.append(
                _make_item(path, f"line:{start}", "paragraph", " ".join(paragraph))
            )
            paragraph = []
    return items


def _expand_paths(paths: Sequence[Path]) -> List[Path]:
    expanded: List[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(item for item in path.rglob("*") if item.is_file()))
        else:
            expanded.append(path)
    return expanded


def extract_paths(paths: Sequence[Path]) -> ExtractionResult:
    items: List[MaterialItem] = []
    ignored: List[Path] = []
    unsupported: List[Path] = []
    errors: List[str] = []
    extractors = {
        ".docx": _docx_items,
        ".htm": _html_items,
        ".html": _html_items,
        ".md": _markdown_items,
        ".txt": _text_items,
    }
    for path in _expand_paths(paths):
        suffix = path.suffix.lower()
        if suffix == ".zip":
            ignored.append(path)
            continue
        extractor = extractors.get(suffix)
        if extractor is None:
            unsupported.append(path)
            continue
        try:
            items.extend(extractor(path))
        except (OSError, UnicodeError, zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
            errors.append(f"{path}: {exc}")
    return ExtractionResult(
        items=tuple(items),
        ignored=tuple(ignored),
        unsupported=tuple(unsupported),
        errors=tuple(errors),
    )
