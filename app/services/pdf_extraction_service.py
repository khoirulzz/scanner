"""Read selectable text from the one-page landscape KK print template.

The PDF remains in memory. Raster images, including the DRAFT watermark, are
not part of the text input and no AI provider is used.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

import fitz
from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import ScannerError
from app.schemas.extraction import ExtractionBundle, HeaderExtraction, PrimaryExtraction, SecondaryExtraction
from app.services.row_mapper import merge_rows


# The numbered tokens printed below the headings are the per-document source
# of truth. Dukcapil's generator can autofit the columns and can move the
# second table down when heading (11) wraps onto a third line.
_PRIMARY_FIELDS = (
    'nama_lengkap', 'nik', 'jenis_kelamin', 'tempat_lahir',
    'tanggal_lahir', 'agama', 'pendidikan', 'jenis_pekerjaan',
    'golongan_darah',
)
_SECONDARY_FIELDS = (
    'status_perkawinan', 'tanggal_perkawinan', 'status_hubungan',
    'kewarganegaraan', 'no_paspor', 'no_kitas_kitap', 'nama_ayah',
    'nama_ibu',
)


@dataclass(frozen=True)
class PdfWord:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class NativePdfResult:
    bundle: ExtractionBundle
    thumbnail_mime: str
    thumbnail_data: bytes
    metadata: dict


@dataclass(frozen=True)
class TableLayout:
    anchor_y: float
    first_column_left: float
    columns: tuple[tuple[str, float, float], ...]


def _normalise_value(value: str) -> str | None:
    value = re.sub(r'\s+', ' ', value).strip(' \t:|-')
    return value or None


def _words(page: fitz.Page) -> list[PdfWord]:
    return [
        PdfWord(x0, y0, x1, y1, text.strip())
        for x0, y0, x1, y1, text, *_ in page.get_text('words', sort=True)
        if text.strip() and text.strip().upper() != 'DRAFT'
    ]


def _cell(words: list[PdfWord], width: float, left: float, right: float) -> str | None:
    selected = [word for word in words if left <= word.x_center / width < right]
    return _normalise_value(' '.join(word.text for word in sorted(selected, key=lambda word: word.x0)))


def _column_number(text: str) -> int | None:
    match = re.fullmatch(r'\(\s*(\d{1,2})\s*\)', text.strip())
    return int(match.group(1)) if match else None


def _numbered_anchor_line(words: list[PdfWord], expected: range) -> list[PdfWord]:
    expected_numbers = set(expected)
    candidates = [word for word in words if _column_number(word.text) in expected_numbers]
    matches: list[list[PdfWord]] = []
    for candidate in candidates:
        line = [word for word in candidates if abs(word.y_center - candidate.y_center) <= 3.0]
        by_number = {_column_number(word.text): word for word in line}
        if set(by_number) == expected_numbers:
            matches.append([by_number[number] for number in expected])
    if not matches:
        raise ScannerError('PDF_TABLE_UNREADABLE', 'Nomor acuan kolom tabel KK tidak lengkap.')
    anchors = min(matches, key=lambda line: max(word.y_center for word in line) - min(word.y_center for word in line))
    if any(left.x_center >= right.x_center for left, right in zip(anchors, anchors[1:])):
        raise ScannerError('PDF_TABLE_UNREADABLE', 'Urutan nomor acuan kolom tabel KK tidak konsisten.')
    return anchors


def _vertical_grid_boundaries(page: fitz.Page, y: float) -> list[float]:
    """Return one x coordinate per vector grid line crossing ``y``."""
    coordinates: list[float] = []
    for drawing in page.get_drawings():
        for item in drawing.get('items', ()):
            if item[0] == 'l':
                start, end = item[1], item[2]
                if abs(start.x - end.x) <= 0.25 and min(start.y, end.y) - 0.5 <= y <= max(start.y, end.y) + 0.5:
                    coordinates.append((start.x + end.x) / 2)
            elif item[0] == 're':
                rectangle = item[1]
                if rectangle.y0 - 0.5 <= y <= rectangle.y1 + 0.5:
                    coordinates.extend((rectangle.x0, rectangle.x1))
    clusters: list[list[float]] = []
    for coordinate in sorted(coordinates):
        if not clusters or coordinate - clusters[-1][-1] > 2.0:
            clusters.append([coordinate])
        else:
            clusters[-1].append(coordinate)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _table_layout(
    page: fitz.Page, words: list[PdfWord], width: float,
    expected: range, fields: tuple[str, ...],
) -> TableLayout:
    anchors = _numbered_anchor_line(words, expected)
    anchor_y = sum(word.y_center for word in anchors) / len(anchors)

    # Native Dukcapil PDFs contain vector grid lines. Numbered anchors identify
    # which adjacent pair belongs to each field, while the grid supplies the
    # exact edges (including the real table margin, which is not the page edge).
    grid = _vertical_grid_boundaries(page, anchor_y)
    grid_columns: list[tuple[str, float, float]] = []
    for field, anchor in zip(fields, anchors):
        left_candidates = [boundary for boundary in grid if boundary < anchor.x_center]
        right_candidates = [boundary for boundary in grid if boundary > anchor.x_center]
        if not left_candidates or not right_candidates:
            grid_columns = []
            break
        grid_columns.append((field, max(left_candidates) / width, min(right_candidates) / width))
    if len(grid_columns) == len(fields):
        widths = [right - left for _, left, right in grid_columns]
        aligned = all(
            abs(grid_columns[index][2] - grid_columns[index + 1][1]) <= 0.003
            for index in range(len(grid_columns) - 1)
        )
        if aligned and grid_columns[0][1] > 0 and all(cell_width > 0.012 for cell_width in widths):
            return TableLayout(
                anchor_y=anchor_y,
                first_column_left=grid_columns[0][1],
                columns=tuple(grid_columns),
            )

    # Every numbered token is horizontally centred in its own cell. Starting
    # from the page edge, recover cell boundaries as a fallback for PDFs whose
    # table grid is not represented by vector paths.
    right = 1.0
    reversed_columns: list[tuple[str, float, float]] = []
    for field, anchor in reversed(list(zip(fields, anchors))):
        left = (2 * anchor.x_center / width) - right
        reversed_columns.append((field, left, right))
        right = left
    columns = tuple(reversed(reversed_columns))
    widths = [column_right - column_left for _, column_left, column_right in columns]
    if right <= 0 or right >= 0.10 or any(cell_width <= 0.012 for cell_width in widths):
        raise ScannerError('PDF_TABLE_UNREADABLE', 'Lebar kolom hasil deteksi tidak masuk akal.')
    return TableLayout(anchor_y=anchor_y, first_column_left=right, columns=columns)


def _header(words: list[PdfWord], width: float, height: float) -> HeaderExtraction:
    top_numbers = {
        word.text for word in words
        if word.y_center < height * 0.105 and 0.2 < word.x_center / width < 0.8
        and re.fullmatch(r'\d{16}', word.text)
    }
    values: dict[str, str | None] = {'no_kk': next(iter(top_numbers)) if len(top_numbers) == 1 else None}
    label_map = {
        'NAMA KEPALA KELUARGA': 'nama_kepala_keluarga',
        'ALAMAT': 'alamat', 'RT / RW': 'rt_rw', 'KODE POS': 'kode_pos',
        'DESA / KELURAHAN': 'desa', 'KECAMATAN': 'kecamatan',
        'KABUPATEN / KOTA': 'kabupaten', 'PROVINSI': 'provinsi',
    }
    header_words = [word for word in words if 0.10 <= word.y_center / height <= 0.175]
    for label, key in label_map.items():
        label_parts = label.replace(' / ', ' ').split()
        label_zone = (0.13, 0.265) if key in {'nama_kepala_keluarga', 'alamat', 'rt_rw', 'kode_pos'} else (0.58, 0.685)
        value_zone = (0.265, 0.58) if label_zone[0] == 0.13 else (0.685, 0.93)
        candidates = [word for word in header_words if label_zone[0] <= word.x_center / width < label_zone[1]]
        anchor = next((word for word in candidates if (word.text.upper().replace('/', ' ').strip(': ').split() or [''])[0] == label_parts[0]), None)
        if anchor is None:
            continue
        row_words = [word for word in header_words if abs(word.y_center - anchor.y_center) <= 2.5]
        row_label = _cell(row_words, width, *label_zone) or ''
        if not all(part in row_label.upper().replace('/', ' ').split() for part in label_parts):
            continue
        value = _cell(row_words, width, *value_zone)
        if key == 'rt_rw':
            numbers = re.findall(r'\d{1,3}', value or '')
            if len(numbers) == 2:
                values['rt'], values['rw'] = numbers
        elif key == 'kode_pos':
            match = re.search(r'\b\d{5}\b', value or '')
            values[key] = match.group() if match else None
        else:
            values[key] = value
    if not values['no_kk'] or not values.get('nama_kepala_keluarga'):
        raise ScannerError('PDF_TABLE_UNREADABLE', 'Header KK tidak cocok dengan blanko yang didukung.')
    return HeaderExtraction(**values)


def _table_rows(
    words: list[PdfWord], width: float, layout: TableLayout, primary: bool,
    stop_y: float | None = None, expected_rows: set[int] | None = None,
) -> list[dict]:
    region = [
        word for word in words
        if word.y_center > layout.anchor_y + 2.0
        and (stop_y is None or word.y_center < stop_y)
    ]
    markers = [
        word for word in region
        if word.x_center / width < layout.first_column_left
        and re.fullmatch(r'(?:[1-9]|10)', word.text)
        and (expected_rows is None or int(word.text) in expected_rows)
    ]
    if expected_rows is not None:
        # Footer text can contain isolated numbers. The actual row marker is
        # always the first matching number below the numbered header line.
        first_marker: dict[int, PdfWord] = {}
        for marker in sorted(markers, key=lambda word: word.y_center):
            first_marker.setdefault(int(marker.text), marker)
        markers = list(first_marker.values())
    rows: list[dict] = []
    for marker in sorted(markers, key=lambda word: word.y_center):
        tolerance = max(4.0, (marker.y1 - marker.y0) * 0.65)
        line = [word for word in region if abs(word.y_center - marker.y_center) <= tolerance]
        values = {name: _cell(line, width, left, right) for name, left, right in layout.columns}
        values['row'] = int(marker.text)
        if primary:
            # Empty printable slots carry a row number and hyphens, but are not people.
            if not values['nama_lengkap'] and not values['nik']:
                continue
        elif not any(value for key, value in values.items() if key not in {'row', 'tanggal_perkawinan'}):
            continue
        values.pop('tanggal_perkawinan', None)
        rows.append(values)
    row_numbers = [row['row'] for row in rows]
    if len(row_numbers) != len(set(row_numbers)):
        raise ScannerError('PDF_TABLE_UNREADABLE', 'Nomor baris tabel terduplikasi.')
    return rows


def _thumbnail(page: fitz.Page) -> tuple[str, bytes]:
    scale = min(1.5, 900 / max(page.rect.width, page.rect.height))
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image = Image.open(BytesIO(pixmap.tobytes('png')))
    image.thumbnail((get_settings().thumbnail_long_edge, get_settings().thumbnail_long_edge))
    output = BytesIO()
    image.save(output, format='WEBP', quality=60, method=4)
    return 'image/webp', output.getvalue()


def extract_pdf_document(data: bytes) -> NativePdfResult:
    settings = get_settings()
    try:
        document = fitz.open(stream=data, filetype='pdf')
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise ScannerError('PDF_INVALID', 'File PDF tidak dapat dibuka.') from exc
    try:
        if document.needs_pass:
            raise ScannerError('PDF_ENCRYPTED', 'PDF terkunci sandi.')
        if document.page_count > settings.max_pdf_pages:
            raise ScannerError('PDF_TOO_MANY_PAGES', 'Jumlah halaman PDF melebihi batas.')
        if document.page_count != 1:
            raise ScannerError('PDF_INVALID', 'PDF tidak memiliki halaman.')
        page = document[0]
        words = _words(page)
        if sum(len(word.text) for word in words) < settings.min_pdf_text_characters:
            raise ScannerError('PDF_NO_SELECTABLE_TEXT', 'PDF tidak memiliki cukup teks native.')
        width, height = page.rect.width, page.rect.height
        if not 1.25 <= width / height <= 1.6:
            raise ScannerError('PDF_TABLE_UNREADABLE', 'Ukuran halaman tidak cocok dengan blanko KK.')
        primary_layout = _table_layout(page, words, width, range(1, 10), _PRIMARY_FIELDS)
        secondary_layout = _table_layout(page, words, width, range(10, 18), _SECONDARY_FIELDS)
        if primary_layout.anchor_y >= secondary_layout.anchor_y:
            raise ScannerError('PDF_TABLE_UNREADABLE', 'Urutan tabel anggota KK tidak konsisten.')
        header = _header(words, width, height)
        primary = PrimaryExtraction(rows=_table_rows(
            words, width, primary_layout, True, stop_y=secondary_layout.anchor_y,
        ))
        primary_rows = {row.row for row in primary.rows}
        secondary = SecondaryExtraction(rows=_table_rows(
            words, width, secondary_layout, False, expected_rows=primary_rows,
        ))
        if not primary.rows or {row.row for row in primary.rows} != {row.row for row in secondary.rows}:
            raise ScannerError('PDF_TABLE_UNREADABLE', 'Baris anggota pada kedua tabel tidak cocok.')
        members, mismatches = merge_rows(primary, secondary)
        bundle = ExtractionBundle(header=header, primary=primary, secondary=secondary, members=members)
        thumbnail_mime, thumbnail_data = _thumbnail(page)
        return NativePdfResult(
            bundle=bundle, thumbnail_mime=thumbnail_mime, thumbnail_data=thumbnail_data,
            metadata={'source_type': 'native_pdf_text', 'parser': 'kk-landscape-v3', 'page_count': 1, 'word_count': len(words), 'row_mismatches': mismatches},
        )
    finally:
        document.close()
