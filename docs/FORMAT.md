# Định dạng tệp TT10 – nguồn & điểm chưa chắc chắn

## Nguồn chính (đã đối chiếu)
1. **Phụ lục XV – Tên, cấu trúc và nội dung của tệp dữ liệu**, Thông tư 10/2021/TT-BTNMT. Bản .docx lưu tại `docs/sources/TT10-2021_PhuLucXV.docx`, tải từ https://www.luatmoitruong.vn/thong-tu-10-2021-tt-btnmt/phu-luc/phu-luc-xv.-ten-cau-truc-va-noi-dung-cua-tep-du-lieu
2. **Điều 39 TT10** (truyền dữ liệu, 5 phút, FTP/FTPs/sFTP, lưu 60 ngày, gửi bù, báo cáo khi gián đoạn >12 giờ, GMT+7): https://thuvienphapluat.vn/van-ban/Tai-nguyen-Moi-truong/Thong-tu-10-2021-TT-BTNMT-ky-thuat-quan-trac-moi-truong-481294.aspx
3. Hướng dẫn của Sở Đồng Nai (nhắc lại Điều 39 + Phụ lục 15): https://ttptquydat.stnmt.dongnai.gov.vn/VN/Huongdantruyendulieuqt

## QTLink triển khai đúng như Phụ lục XV
| Mục | Quy định | Code |
|---|---|---|
| Tên tệp | `TenTinh_TenCoso_TenTram_Thoigian.txt`, Thoigian = `yyyyMMddhhmmss` | `tt10.file_name` |
| TenTinh | Ký hiệu Bảng 33 (vd BN, HN, HCM, DN, BD) | `tt10.PROVINCE_CODES` (chỉ cảnh báo) |
| TenCoSo | 4 ký tự, viết liền không dấu | `validate_ids` |
| TenTram | 6 ký tự: `NUO`+3 (nước) / `KHI`+3 (khí) | `validate_ids` |
| Dòng dữ liệu | `Thông số<TAB>Kết quả<TAB>Đơn vị<TAB>Thời gian<TAB>Trạng thái`, mỗi thông số một dòng | `tt10.build_content` |
| Ký hiệu thông số/đơn vị | Bảng 34 (pH `-`, COD `mg/L`, `Flow out 1` `m3/h`, SO2 `mg/Nm3`, O2 `%V`…) | do người dùng cấu hình |
| Trạng thái | `00` đang đo, `01` hiệu chuẩn, `02` báo lỗi thiết bị (Bảng 35) | `tt10.STATUS_*` |
| Thư mục máy chủ | `TramA/yyyy/mm/dd` | `tt10.remote_dir` |

## Chưa chắc chắn → để cấu hình được
- **Mã tỉnh sau sáp nhập 2025** (63 → 34 tỉnh): Bảng 33 là danh sách cũ. `station.province` nhập tự do, chỉ cảnh báo.
- **Tên thư mục `TramA`** và thư mục gốc trên máy chủ Sở: `station_folder`, `remote_root` mỗi đích.
- **Số chữ số thập phân** (mặc định 2), **ký tự xuống dòng** (CRLF mặc định / LF), **mã hoá** (UTF-8, nội dung chỉ ASCII).
- **Giá trị 5 phút**: TT10 không nói lấy trung bình hay tức thời → `aggregate: avg|last`.
- **Khi không có số đo**: ghi `0` + trạng thái `02` (không quy định).
- **Có dòng tiêu đề không**: Phụ lục XV không có dòng tiêu đề → QTLink không ghi.
- Một số Sở có hướng dẫn riêng (ví dụ yêu cầu sFTP, tên tài khoản). Luôn hỏi Sở trước khi nghiệm thu.

## Lưu ý về nguồn thương mại mâu thuẫn
Bài DeviceLab (https://devicelab.vn/kien-thuc/truyen-du-lieu-quan-trac-so-tnmt-ftp-sftp/) mô tả tên tệp `[MÃ_TRẠM]_[YYYYMMDD]_[HHMMSS].txt`, dòng tiêu đề kiểu bảng ngang và mã trạng thái 03/04. Điều này **không khớp** Phụ lục XV gốc, nên QTLink **không** dùng.
