"""Чтение старых книг Excel (.xls) стандартной библиотекой.

Областные управления финансов выкладывают отчёты в формате BIFF8 внутри контейнера
OLE2, а не в xlsx. Внешние библиотеки в проекте не используются, поэтому здесь
разобраны ровно те две вещи, которые нужны: как достать поток Workbook из
контейнера и как прочитать из него значения ячеек.

Поддерживается то, что встречается в этих отчётах: общая таблица строк (SST),
числа (NUMBER, RK, MULRK), строки в ячейках (LABEL, LABELSST), формулы с уже
посчитанным значением (FORMULA и следующий за ней STRING), пустые ячейки (BLANK,
MULBLANK). Всё остальное пропускается: задача не в полной поддержке формата, а в
чтении конкретных отчётов.
"""

from __future__ import annotations

import struct

BOF = 0x0809
EOF = 0x000A
BOUNDSHEET = 0x0085
SST = 0x00FC
CONTINUE = 0x003C
ROW = 0x0208
NUMBER = 0x0203
RK = 0x027E
MULRK = 0x00BD
LABEL = 0x0204
LABELSST = 0x00FD
FORMULA = 0x0006
STRING = 0x0207
BLANK = 0x0201
MULBLANK = 0x00BE
RSTRING = 0x00D6

SECTOR = 512
DIFSECT = 0xFFFFFFFC
FATSECT = 0xFFFFFFFD
ENDOFCHAIN = 0xFFFFFFFE
FREESECT = 0xFFFFFFFF


class XlsError(RuntimeError):
    pass


# --- Контейнер OLE2 ------------------------------------------------------------


def _fat(raw: bytes) -> list[int]:
    """Таблица размещения секторов: по ней собираются цепочки потоков."""
    count = struct.unpack_from("<I", raw, 44)[0]
    sectors = list(struct.unpack_from("<109I", raw, 76))
    difat_start, difat_count = struct.unpack_from("<II", raw, 68)
    sector = difat_start
    for _ in range(difat_count):
        if sector in (ENDOFCHAIN, FREESECT):
            break
        offset = (sector + 1) * SECTOR
        block = struct.unpack_from("<128I", raw, offset)
        sectors += list(block[:127])
        sector = block[127]

    fat: list[int] = []
    for index in sectors[:count]:
        if index in (ENDOFCHAIN, FREESECT):
            continue
        offset = (index + 1) * SECTOR
        fat += list(struct.unpack_from("<128I", raw, offset))
    return fat


def _chain(fat: list[int], start: int) -> list[int]:
    out: list[int] = []
    sector = start
    while sector not in (ENDOFCHAIN, FREESECT) and sector < len(fat):
        if sector in out:
            raise XlsError("цепочка секторов зациклилась")
        out.append(sector)
        sector = fat[sector]
    return out


def _read_chain(
    raw: bytes, fat: list[int], start: int, size: int | None = None
) -> bytes:
    parts = [raw[(s + 1) * SECTOR : (s + 2) * SECTOR] for s in _chain(fat, start)]
    data = b"".join(parts)
    return data[:size] if size else data


