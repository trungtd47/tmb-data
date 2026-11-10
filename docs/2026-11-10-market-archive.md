# Lưu trữ giá thị trường hằng ngày (market archive)

**Date:** 2026-11-10 · **Task:** t_8084425e

Mục tiêu: TMB tự tích lũy dữ liệu gốc theo thời gian (USD Vietcombank, SJC miếng, nhẫn SJC, vàng thế giới, USDT P2P) để làm trang thống kê. Trước đây chỉ USDT P2P được lưu; các số khác mất dần mỗi ngày.

## File dữ liệu (repo tmb-data, nhánh main)

| File | Nội dung | Giữ |
|---|---|---|
| `public/data/market-hourly.json` | Mẫu giờ: `t` (UTC), `usdt_buy/sell/mid`, `vcb_cash_buy/transfer_buy/sell`, `sjc_buy/sell`, `ring_buy/sell`, `xau_usd`, `delayed`, `at_usdt/at_vcb/at_gold` (thời điểm cập nhật của từng nguồn) | 45 ngày |
| `public/data/market-daily.json` | 1 dòng/ngày giờ VN: mỗi chỉ số `{open,high,low,close,avg,n}` + chỉ số dẫn xuất | vĩnh viễn |
| `public/data/p2p-daily.json`, `p2p-history.json` | Cron P2P cũ (không đổi) | như cũ |

Raw: `https://raw.githubusercontent.com/trungtd47/tmb-data/main/public/data/market-daily.json`

`market-daily.json` có `schema_version`, `method` (công thức tiếng Việt từng chỉ số), `sources`, `days[]`. Dòng ngày có thêm: `backfill` (true = dựng lại từ nguồn lịch sử, `n:1`), `samples` (số mẫu giờ), `spread_unreliable` (ngày < 2026-11-10), `weekend` (T7/CN, nguồn giữ giá phiên trước), `src` (nguồn từng nhóm).

## Công thức

- `usdt_mid` = trung bình giá mua/bán USDT P2P (Binance P2P, 5 quảng cáo đầu mỗi chiều).
- `usdt_vs_vcb_pct` = (USDT mid − VCB bán) / VCB bán × 100.
- Vàng thế giới quy đổi = `xau_usd` × 1,20565 oz/lượng × VCB bán (1,20565 = 37,5 g / 31,1035 g).
- `sjc_vs_world_mil` = (SJC bán − vàng thế giới quy đổi) / 1.000.000 (triệu đồng/lượng); `sjc_vs_world_pct` = chênh đó / vàng thế giới quy đổi × 100.
- `sjc_spread_pct` = (SJC bán − SJC mua) / SJC bán × 100; `ring_spread_pct` tương tự cho nhẫn; `usd_cash_spread_pct` = (VCB bán − VCB mua tiền mặt) / VCB bán × 100.
- Dòng live: dẫn xuất tính trên từng mẫu giờ đủ đầu vào rồi mới gộp OHLC/avg theo ngày. Dòng backfill: tính trên số 1 bản/ngày, với USDT dùng `avg` ngày của p2p-daily.
- Thiếu nguồn / vàng `delayed` / số ngoài khoảng hợp lý ⇒ `null`. Không điền số giả, không carry-forward.

## Script và cron (ngoài repo, profile coder)

- `~/.hermes/profiles/coder/scripts/market_archive.py` - stdlib, cron `38f9897db3c7` "Market Archive (giá hằng giờ)": `7 * * * *`, Asia/Ho_Chi_Minh, no_agent, deliver local (giống cron P2P; stdout rỗng khi ổn, chỉ in khi lỗi). 1 request `themoneybrew.org/api/gia-hom-nay`/giờ. Commit + push qua git worktree riêng từ `origin/main` (không đụng working tree của `~/projects/tmb-data`), tự thử lại tối đa 3 lần nếu push bị từ chối do cron P2P đẩy xen giữa. Bỏ qua mẫu nếu mẫu trước < 15 phút.
- `~/.hermes/profiles/coder/scripts/market_backfill.py` - chạy 1 lần (idempotent, chỉ thay dòng `backfill:true`, không đụng dòng live). Giãn request VCB ≥ 2,2 giây, cache ở thư mục scratch.
- Test: `tests/test_market_archive.py` (`python3 -m unittest tests/test_market_archive.py`), 13 test: gộp ngày OHLC, null/delayed, công thức premium, ranh giới ngày VN, cửa sổ 45 ngày.

