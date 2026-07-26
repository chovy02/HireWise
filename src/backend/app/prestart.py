"""Chuẩn bị database TRƯỚC khi uvicorn bắt đầu nhận request.

Chạy một lần lúc container `api` khởi động (xem `command` của service api trong
docker-compose.yml). Giải quyết 3 nguyên nhân khiến frontend báo
"Backend not reachable on http://localhost:8000":

1. Postgres chưa sẵn sàng. `depends_on` chỉ đợi container CHẠY, không đợi Postgres
   nhận kết nối — lần `up` đầu tiên Postgres còn phải initdb mất cả chục giây, api
   nối vào là chết. Ở đây ta đợi hẳn tới khi nối được.

2. Bảng chưa tồn tại (máy mới clone về, volume trống).

3. Bảng có rồi nhưng THIẾU CỘT vì migration chưa chạy. Đây đúng là lỗi
   `column users.is_banned does not exist` từng làm api crash ngay lúc startup.

QUAN HỆ GIỮA create_all VÀ ALEMBIC — đọc kỹ trước khi sửa file này:
Schema nền của dự án do `Base.metadata.create_all()` dựng, KHÔNG phải do alembic;
các file trong migrations/ đều là ALTER tăng dần, không có migration nào tạo bảng
gốc. Vì vậy:
  - DB trống  -> create_all dựng đủ schema HIỆN TẠI (đã gồm mọi cột mới) nên chỉ
    cần `stamp head` để đánh dấu "đã ở bản mới nhất". Chạy `upgrade head` ở đây sẽ
    hỏng: alembic đi thêm cột mà create_all vừa tạo -> DuplicateColumn.
  - DB đã có sẵn (đồng đội pull code mới về, volume cũ) -> create_all không bao giờ
    ALTER bảng đã tồn tại, nên phải `upgrade head` để bổ sung cột còn thiếu.
Phân biệt hai trường hợp bằng sự tồn tại của bảng `alembic_version`.
"""

import os
import sys
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app.database import engine
from app import models

# /app trong container (thư mục chứa alembic.ini và migrations/).
BACKEND_ROOT = Path(__file__).resolve().parent.parent

DB_WAIT_TIMEOUT = int(os.getenv("DB_WAIT_TIMEOUT", "90"))


def _log(msg: str) -> None:
    print(f"[prestart] {msg}", flush=True)


def wait_for_db(timeout: int = DB_WAIT_TIMEOUT) -> None:
    """Thử kết nối tới khi Postgres trả lời, hoặc thoát hẳn khi quá hạn."""
    deadline = time.time() + timeout
    attempt = 0
    while True:
        attempt += 1
        try:
            with engine.connect():
                _log(f"Postgres đã sẵn sàng (thử {attempt} lần).")
                return
        except OperationalError as e:
            if time.time() >= deadline:
                _log(f"Không kết nối được Postgres sau {timeout}s: {e}")
                sys.exit(1)
            if attempt == 1 or attempt % 5 == 0:
                _log(f"Đợi Postgres… (lần {attempt})")
            time.sleep(2)


def _alembic_config() -> Config:
    """Config trỏ tuyệt đối, để chạy được dù CWD là gì.

    URL lấy từ DATABASE_URL trong migrations/env.py, không đọc từ alembic.ini
    (dòng sqlalchemy.url trong đó chỉ là placeholder).
    """
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return cfg


def sync_schema() -> None:
    fresh = not inspect(engine).has_table("alembic_version")

    # Tạo các bảng còn THIẾU. Không bao giờ sửa bảng đã có -> phần cột thiếu để
    # alembic lo ở dưới.
    models.Base.metadata.create_all(bind=engine)

    cfg = _alembic_config()
    if fresh:
        _log("DB mới: create_all đã dựng schema hiện tại -> đánh dấu 'stamp head'.")
        command.stamp(cfg, "head")
    else:
        _log("DB đã có: chạy 'alembic upgrade head' để bổ sung cột/bảng còn thiếu.")
        command.upgrade(cfg, "head")


def main() -> None:
    wait_for_db()
    sync_schema()
    _log("Database sẵn sàng.")


if __name__ == "__main__":
    main()