def workbook_stream(raw: bytes) -> bytes:
    """Поток Workbook из контейнера OLE2."""
    if raw[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise XlsError("файл не является книгой .xls")
    fat = _fat(raw)
    dir_start = struct.unpack_from("<I", raw, 48)[0]
    directory = _read_chain(raw, fat, dir_start)

    entries = []
    for offset in range(0, len(directory), 128):
        chunk = directory[offset : offset + 128]
        if len(chunk) < 128:
            break
        name_len = struct.unpack_from("<H", chunk, 64)[0]
        name = chunk[: max(name_len - 2, 0)].decode("utf-16-le", "ignore")
        start, size = struct.unpack_from("<IQ", chunk, 116)
        entries.append((name, start, size))

    root = entries[0] if entries else None
    for name, start, size in entries:
        if name in ("Workbook", "Book"):
            if size >= 4096:
                return _read_chain(raw, fat, start, size)
            # Короткие потоки лежат в мини-контейнере внутри корневого потока.
            mini_fat_start = struct.unpack_from("<I", raw, 60)[0]
            mini_fat = []
            for sector in _chain(fat, mini_fat_start):
                mini_fat += list(
                    struct.unpack_from("<128I", raw, (sector + 1) * SECTOR)
                )
            mini_stream = _read_chain(raw, fat, root[1], root[2]) if root else b""
            out = bytearray()
            index = start
            while index not in (ENDOFCHAIN, FREESECT) and index < len(mini_fat):
                out += mini_stream[index * 64 : (index + 1) * 64]
                index = mini_fat[index]
            return bytes(out[:size])
    raise XlsError("в книге нет потока Workbook")


# --- Записи BIFF ---------------------------------------------------------------


def records(stream: bytes):
    """Записи потока: код, тело. Продолжения CONTINUE приклеиваются к предыдущей."""
    offset = 0
    pending: tuple[int, bytearray] | None = None
    while offset + 4 <= len(stream):
        code, length = struct.unpack_from("<HH", stream, offset)
        body = stream[offset + 4 : offset + 4 + length]
        offset += 4 + length
        if code == CONTINUE and pending is not None:
            pending[1].extend(body)
            continue
        if pending is not None:
            yield pending[0], bytes(pending[1])
        pending = (code, bytearray(body))
    if pending is not None:
        yield pending[0], bytes(pending[1])


def _unicode_string(data: bytes, pos: int) -> tuple[str, int]:
    """Строка BIFF8: длина в символах, флаги, потом сами символы."""
    length = struct.unpack_from("<H", data, pos)[0]
    flags = data[pos + 2]
    pos += 3
    rich = far = 0
    if flags & 0x08:
        rich = struct.unpack_from("<H", data, pos)[0]
        pos += 2
    if flags & 0x04:
        far = struct.unpack_from("<I", data, pos)[0]
        pos += 4
    if flags & 0x01:
        text = data[pos : pos + length * 2].decode("utf-16-le", "ignore")
        pos += length * 2
    else:
        text = data[pos : pos + length].decode("cp1251", "ignore")
        pos += length
    pos += rich * 4 + far
    return text, pos


def shared_strings(body: bytes) -> list[str]:
    out: list[str] = []
    pos = 8
    while pos < len(body):
        try:
            text, pos = _unicode_string(body, pos)
        except (struct.error, IndexError):
            break
        out.append(text)
    return out


def _rk_value(bits: int) -> float:
    """Число в упакованном виде: целое или урезанное с плавающей точкой."""
    if bits & 0x02:
        value = float(bits >> 2)
    else:
        value = struct.unpack("<d", struct.pack("<Q", (bits & 0xFFFFFFFC) << 32))[0]
    return value / 100 if bits & 0x01 else value


def sheet_names(stream: bytes) -> list[tuple[str, int]]:
    """Имена листов и смещения их начала в потоке."""
    names = []
    for code, body in records(stream):
        if code == BOUNDSHEET:
            position = struct.unpack_from("<I", body, 0)[0]
            length = body[6]
            flags = body[7]
            if flags & 0x01:
                text = body[8 : 8 + length * 2].decode("utf-16-le", "ignore")
            else:
                text = body[8 : 8 + length].decode("cp1251", "ignore")
            names.append((text, position))
    return names


def sheet_rows(stream: bytes, start: int, strings: list[str]) -> list[list[str]]:
    """Ячейки одного листа как таблица строк.

    Значения приводятся к строкам: дальше их разбирает та же логика, что и для
    xlsx, а форматы чисел в этих отчётах не несут смысла."""
    cells: dict[int, dict[int, str]] = {}
    last: tuple[int, int] | None = None
    for code, body in records(stream[start:]):
        if code == EOF:
            break
        try:
            if code in (NUMBER, RK, LABELSST, LABEL, FORMULA, BLANK):
                row, col = struct.unpack_from("<HH", body, 0)
            if code == NUMBER:
                value = struct.unpack_from("<d", body, 6)[0]
                cells.setdefault(row, {})[col] = f"{value:.10g}"
            elif code == RK:
                bits = struct.unpack_from("<I", body, 6)[0]
                cells.setdefault(row, {})[col] = f"{_rk_value(bits):.10g}"
            elif code == MULRK:
                row, first = struct.unpack_from("<HH", body, 0)
                count = (len(body) - 6) // 6
                for i in range(count):
                    bits = struct.unpack_from("<I", body, 4 + i * 6 + 2)[0]
                    cells.setdefault(row, {})[first + i] = f"{_rk_value(bits):.10g}"
            elif code == LABELSST:
                index = struct.unpack_from("<I", body, 6)[0]
                if index < len(strings):
                    cells.setdefault(row, {})[col] = strings[index]
            elif code == LABEL:
                text, _ = _unicode_string(body, 6)
                cells.setdefault(row, {})[col] = text
            elif code == FORMULA:
                raw = body[6:14]
                if raw[6:8] == b"\xff\xff" and raw[0] == 0:
                    last = (row, col)  # значение придёт следующей записью STRING
                elif raw[6:8] == b"\xff\xff" and raw[0] == 3:
                    cells.setdefault(row, {})[col] = ""
                else:
                    value = struct.unpack("<d", raw)[0]
                    cells.setdefault(row, {})[col] = f"{value:.10g}"
            elif code == STRING and last:
                text, _ = _unicode_string(body, 0)
                cells.setdefault(last[0], {})[last[1]] = text
                last = None
        except (struct.error, IndexError):
            continue
    if not cells:
        return []
    width = max(max(row) for row in cells.values()) + 1
    return [
        [cells.get(index, {}).get(col, "") for col in range(width)]
        for index in range(max(cells) + 1)
    ]


class Workbook:
    """Книга .xls с тем же интерфейсом, что у разбора xlsx в budget.py."""

    def __init__(self, raw: bytes):
        self.stream = workbook_stream(raw)
        self.strings: list[str] = []
        for code, body in records(self.stream):
            if code == SST:
                self.strings = shared_strings(body)
                break
        self.sheets = [(name, str(offset)) for name, offset in sheet_names(self.stream)]
        if not self.sheets:
            raise XlsError("в книге нет листов")

    @property
    def modified(self) -> str:
        return ""

    def rows(self, path: str) -> list[list[str]]:
        return sheet_rows(self.stream, int(path), self.strings)
