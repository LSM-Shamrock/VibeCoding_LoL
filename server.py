"""전용 서버만 실행 (화면 없음).

    py server.py [포트]

클라이언트의 '서버 열고 시작' 버튼을 쓰면 이 파일을 따로 실행할 필요는 없다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.server.server import run_dedicated  # noqa: E402
from game.shared.constants import DEFAULT_PORT  # noqa: E402

if __name__ == "__main__":
    run_dedicated(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT)
