"""A small PDF reader: what is drawn on each page, as positioned glyphs, lines and filled shapes.

Only what a score needs is read. A PDF that a notation program wrote is not a picture: every
notehead, clef, rest and accidental is a character of a music font placed at an exact point, every
staff line, stem and barline is a drawn line, every beam and tie a filled shape, and every word of
the lyrics is text. This module turns the page description into those three lists, in page
coordinates (points, origin at the bottom left, y upwards). It understands the parts of the format
such files use: the object syntax, compressed streams (Flate, with the PNG predictors of
cross-reference streams; ASCIIHex; ASCII85), object streams, the page tree with inherited
resources, form XObjects, simple and composite fonts with their ``ToUnicode`` maps and widths, and
the path and text operators of content streams. Images are skipped; an encrypted file is refused.

It is deliberately written without a third-party library so that BLT has no new dependency.
"""

import contextlib
import itertools
import re
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from barbershop_tracks.core.pdfscore.glyph_names import glyph_name_to_text


class PdfError(Exception):
    """The file is not a PDF this reader can read (damaged, encrypted, or of an unknown form)."""


# --- objects ------------------------------------------------------------------------------------


class Name(str):
    """A PDF name (``/Type``), kept apart from strings."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class Ref:
    num: int
    gen: int


@dataclass(slots=True)
class Stream:
    attrs: dict[str, Any]
    raw: bytes


_WS = b" \t\r\n\x0c\x00"
_DELIM = b"()<>[]{}/%"
_TOKEN_END = re.compile(rb"[\s()<>\[\]{}/%]")


class Lexer:
    """Reads PDF objects from bytes. ``resolve`` is applied by the document, not here."""

    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def skip_ws(self) -> None:
        data, n = self.data, len(self.data)
        while self.pos < n:
            c = data[self.pos]
            if c in _WS:
                self.pos += 1
            elif c == 0x25:  # % comment
                end = data.find(b"\n", self.pos)
                end2 = data.find(b"\r", self.pos)
                ends = [e for e in (end, end2) if e >= 0]
                self.pos = min(ends) if ends else n
            else:
                break

    def at_end(self) -> bool:
        self.skip_ws()
        return self.pos >= len(self.data)

    def token(self) -> bytes:
        """The next bare token (a number, keyword or operator) without consuming objects."""
        self.skip_ws()
        m = _TOKEN_END.search(self.data, self.pos)
        end = m.start() if m else len(self.data)
        if end == self.pos:
            end += 1
        tok = self.data[self.pos : end]
        self.pos = end
        return tok

    def read(self) -> Any:
        self.skip_ws()
        data = self.data
        if self.pos >= len(data):
            raise PdfError("unexpected end of data")
        c = data[self.pos]
        if c == 0x2F:  # /
            self.pos += 1
            m = _TOKEN_END.search(data, self.pos)
            end = m.start() if m else len(data)
            raw = data[self.pos : end]
            self.pos = end
            return Name(_unescape_name(raw))
        if c == 0x28:  # (
            return self._literal_string()
        if c == 0x3C:  # <
            if data[self.pos + 1 : self.pos + 2] == b"<":
                self.pos += 2
                result: dict[str, Any] = {}
                while True:
                    self.skip_ws()
                    if data[self.pos : self.pos + 2] == b">>":
                        self.pos += 2
                        break
                    key = self.read()
                    if not isinstance(key, Name):
                        raise PdfError("dictionary key is not a name")
                    result[str(key)] = self.read()
                if self._peek_keyword(b"stream"):
                    return self._stream(result)
                return result
            end = data.find(b">", self.pos)
            hexed = re.sub(rb"\s", b"", data[self.pos + 1 : end])
            self.pos = end + 1
            if len(hexed) % 2:
                hexed += b"0"
            return bytes.fromhex(hexed.decode("ascii"))
        if c == 0x5B:  # [
            self.pos += 1
            items: list[Any] = []
            while True:
                self.skip_ws()
                if data[self.pos] == 0x5D:
                    self.pos += 1
                    return items
                items.append(self.read())
        tok = self.token()
        if tok in (b"true", b"false"):
            return tok == b"true"
        if tok == b"null":
            return None
        number = _number(tok)
        if number is None:
            return Operator(tok.decode("latin-1"))
        if isinstance(number, int) and number >= 0:
            save = self.pos
            second = self.token()
            if second.isdigit():
                third = self.token()
                if third == b"R":
                    return Ref(number, int(second))
            self.pos = save
        return number

    def _peek_keyword(self, word: bytes) -> bool:
        save = self.pos
        self.skip_ws()
        if self.data.startswith(word, self.pos):
            return True
        self.pos = save
        return False

    def _stream(self, attrs: dict[str, Any]) -> Stream:
        self.pos += len(b"stream")
        if self.data[self.pos : self.pos + 2] == b"\r\n":
            self.pos += 2
        elif self.data[self.pos : self.pos + 1] in (b"\n", b"\r"):
            self.pos += 1
        length = attrs.get("Length")
        if isinstance(length, int) and self.data[
            self.pos + length : self.pos + length + 20
        ].lstrip().startswith(b"endstream"):
            raw = self.data[self.pos : self.pos + length]
            self.pos += length
        else:  # an indirect or wrong /Length: find the end
            end = self.data.find(b"endstream", self.pos)
            if end < 0:
                raise PdfError("stream without endstream")
            raw = self.data[self.pos : end].rstrip(b"\r\n")
            self.pos = end
        self.pos = self.data.find(b"endstream", self.pos) + len(b"endstream")
        return Stream(attrs, raw)

    def _literal_string(self) -> bytes:
        data = self.data
        self.pos += 1
        out = bytearray()
        depth = 1
        while self.pos < len(data):
            c = data[self.pos]
            self.pos += 1
            if c == 0x5C:  # backslash
                e = data[self.pos]
                self.pos += 1
                simple = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}
                if e in simple:
                    out.append(simple[e])
                elif 0x30 <= e <= 0x37:
                    digits = bytes([e])
                    while len(digits) < 3 and 0x30 <= data[self.pos] <= 0x37:
                        digits += bytes([data[self.pos]])
                        self.pos += 1
                    out.append(int(digits, 8) & 0xFF)
                elif e == 0x0D:
                    if data[self.pos] == 0x0A:
                        self.pos += 1
                elif e == 0x0A:
                    pass
                else:
                    out.append(e)
            elif c == 0x28:
                depth += 1
                out.append(c)
            elif c == 0x29:
                depth -= 1
                if depth == 0:
                    break
                out.append(c)
            else:
                out.append(c)
        return bytes(out)


class Operator(str):
    """A content-stream operator (``Tj``, ``re``)."""

    __slots__ = ()


def _number(tok: bytes) -> int | float | None:
    try:
        if b"." in tok:
            return float(tok)
        return int(tok)
    except ValueError:
        return None


def _unescape_name(raw: bytes) -> str:
    if b"#" in raw:
        raw = re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), raw)
    return raw.decode("latin-1")


# --- filters ------------------------------------------------------------------------------------


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _unpredict(data: bytes, params: dict[str, Any]) -> bytes:
    predictor = params.get("Predictor", 1)
    if not isinstance(predictor, int) or predictor < 10:
        return data
    columns = int(params.get("Columns", 1))
    colors = int(params.get("Colors", 1))
    bpc = int(params.get("BitsPerComponent", 8))
    bpp = max(1, colors * bpc // 8)
    row_len = (columns * colors * bpc + 7) // 8
    out = bytearray()
    prev = bytearray(row_len)
    for start in range(0, len(data), row_len + 1):
        kind = data[start]
        row = bytearray(data[start + 1 : start + 1 + row_len])
        row.extend(b"\0" * (row_len - len(row)))
        for i in range(row_len):
            left = row[i - bpp] if i >= bpp else 0
            up = prev[i]
            corner = prev[i - bpp] if i >= bpp else 0
            if kind == 1:
                row[i] = (row[i] + left) & 0xFF
            elif kind == 2:
                row[i] = (row[i] + up) & 0xFF
            elif kind == 3:
                row[i] = (row[i] + (left + up) // 2) & 0xFF
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                pred = left if pa <= pb and pa <= pc else (up if pb <= pc else corner)
                row[i] = (row[i] + pred) & 0xFF
        out.extend(row)
        prev = row
    return bytes(out)


def _ascii85(data: bytes) -> bytes:
    data = re.sub(rb"\s", b"", data)
    if data.startswith(b"<~"):
        data = data[2:]
    end = data.find(b"~>")
    if end >= 0:
        data = data[:end]
    out = bytearray()
    group: list[int] = []
    for c in data:
        if c == 0x7A and not group:
            out.extend(b"\0\0\0\0")
            continue
        group.append(c - 33)
        if len(group) == 5:
            value = 0
            for g in group:
                value = value * 85 + g
            out.extend(value.to_bytes(4, "big"))
            group = []
    if group:
        n = len(group)
        group.extend([84] * (5 - n))
        value = 0
        for g in group:
            value = value * 85 + g
        out.extend(value.to_bytes(4, "big")[: n - 1])
    return bytes(out)


def _lzw(data: bytes, early: int = 1) -> bytes:
    out = bytearray()
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    width, buffer, bits = 9, 0, 0
    prev: bytes | None = None
    for byte in data:
        buffer = (buffer << 8) | byte
        bits += 8
        while bits >= width:
            bits -= width
            code = (buffer >> bits) & ((1 << width) - 1)
            if code == 256:
                table = table[:258]
                width, prev = 9, None
                continue
            if code == 257:
                return bytes(out)
            if code < len(table):
                entry = table[code]
                if prev is not None:
                    table.append(prev + entry[:1])
            elif prev is not None:
                entry = prev + prev[:1]
                table.append(entry)
            else:
                raise PdfError("bad LZW data")
            out.extend(entry)
            prev = entry
            if len(table) + early >= (1 << width) and width < 12:
                width += 1
    return bytes(out)


def decode_stream(stream: Stream, doc: "Document | None" = None) -> bytes:
    def get(value: Any) -> Any:
        return doc.resolve(value) if doc is not None else value

    filters = [str(f) for f in _as_list(get(stream.attrs.get("Filter")))]
    params = [get(p) or {} for p in _as_list(get(stream.attrs.get("DecodeParms")))]
    data = stream.raw
    for i, name in enumerate(filters):
        p = params[i] if i < len(params) and isinstance(params[i], dict) else {}
        if name in ("FlateDecode", "Fl"):
            try:
                data = zlib.decompress(data)
            except zlib.error:
                data = zlib.decompressobj().decompress(data)
            data = _unpredict(data, p)
        elif name in ("ASCIIHexDecode", "AHx"):
            text = re.sub(rb"\s", b"", data).rstrip(b">")
            if len(text) % 2:
                text += b"0"
            data = bytes.fromhex(text.decode("ascii"))
        elif name in ("ASCII85Decode", "A85"):
            data = _ascii85(data)
        elif name in ("LZWDecode", "LZW"):
            data = _unpredict(_lzw(data, int(p.get("EarlyChange", 1))), p)
        else:
            raise PdfError(f"unsupported filter {name}")
    return data


# --- the document -------------------------------------------------------------------------------

_OBJ = re.compile(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b")


class Document:
    """All objects of a PDF file, found by scanning (robust to a damaged cross-reference table)."""

    def __init__(self, data: bytes) -> None:
        if not data.lstrip()[:5] == b"%PDF-":
            raise PdfError("not a PDF file")
        self.data = data
        self.objects: dict[int, Any] = {}
        self._offsets: dict[int, int] = {}
        for m in _OBJ.finditer(data):
            self._offsets[int(m.group(1))] = m.end()  # a later definition replaces an earlier one
        self._loaded_objstm = False
        self.trailer = self._find_trailer()
        if "Encrypt" in self.trailer:
            raise PdfError("the PDF is encrypted")

    def _find_trailer(self) -> dict[str, Any]:
        trailer: dict[str, Any] = {}
        for m in re.finditer(rb"trailer\s*<<", self.data):
            lex = Lexer(self.data, m.end() - 2)
            try:
                found = lex.read()
            except (PdfError, IndexError):
                continue
            if isinstance(found, dict):
                trailer.update(found)
        if "Root" not in trailer:  # a cross-reference stream carries the trailer keys
            for num in self._offsets:
                obj = self.get(num)
                if isinstance(obj, Stream) and obj.attrs.get("Type") == "XRef":
                    trailer.update(obj.attrs)
        if "Root" not in trailer:
            for num in list(self._offsets):
                obj = self.get(num)
                if isinstance(obj, dict) and obj.get("Type") == "Catalog":
                    trailer["Root"] = Ref(num, 0)
                    break
        if "Root" not in trailer:
            self._load_object_streams()
            for num, obj in self.objects.items():
                if isinstance(obj, dict) and obj.get("Type") == "Catalog":
                    trailer["Root"] = Ref(num, 0)
                    break
        if "Root" not in trailer:
            raise PdfError("the PDF has no document catalog")
        return trailer

    def get(self, num: int) -> Any:
        if num in self.objects:
            return self.objects[num]
        offset = self._offsets.get(num)
        if offset is None:
            if not self._loaded_objstm:
                self._load_object_streams()
                return self.objects.get(num)
            return None
        lex = Lexer(self.data, offset)
        try:
            obj = lex.read()
        except (PdfError, IndexError, ValueError):
            obj = None
        self.objects[num] = obj
        return obj

    def _load_object_streams(self) -> None:
        self._loaded_objstm = True
        for num in list(self._offsets):
            obj = self.get(num)
            if not (isinstance(obj, Stream) and obj.attrs.get("Type") == "ObjStm"):
                continue
            try:
                data = decode_stream(obj, self)
            except (PdfError, zlib.error, ValueError):
                continue
            n = int(self.resolve(obj.attrs.get("N", 0)))
            first = int(self.resolve(obj.attrs.get("First", 0)))
            header = Lexer(data)
            pairs = [(header.read(), header.read()) for _ in range(n)]
            for obj_num, rel in pairs:
                if int(obj_num) in self._offsets:
                    continue  # an object written directly in the file is the newer one
                lex = Lexer(data, first + int(rel))
                try:
                    self.objects[int(obj_num)] = lex.read()
                except (PdfError, IndexError, ValueError):
                    continue

    def resolve(self, value: Any) -> Any:
        seen = 0
        while isinstance(value, Ref) and seen < 32:
            value = self.get(value.num)
            seen += 1
        return value

    def pages(self) -> list[dict[str, Any]]:
        root = self.resolve(self.trailer["Root"])
        found: list[dict[str, Any]] = []

        def walk(node: Any, inherited: dict[str, Any], depth: int) -> None:
            node = self.resolve(node)
            if not isinstance(node, dict) or depth > 64:
                return
            here = dict(inherited)
            for key in ("Resources", "MediaBox", "CropBox", "Rotate"):
                if key in node:
                    here[key] = node[key]
            if node.get("Type") == "Pages" or "Kids" in node:
                for kid in self.resolve(node.get("Kids")) or []:
                    walk(kid, here, depth + 1)
            else:
                page = dict(node)
                page.update({k: v for k, v in here.items() if k not in node})
                found.append(page)

        walk(root.get("Pages"), {}, 0)
        return found


# --- fonts --------------------------------------------------------------------------------------


@dataclass(slots=True)
class Font:
    name: str  # the base font, subset prefix removed ("Leland")
    two_byte: bool
    to_text: dict[int, str]
    widths: dict[int, float]  # in text space units (1/1000 em)
    default_width: float

    def codes(self, raw: bytes) -> Iterator[int]:
        if self.two_byte:
            for i in range(0, len(raw) - 1, 2):
                yield (raw[i] << 8) | raw[i + 1]
        else:
            yield from raw

    def text(self, code: int) -> str:
        found = self.to_text.get(code)
        if found is not None:
            return found
        return "" if self.two_byte else chr(code)

    def width(self, code: int) -> float:
        return self.widths.get(code, self.default_width)


def _parse_cmap(data: bytes) -> dict[int, str]:
    result: dict[int, str] = {}

    def text_of(raw: bytes) -> str:
        try:
            return raw.decode("utf-16-be")
        except UnicodeDecodeError:
            return raw.decode("latin-1")

    lex = Lexer(data)
    stack: list[Any] = []
    while not lex.at_end():
        try:
            item = lex.read()
        except (PdfError, IndexError, ValueError):
            break
        if isinstance(item, Operator):
            if item == "endbfchar":
                for i in range(0, len(stack) - 1, 2):
                    src, dst = stack[i], stack[i + 1]
                    if isinstance(src, bytes) and isinstance(dst, bytes):
                        result[int.from_bytes(src, "big")] = text_of(dst)
            elif item == "endbfrange":
                for i in range(0, len(stack) - 2, 3):
                    lo, hi, dst = stack[i], stack[i + 1], stack[i + 2]
                    if not (isinstance(lo, bytes) and isinstance(hi, bytes)):
                        continue
                    a, b = int.from_bytes(lo, "big"), int.from_bytes(hi, "big")
                    if isinstance(dst, list):
                        for k, d in enumerate(dst[: b - a + 1]):
                            if isinstance(d, bytes):
                                result[a + k] = text_of(d)
                    elif isinstance(dst, bytes) and b - a < 65536:
                        base = text_of(dst)
                        if base:
                            for k in range(b - a + 1):
                                result[a + k] = base[:-1] + chr(ord(base[-1]) + k)
            stack = []
        else:
            stack.append(item)
    return result


_STANDARD_BYTES = {i: chr(i) for i in range(32, 127)}


def load_font(doc: Document, obj: Any) -> Font:
    font = doc.resolve(obj) or {}
    base = str(doc.resolve(font.get("BaseFont", "")) or "")
    base = base.split("+", 1)[1] if re.match(r"^[A-Z]{6}\+", base) else base
    subtype = font.get("Subtype")
    to_text: dict[int, str] = {}
    widths: dict[int, float] = {}
    default_width = 500.0
    two_byte = subtype == "Type0"
    if two_byte:
        descendants = doc.resolve(font.get("DescendantFonts")) or []
        cid = doc.resolve(descendants[0]) if descendants else {}
        default_width = float(doc.resolve(cid.get("DW", 1000)))
        w = doc.resolve(cid.get("W")) or []
        i = 0
        while i < len(w):
            first = doc.resolve(w[i])
            nxt = doc.resolve(w[i + 1]) if i + 1 < len(w) else None
            if isinstance(nxt, list):
                for k, value in enumerate(nxt):
                    widths[int(first) + k] = float(doc.resolve(value))
                i += 2
            else:
                last, value = nxt, doc.resolve(w[i + 2]) if i + 2 < len(w) else 0
                for code in range(int(first), int(last or first) + 1):
                    widths[code] = float(value)
                i += 3
    else:
        first = int(doc.resolve(font.get("FirstChar", 0)) or 0)
        for k, value in enumerate(doc.resolve(font.get("Widths")) or []):
            widths[first + k] = float(doc.resolve(value))
        default_width = 0.0 if widths else 500.0
        to_text.update(_STANDARD_BYTES)
        encoding = doc.resolve(font.get("Encoding"))
        if isinstance(encoding, dict):
            code = 0
            for item in doc.resolve(encoding.get("Differences")) or []:
                item = doc.resolve(item)
                if isinstance(item, int):
                    code = item
                elif isinstance(item, Name):
                    text = glyph_name_to_text(str(item))
                    if text:
                        to_text[code] = text
                    code += 1
    to_unicode = doc.resolve(font.get("ToUnicode"))
    if isinstance(to_unicode, Stream):
        with contextlib.suppress(PdfError, zlib.error, ValueError):
            to_text.update(_parse_cmap(decode_stream(to_unicode, doc)))
    return Font(base, two_byte, to_text, widths, default_width)


# --- page content -------------------------------------------------------------------------------

Matrix = tuple[float, float, float, float, float, float]
_IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mul(a: Matrix, b: Matrix) -> Matrix:
    """``a`` then ``b`` (row vectors, as in PDF)."""
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    )


def _apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    return (x * m[0] + y * m[2] + m[4], x * m[1] + y * m[3] + m[5])


@dataclass(frozen=True, slots=True)
class Glyph:
    text: str
    font: str
    x: float  # the glyph's origin on the page
    y: float
    size: float  # the font size in page units (vertical scale)
    width: float  # the advance width in page units
    # the text-showing operation that drew it: a notation program writes each syllable, word or
    # mark as a text of its own, so glyphs of one run belong together
    run: int = 0


@dataclass(frozen=True, slots=True)
class Segment:
    """A straight stroked line."""

    x0: float
    y0: float
    x1: float
    y1: float
    width: float


@dataclass(frozen=True, slots=True)
class Shape:
    """A filled area (or a stroked curve): its outline, flattened to points."""

    points: tuple[tuple[float, float], ...]
    filled: bool
    curved: bool  # the outline has Bézier pieces (a tie or a slur) rather than only straight sides
    width: float  # the line width, for a stroked curve

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass(slots=True)
class Page:
    number: int
    width: float
    height: float
    glyphs: list[Glyph] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)


@dataclass(slots=True)
class _State:
    ctm: Matrix = _IDENTITY
    line_width: float = 1.0
    font: Font | None = None
    size: float = 1.0
    char_space: float = 0.0
    word_space: float = 0.0
    hscale: float = 1.0
    leading: float = 0.0
    rise: float = 0.0

    def copy(self) -> "_State":
        return _State(
            self.ctm,
            self.line_width,
            self.font,
            self.size,
            self.char_space,
            self.word_space,
            self.hscale,
            self.leading,
            self.rise,
        )


def _bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 8,
) -> list[tuple[float, float]]:
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append(
            (
                u * u * u * p0[0]
                + 3 * u * u * t * p1[0]
                + 3 * u * t * t * p2[0]
                + t * t * t * p3[0],
                u * u * u * p0[1]
                + 3 * u * u * t * p1[1]
                + 3 * u * t * t * p2[1]
                + t * t * t * p3[1],
            )
        )
    return out


class _Interpreter:
    def __init__(self, doc: Document, page: Page) -> None:
        self.doc = doc
        self.page = page
        self.fonts: dict[int, Font] = {}
        self.depth = 0
        self.runs = 0

    def font(self, resources: dict[str, Any], name: str) -> Font | None:
        fonts = self.doc.resolve(resources.get("Font")) or {}
        ref = fonts.get(name)
        if ref is None:
            return None
        key = ref.num if isinstance(ref, Ref) else id(ref)
        if key not in self.fonts:
            self.fonts[key] = load_font(self.doc, ref)
        return self.fonts[key]

    def run(self, content: bytes, resources: dict[str, Any], state: _State) -> None:
        self.depth += 1
        if self.depth > 16:
            return
        lex = Lexer(content)
        operands: list[Any] = []
        stack: list[_State] = []
        subpaths: list[list[tuple[float, float]]] = []
        curved = False
        current: list[tuple[float, float]] = []
        tm: Matrix = _IDENTITY
        tlm: Matrix = _IDENTITY

        def point(x: Any, y: Any) -> tuple[float, float]:
            return _apply(state.ctm, float(x), float(y))

        def flush(filled: bool, stroked: bool) -> None:
            nonlocal subpaths, current, curved
            if current:
                subpaths.append(current)
            scale = (abs(state.ctm[0] * state.ctm[3] - state.ctm[1] * state.ctm[2])) ** 0.5
            width = state.line_width * scale
            for sub in subpaths:
                if len(sub) < 2:
                    continue
                if filled:
                    self.page.shapes.append(Shape(tuple(sub), True, curved, width))
                elif stroked:
                    if not curved:
                        for a, b in itertools.pairwise(sub):
                            self.page.segments.append(Segment(a[0], a[1], b[0], b[1], width))
                    else:
                        self.page.shapes.append(Shape(tuple(sub), False, True, width))
            subpaths, current, curved = [], [], False

        def show(raw: bytes) -> None:
            nonlocal tm
            font = state.font
            if font is None:
                return
            for code in font.codes(raw):
                trm = _mul(
                    (state.size * state.hscale, 0.0, 0.0, state.size, 0.0, state.rise),
                    _mul(tm, state.ctm),
                )
                w0 = font.width(code) / 1000.0
                text = font.text(code)
                size = (trm[2] ** 2 + trm[3] ** 2) ** 0.5
                adv = (w0 * state.size + state.char_space) * state.hscale
                if code == 32 and not font.two_byte:
                    adv += state.word_space * state.hscale
                adv_page = (
                    adv
                    * (tm[0] ** 2 + tm[1] ** 2) ** 0.5
                    * ((state.ctm[0] ** 2 + state.ctm[1] ** 2) ** 0.5)
                )
                if text and not text.isspace():
                    self.page.glyphs.append(
                        Glyph(text, font.name, trm[4], trm[5], size, adv_page, self.runs)
                    )
                tm = _mul((1.0, 0.0, 0.0, 1.0, adv, 0.0), tm)

        while True:
            try:
                if lex.at_end():
                    break
                item = lex.read()
            except (PdfError, IndexError, ValueError):
                break
            if not isinstance(item, Operator):
                operands.append(item)
                continue
            op = str(item)
            o = operands
            operands = []
            try:
                if op == "q":
                    stack.append(state.copy())
                elif op == "Q":
                    if stack:
                        state = stack.pop()
                elif op == "cm" and len(o) == 6:
                    state.ctm = _mul(tuple(float(v) for v in o), state.ctm)  # type: ignore[arg-type]
                elif op == "w" and o:
                    state.line_width = float(o[0])
                elif op == "m" and len(o) == 2:
                    if current:
                        subpaths.append(current)
                    current = [point(o[0], o[1])]
                elif op == "l" and len(o) == 2:
                    current.append(point(o[0], o[1]))
                elif op in ("c", "v", "y") and current:
                    nums = [float(v) for v in o]
                    p0 = current[-1]
                    if op == "c" and len(nums) == 6:
                        p1, p2, p3 = point(*nums[0:2]), point(*nums[2:4]), point(*nums[4:6])
                    elif op == "v" and len(nums) == 4:
                        p1, p2, p3 = p0, point(*nums[0:2]), point(*nums[2:4])
                    elif op == "y" and len(nums) == 4:
                        p1, p2, p3 = point(*nums[0:2]), point(*nums[2:4]), point(*nums[2:4])
                    else:
                        continue
                    current.extend(_bezier(p0, p1, p2, p3))
                    curved = True
                elif op == "h":
                    if current:
                        current.append(current[0])
                elif op == "re" and len(o) == 4:
                    if current:
                        subpaths.append(current)
                    x, y, w, h = (float(v) for v in o)
                    current = [point(x, y), point(x + w, y), point(x + w, y + h), point(x, y + h)]
                    current.append(current[0])
                elif op in ("S", "s"):
                    flush(False, True)
                elif op in ("f", "F", "f*", "B", "B*", "b", "b*"):
                    flush(True, False)
                elif op == "n":
                    subpaths, current, curved = [], [], False
                elif op == "BT":
                    tm = tlm = _IDENTITY
                    self.runs += 1
                elif op == "Tf" and len(o) == 2:
                    state.font = self.font(resources, str(o[0]))
                    state.size = float(o[1])
                elif op == "Tc" and o:
                    state.char_space = float(o[0])
                elif op == "Tw" and o:
                    state.word_space = float(o[0])
                elif op == "Tz" and o:
                    state.hscale = float(o[0]) / 100.0
                elif op == "TL" and o:
                    state.leading = float(o[0])
                elif op == "Ts" and o:
                    state.rise = float(o[0])
                elif op in ("Td", "TD") and len(o) == 2:
                    if op == "TD":
                        state.leading = -float(o[1])
                    tlm = _mul((1.0, 0.0, 0.0, 1.0, float(o[0]), float(o[1])), tlm)
                    tm = tlm
                elif op == "Tm" and len(o) == 6:
                    tlm = tm = tuple(float(v) for v in o)  # type: ignore[assignment]
                elif op == "T*":
                    tlm = _mul((1.0, 0.0, 0.0, 1.0, 0.0, -state.leading), tlm)
                    tm = tlm
                if op == "Tj" and o and isinstance(o[0], bytes):
                    show(o[0])
                elif op in ("'", '"') and o and isinstance(o[-1], bytes):
                    if op == '"' and len(o) == 3:
                        state.word_space, state.char_space = float(o[0]), float(o[1])
                    tlm = _mul((1.0, 0.0, 0.0, 1.0, 0.0, -state.leading), tlm)
                    tm = tlm
                    show(o[-1])
                elif op == "TJ" and o and isinstance(o[0], list):
                    for part in o[0]:
                        if isinstance(part, bytes):
                            show(part)
                        elif isinstance(part, (int, float)):
                            shift = -float(part) / 1000.0 * state.size * state.hscale
                            tm = _mul((1.0, 0.0, 0.0, 1.0, shift, 0.0), tm)
                elif op == "Do" and o:
                    self._xobject(resources, str(o[0]), state)
                elif op == "BI":
                    end = re.compile(rb"\sEI(?=[\s]|$)").search(lex.data, lex.pos)
                    lex.pos = end.end() if end else len(lex.data)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
        self.depth -= 1

    def _xobject(self, resources: dict[str, Any], name: str, state: _State) -> None:
        xobjects = self.doc.resolve(resources.get("XObject")) or {}
        obj = self.doc.resolve(xobjects.get(name))
        if not isinstance(obj, Stream) or obj.attrs.get("Subtype") != "Form":
            return
        inner = state.copy()
        matrix = self.doc.resolve(obj.attrs.get("Matrix"))
        if isinstance(matrix, list) and len(matrix) == 6:
            inner.ctm = _mul(tuple(float(v) for v in matrix), inner.ctm)  # type: ignore[arg-type]
        own = self.doc.resolve(obj.attrs.get("Resources")) or resources
        try:
            self.run(decode_stream(obj, self.doc), own, inner)
        except (PdfError, zlib.error):
            return


def read_pages(path: Path, *, max_pages: int = 200) -> list[Page]:
    """Everything drawn on each page of the PDF at ``path``. Raises :class:`PdfError`."""
    try:
        data = path.read_bytes()
    except OSError as error:
        raise PdfError(f"cannot read {path.name}: {error}") from error
    doc = Document(data)
    pages: list[Page] = []
    for number, page in enumerate(doc.pages()[:max_pages], start=1):
        box = doc.resolve(page.get("CropBox") or page.get("MediaBox")) or [0, 0, 612, 792]
        x0, y0, x1, y1 = (float(doc.resolve(v)) for v in box)
        rotate = int(doc.resolve(page.get("Rotate", 0)) or 0) % 360
        result = Page(number, x1 - x0, y1 - y0)
        resources = doc.resolve(page.get("Resources")) or {}
        contents = doc.resolve(page.get("Contents"))
        streams = [doc.resolve(c) for c in contents] if isinstance(contents, list) else [contents]
        content = b"\n".join(decode_stream(s, doc) for s in streams if isinstance(s, Stream))
        state = _State()
        state.ctm = (1.0, 0.0, 0.0, 1.0, -x0, -y0)
        if rotate:
            raise PdfError("rotated pages are not supported")
        _Interpreter(doc, result).run(content, resources, state)
        pages.append(result)
    # a music font older than SMuFL (Finale's Maestro and its kind) is read as its SMuFL characters
    from barbershop_tracks.core.pdfscore.legacy_fonts import translate_legacy_music_fonts

    translate_legacy_music_fonts(pages)
    return pages


__all__ = ["Glyph", "Page", "PdfError", "Segment", "Shape", "read_pages"]
