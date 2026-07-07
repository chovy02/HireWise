"""
REPL test AI Agent (kiến trúc B) — chạy thẳng terminal, KHÔNG cần login/frontend.

Cách chạy (từ thư mục src/backend, đã set sẵn các biến môi trường DATABASE_URL,
GROQ_API_KEY như khi chạy backend):

    python test_agent.py

Gõ câu hỏi tiếng Việt, gõ 'quit' để thoát. Thêm cờ --debug để xem agent đã gọi
tool nào với tham số gì.

    python test_agent.py --debug
"""

import json
import sys

from app.database import SessionLocal
from app import models
from app.services.ai_agent.agent import run_agent


def main():
    debug = "--debug" in sys.argv
    db = SessionLocal()

    # Lấy 1 user thật làm "HR đang đăng nhập" (cần cho tool create_jd). Ưu tiên admin.
    user = (
        db.query(models.User)
        .order_by(models.User.role.desc())  # 'hr_staff' < 'admin' theo alphabet? -> lấy tạm user đầu
        .first()
    )
    if user is None:
        print("!! Chưa có user nào trong DB. Hãy chạy backend 1 lần để seed admin, hoặc đăng ký 1 tài khoản.")
        return

    print(f"== HireWise Agent REPL == (đăng nhập giả lập: {user.email} / {user.role})")
    print("Gõ câu hỏi, 'quit' để thoát.\n")

    history: list[dict] = []
    try:
        while True:
            try:
                msg = input("HR > ").strip()
            except EOFError:
                break
            if not msg:
                continue
            if msg.lower() in {"quit", "exit", "thoat"}:
                break

            out = run_agent(db, msg, user_id=user.id, history=history)

            if debug and out.get("steps"):
                for s in out["steps"]:
                    print(f"   🔧 {s['tool']}({json.dumps(s['args'], ensure_ascii=False)})")
                    print(f"      -> {json.dumps(s['result'], ensure_ascii=False, default=str)[:300]}")

            if out.get("tool_calls"):
                print(f"   [tools: {', '.join(out['tool_calls'])}]")
            print(f"AI > {out['reply']}\n")

            # Nối phiên để hỏi tiếp có ngữ cảnh.
            history.append({"role": "user", "content": msg})
            history.append({"role": "assistant", "content": out["reply"]})
    finally:
        db.close()
        print("Bye.")


if __name__ == "__main__":
    main()
