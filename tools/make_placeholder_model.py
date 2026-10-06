"""플레이스홀더 챔피언 모델(OBJ+MTL)을 생성한다.

실행: py tools/make_placeholder_model.py
결과: assets/models/champions/frost_archer/model.obj, model.mtl
진짜 3D 모델을 구하면 이 파일들을 바꾸거나 data/champions/frost_archer.json 의 model.file 을 바꾸면 된다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.client.geometry import export_obj  # noqa: E402
from game.client.procedural import build_frost_archer  # noqa: E402
from game.shared.constants import ASSET_DIR  # noqa: E402


def main():
    out_dir = os.path.join(ASSET_DIR, "models", "champions", "frost_archer")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "model.obj")
    builder = build_frost_archer()
    export_obj(builder, path, "model.mtl")
    print("생성:", path, f"({len(builder.verts) // 3} 삼각형)")


if __name__ == "__main__":
    main()
