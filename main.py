"""칼바람 아레나 클라이언트 실행.

    py main.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description="칼바람 아레나")
    parser.add_argument("--autotest", metavar="DIR", help="자동 진행하며 스크린샷을 DIR 에 저장 (개발용)")
    parser.add_argument("--team-size", type=int, default=3, help="자동 테스트 팀 인원")
    args = parser.parse_args()

    from game.client.app import App
    auto = None
    if args.autotest:
        from game.client.autotest import AutoTest
        auto = AutoTest(args.autotest, args.team_size)
    App(autotest=auto).run()


if __name__ == "__main__":
    main()