## Nguồn backfill

| Cột | Nguồn | Ghi chú |
|---|---|---|
| USD VCB (mua tiền mặt/chuyển khoản/bán) | `vietcombank.com.vn/api/exchangerates?date=YYYY-MM-DD` | Bản cuối ngày (`UpdatedDate` 23:00). T7/CN VCB giữ giá thứ Sáu. |
| SJC miếng, nhẫn SJC 9999, XAU/USD | `vang.today/api/prices?days=N` (mã `SJL1L10`, `SJ9999`, `XAUUSD`) | Cùng nguồn với dữ liệu live nên chuỗi liền mạch. Mỗi ngày 1 mốc (giá cập nhật cuối ngày). |
| USDT | `p2p-daily.json` (OHLC, avg, spread) | `spread_unreliable:true` cho ngày < 2026-11-10 (chiều mua/bán bị đảo, sửa 6ebaf93b); `mid`/avg đúng. Không xóa gì. |

### Lệch so với brief

- **SJC không lấy từ Simplize** mà từ vang.today `SJL1L10`: Simplize `SJC:M1L` thiếu 29/93 ngày (cuối tuần, lễ), vang.today đủ 93/93 và cùng nguồn với dòng live. Simplize dùng để đối chiếu: trong 64 ngày có cả hai, 52 ngày trùng khớp tuyệt đối, 12 ngày lệch ≤ 1,5 triệu/lượng (≤ 1%, do chốt giá khác thời điểm trong ngày).
- **Nhẫn**: Simplize không có ticker nhẫn (thử `SJC:N1L`, `NHAN`, `R9999`, `N9999` đều rỗng); lấy từ vang.today `SJ9999` (khớp số live 137,2/141,2 triệu).
- **Vàng thế giới**: Stooq bị chặn bằng JS challenge. Dùng vang.today `XAUUSD` (spot, khớp gold-api.com live trong ~0,3%). Đối chiếu Simplize `GC=F` (hợp đồng tương lai COMEX): XAU thấp hơn GC=F trung bình 0,73%, tối đa 1,4% - cùng chiều với phí contango, không dùng GC=F vì không phải giá spot.
- **USD VCB 16/10/2026**: bản cuối ngày bán 26.080 (mua tiền mặt 25.670); vault ghi 26.060 (mua 25.650) chụp lúc khác trong ngày. Cùng lệch +20 hai chiều nên là chênh theo giờ, không phải lỗi dữ liệu.

## Độ phủ (2026-08-09 → 2026-11-09, 93 ngày backfill; từ 2026-11-10 là dòng live)

| Cột | Số ngày có | Ngày thiếu |
|---|---|---|
| usdt_mid (OHLC từ p2p-daily) | 93/93 | không |
| usdt_spread | 93/93 | không (cờ unreliable cả 93 ngày) |
| vcb_cash_buy / transfer_buy / sell | 93/93 | không |
| sjc_buy / sjc_sell | 93/93 | không |
| ring_buy / ring_sell | 93/93 | không |
| xau_usd | 93/93 | không |
| 6 chỉ số dẫn xuất | 93/93 | không |

27/93 ngày là T7/CN (cờ `weekend:true`): giá VCB, SJC giữ nguyên phiên trước; XAU là mốc đóng cửa thứ Sáu/giá cuối. Khi vẽ biểu đồ nên lọc `weekend` nếu cần chuỗi chỉ ngày giao dịch.

## Lưu ý cho trang thống kê

