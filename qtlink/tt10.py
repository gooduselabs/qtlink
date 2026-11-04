"""Định dạng tệp dữ liệu theo Phụ lục XV, Thông tư 10/2021/TT-BTNMT.

Nguồn: docs/sources/TT10-2021_PhuLucXV.docx (bản Phụ lục XV), Điều 39 TT10.
- Tên tệp: TenTinh_TenCoso_TenTram_Thoigian.txt, Thoigian = yyyyMMddhhmmss
- TenCoSo: 4 ký tự, viết liền không dấu; TenTram: 6 ký tự (NUOxxx / KHIxxx)
- Mỗi dòng: Thông số<TAB>Kết quả<TAB>Đơn vị<TAB>Thời gian(yyyyMMddhhmmss)<TAB>Trạng thái
- Trạng thái: 00 đang đo, 01 hiệu chuẩn, 02 báo lỗi thiết bị (Bảng 35)
- Thư mục máy chủ: /TramA/yyyy/mm/dd
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime

STATUS_MEASURING = "00"
STATUS_CALIBRATING = "01"
STATUS_FAULT = "02"
VALID_STATUS = {STATUS_MEASURING, STATUS_CALIBRATING, STATUS_FAULT}

# Bảng 33 (63 tỉnh, trước sáp nhập 2025). Chỉ để kiểm tra/gợi ý; mã tỉnh luôn cấu hình được.
PROVINCE_CODES = {
    "AG","BK","BD","BDi","BG","BL","BN","BP","BT","BTh","BV","CB","CM","CT","DNa","DL","DNo",
    "DB","DN","DT","GL","HG","HNa","HN","HT","HD","HP","HGi","HB","HY","KG","KH","KT","LC","LD",
    "LS","LCa","LA","ND","NA","NB","NT","PT","PY","QB","QNa","QNg","QN","QT","HCM","SL","ST","TN",
    "TB","TNg","TH","TTH","TG","TQ","TV","VL","VP","YB",
}
TS_FMT = "%Y%m%d%H%M%S"
_ASCII = re.compile(r"^[A-Za-z0-9]+$")


@dataclass
class Record:
    parameter: str
    value: float | None
    unit: str
    time: datetime
    status: str = STATUS_MEASURING


def validate_ids(province: str, facility: str, station: str, strict: bool = True) -> list[str]:
    """Trả về danh sách cảnh báo (rỗng = hợp lệ)."""
    w = []
    for name, v in (("province", province), ("facility", facility), ("station", station)):
        if not _ASCII.match(v or ""):
            w.append(f"{name} phải viết liền, không dấu, chỉ chữ/số: {v!r}")
    if province not in PROVINCE_CODES:
        w.append(f"Mã tỉnh {province!r} không có trong Bảng 33 (có thể do sáp nhập tỉnh 2025 - kiểm tra với Sở)")
    if strict and len(facility) != 4:
        w.append(f"TenCoSo nên gồm 4 ký tự (hiện {len(facility)})")
    if strict and (len(station) != 6 or station[:3].upper() not in ("NUO", "KHI")):
        w.append("TenTram nên gồm 6 ký tự, bắt đầu bằng NUO (nước) hoặc KHI (khí)")
    return w


def file_name(province: str, facility: str, station: str, t: datetime) -> str:
    return f"{province}_{facility}_{station}_{t.strftime(TS_FMT)}.txt"


def format_value(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "0"  # không có số đo: ghi 0 kèm trạng thái 02 (cấu hình được ở tầng trên)
    return f"{v:.{decimals}f}"


def build_content(records: list[Record], decimals: int = 2, newline: str = "\r\n") -> str:
    lines = []
    for r in records:
        if r.status not in VALID_STATUS:
            raise ValueError(f"Mã trạng thái không hợp lệ: {r.status}")
        if "\t" in r.parameter or "\t" in r.unit:
            raise ValueError("Ký hiệu thông số/đơn vị không được chứa TAB")
        lines.append("\t".join([r.parameter, format_value(r.value, decimals), r.unit,
                                r.time.strftime(TS_FMT), r.status]))
    return newline.join(lines) + newline


def remote_dir(root: str, station_folder: str, t: datetime) -> str:
    root = (root or "").rstrip("/")
    return f"{root}/{station_folder}/{t:%Y}/{t:%m}/{t:%d}"


def parse_content(text: str) -> list[Record]:
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        p, v, u, t, s = line.split("\t")
        out.append(Record(p, float(v), u, datetime.strptime(t, TS_FMT), s))
    return out
