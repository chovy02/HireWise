"""
Chuẩn bị & kiểm tra điều kiện trước khi chạy load test.
======================================================

    python seed.py                      # kiểm tra tài khoản HR đã sẵn sàng chưa
    python seed.py --create-hr          # nhờ admin tạo tài khoản HR cho load test
    python seed.py --json               # xuất JSON để cắm vào script khác

VÌ SAO CẦN BƯỚC NÀY: mọi endpoint nghiệp vụ của HireWise đều lọc theo chủ sở hữu, nên
một tài khoản mới tinh sẽ thấy danh sách rỗng ở mọi nơi — load test chạy được nhưng
con số đo ra là thời gian trả về một mảng rỗng, tức vô nghĩa. Script này nói thẳng
tài khoản đang có bao nhiêu dữ liệu, và cảnh báo khi lượng dữ liệu quá ít để phép đo
có ý nghĩa.

KHÔNG tự nạp CV: việc đó tiêu quota AI thật và phải do người chạy quyết định.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests

try:
    from dotenv import load_dotenv

    for _up in (".env", "../.env", "../../.env", "../../../.env", "../../../../.env"):
        if os.path.exists(_up):
            load_dotenv(_up, override=False)
            break
except ImportError:
    pass

HOST = os.getenv("LOAD_HOST", "http://localhost:8000").rstrip("/")
HR_EMAIL = os.getenv("LOAD_HR_EMAIL", "")
HR_PASSWORD = os.getenv("LOAD_HR_PASSWORD", "")
ADMIN_EMAIL = os.getenv("LOAD_ADMIN_EMAIL") or os.getenv("DEFAULT_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("LOAD_ADMIN_PASSWORD") or os.getenv("DEFAULT_ADMIN_PASSWORD", "")

# Dưới các mốc này thì phép đo không phản ánh được tải thật.
TOI_THIEU_UNG_VIEN = 10
TOI_THIEU_DA_CHAM = 2


def login(email: str, password: str) -> str | None:
    try:
        r = requests.post(f"{HOST}/auth/login", json={"email": email, "password": password}, timeout=20)
    except requests.RequestException as e:
        print(f"  ✗ Không kết nối được {HOST}: {e}")
        return None
    if r.status_code != 200:
        print(f"  ✗ Đăng nhập {email} thất bại (HTTP {r.status_code}): {r.text[:160]}")
        return None
    return r.json()["access_token"]


def tao_tai_khoan_hr() -> bool:
    if not (ADMIN_EMAIL and ADMIN_PASSWORD):
        print("  ✗ Cần LOAD_ADMIN_EMAIL/PASSWORD (hoặc DEFAULT_ADMIN_* trong .env) để tạo tài khoản.")
        return False
    if not (HR_EMAIL and HR_PASSWORD):
        print("  ✗ Cần LOAD_HR_EMAIL và LOAD_HR_PASSWORD để biết tạo tài khoản nào.")
        return False

    token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not token:
        return False

    r = requests.post(
        f"{HOST}/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "HR Load Test",
            "email": HR_EMAIL,
            "password": HR_PASSWORD,
            "role": "hr_staff",
        },
        timeout=30,
    )
    if r.status_code == 201:
        # Admin tạo trực tiếp -> is_active=True, không phải qua luồng xác minh email.
        print(f"  ✓ Đã tạo tài khoản HR {HR_EMAIL} (đã kích hoạt sẵn).")
        return True
    if r.status_code == 400 and "đã được đăng ký" in r.text:
        print(f"  · Tài khoản {HR_EMAIL} đã tồn tại — bỏ qua bước tạo.")
        return True
    print(f"  ✗ Tạo tài khoản thất bại (HTTP {r.status_code}): {r.text[:200]}")
    return False


def khao_sat_du_lieu(token: str) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    ket_qua: dict = {"host": HOST, "hr_email": HR_EMAIL, "jds": []}

    r = requests.get(f"{HOST}/jds", headers=h, timeout=30)
    r.raise_for_status()
    jds = r.json()

    for jd in sorted(jds, key=lambda j: j.get("candidate_count", 0), reverse=True)[:5]:
        rc = requests.get(f"{HOST}/jds/{jd['id']}/candidates", headers=h, timeout=60)
        candidates = rc.json() if rc.status_code == 200 else []
        rs = requests.get(f"{HOST}/jds/{jd['id']}/shortlists", headers=h, timeout=30)
        shortlists = rs.json() if rs.status_code == 200 else []

        ket_qua["jds"].append({
            "id": jd["id"],
            "title": jd["title"],
            "candidates": len(candidates),
            "scored": sum(1 for c in candidates if c.get("status") == "COMPLETED" and c.get("score") is not None),
            "pending": sum(1 for c in candidates if c.get("status") == "PENDING"),
            "failed": sum(1 for c in candidates if c.get("status") == "FAILED"),
            "shortlists": len(shortlists),
        })

    ket_qua["total_jds"] = len(jds)
    return ket_qua


def main() -> int:
    ap = argparse.ArgumentParser(description="Chuẩn bị dữ liệu cho load test HireWise")
    ap.add_argument("--create-hr", action="store_true", help="Nhờ admin tạo tài khoản HR dùng cho load test")
    ap.add_argument("--json", action="store_true", help="Chỉ in JSON, không in bảng cho người đọc")
    args = ap.parse_args()

    if not args.json:
        print(f"\n  Máy chủ: {HOST}\n")

    if args.create_hr and not tao_tai_khoan_hr():
        return 2

    if not (HR_EMAIL and HR_PASSWORD):
        print("  ✗ Chưa đặt LOAD_HR_EMAIL / LOAD_HR_PASSWORD.")
        return 2

    token = login(HR_EMAIL, HR_PASSWORD)
    if not token:
        return 2

    du_lieu = khao_sat_du_lieu(token)

    if args.json:
        print(json.dumps(du_lieu, ensure_ascii=False, indent=2))
        return 0

    print(f"  ✓ Đăng nhập được bằng {HR_EMAIL} — tài khoản có {du_lieu['total_jds']} dự án.\n")
    if not du_lieu["jds"]:
        print("  ✗ Tài khoản chưa có dự án nào. Hãy tạo một dự án và nạp CV trước khi đo.\n")
        return 1

    print(f"  {'Dự án':<34} {'Ứng viên':>9} {'Đã chấm':>8} {'Chờ':>5} {'Lỗi':>5} {'Shortlist':>10}")
    print("  " + "─" * 76)
    for jd in du_lieu["jds"]:
        ten = jd["title"] if len(jd["title"]) <= 33 else jd["title"][:32] + "…"
        print(f"  {ten:<34} {jd['candidates']:>9} {jd['scored']:>8} {jd['pending']:>5} "
              f"{jd['failed']:>5} {jd['shortlists']:>10}")

    tot_nhat = max(du_lieu["jds"], key=lambda j: j["candidates"])
    print()

    canh_bao = []
    if tot_nhat["candidates"] < TOI_THIEU_UNG_VIEN:
        canh_bao.append(
            f"Dự án nhiều ứng viên nhất chỉ có {tot_nhat['candidates']} hồ sơ "
            f"(nên có ít nhất {TOI_THIEU_UNG_VIEN}). Bảng xếp hạng sẽ trả về quá nhanh "
            "so với thực tế, nên con số p95 đo được lạc quan hơn sự thật."
        )
    if tot_nhat["scored"] < TOI_THIEU_DA_CHAM:
        canh_bao.append(
            f"Chỉ {tot_nhat['scored']} hồ sơ đã chấm xong. Các task cần ứng viên có "
            "điểm (so sánh, phỏng vấn, chỉnh điểm) sẽ tự bỏ qua."
        )
    if tot_nhat["pending"]:
        canh_bao.append(
            f"{tot_nhat['pending']} hồ sơ đang chờ chấm — worker vẫn đang chạy nền và "
            "chiếm CPU/DB. Đợi chấm xong rồi hãy đo, nếu không độ trễ đo được lẫn cả "
            "tải của worker."
        )
    for c in canh_bao:
        print(f"  ⚠ {c}")
    if canh_bao:
        print()

    print("  Sẵn sàng đo. Lệnh gợi ý:\n")
    print(f'    set LOAD_JD_ID={tot_nhat["id"]}')
    print(f"    locust -f locustfile.py --host {HOST} --headless -u 20 -r 5 -t 3m\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