- Dòng backfill chỉ 1 điểm/ngày (`n:1`), `open=high=low=close=avg`; chỉ USDT có OHLC thật (n = số mẫu 30 phút). High/low trong ngày của VCB/SJC/vàng chỉ có từ 2026-11-10 trở đi.
- **2026-11-10 là ngày không trọn** (cron bắt đầu giữa ngày, xem `samples`).
- Dòng ngày live ghi đè theo cửa sổ 45 ngày của market-hourly, dòng backfill không bị chạm.
- Vàng `delayed` ở API (fallback Simplize theo ngày) ghi `null`, `delayed:true` trong mẫu giờ.

## Lesson

Nguồn "đủ 1 request/ngày" cần kiểm độ phủ trước khi chọn: Simplize thiếu 31% ngày, nguồn cùng chuỗi với live (vang.today) đủ 100% và khỏi lệch nguồn khi nối backfill với dòng live.

## Cập nhật schema v2 (2026-11-10, t_1d354c9c): giá vàng theo thương hiệu

- `schema_version` 1 -> 2. Thêm cho 7 sản phẩm `btmh_sjc` (Bảo Tín Mạnh Hải - vàng miếng SJC), `btmh_kgb` (BTMH - nhẫn Kim Gia Bảo 24K), `doji_sjc`, `doji_ring` (nhẫn tròn 9999 Hưng Thịnh Vượng), `pnj_ring` (nhẫn trơn PNJ 999.9), `pq_sjc`, `pq_ring` (Phú Quý) các cột `{id}_buy`, `{id}_sell` (VND/lượng, hãng mua vào/bán ra) và `{id}_spread_pct` = (bán - mua) / bán x 100, cùng dạng `{open,high,low,close,avg,n}`. SJC miếng đã có `sjc_*` nên không lặp. Mọi dòng cũ được thêm cột = `null` (không có key thiếu).
- Live: mỗi mẫu giờ lấy từ `brands[]` của `/api/gia-hom-nay` (sản phẩm thiếu/ẩn do nguồn lỗi -> null).
- Backfill BTMH (`market_brand_backfill.py`, chạy 1 lần): `goldChartData` của baotinmanhhai.vn, 2026-08-09 -> 2026-11-09, **93/93 ngày cho cả `btmh_sjc` và `btmh_kgb`** (mua + bán + spread). So với `sjc_*` (vang.today) 87/93 ngày trùng tuyệt đối, 6 ngày lệch 0,3 - 2,0 triệu/lượng (chốt khác thời điểm trong ngày). DOJI/PNJ/Phú Quý: **chưa backfill (0 ngày)**, bắt đầu có từ 2026-11-10 khi cron lấy được `brands[]`.
- Test: `python3 -m unittest tests/test_market_archive.py` 17/17.

## Cập nhật cách tính USDT (2026-11-10, t_1554c5d4): trung vị và thị trường chéo giá

- **Từ commit này (site chính, 10/11/2026) giá USDT mỗi chiều là TRUNG VỊ của 5 quảng cáo đầu**, không còn trung bình. Lý do: một quảng cáo lệch (vd 25.900 giữa các giá 25.804-25.810) kéo trung bình lên. Các mẫu 30 phút và dòng ngày trước thời điểm này vẫn là trung bình, **không sửa lại**; chênh giữa hai cách thường chỉ vài chục đồng.
- **Spread âm từ 10/11 trở đi (nếu có) là thị trường chéo thật**, khác với lỗi đảo chiều mua/bán trước 10/11 (xem `spread_unreliable`, sửa 6ebaf93b). Binance P2P đôi khi có giá người mua trả (tradeType=SELL) cao hơn giá người bán rao (tradeType=BUY) do hạn mức/điều kiện quảng cáo khác nhau; ví dụ 10:50 ngày 10/11: mua 25.780, bán lại 25.806 (trung vị).
- `/api/p2p` từ nay trả `spread = max(0, buy - sell)` và thêm `crossed` (true khi bán lại > mua), nên mẫu mới do cron ghi sẽ có `spread` 0 thay vì số âm; `p2p-daily.json` đã lọc `spread > 0` khi lấy trung vị. Muốn đếm số lần chéo giá thì dùng `crossed` ở API live, không suy ra từ spread lịch sử.
