"""코드로 만든 챔피언 모델을 OBJ+MTL 로 내보낸다 (블렌더 등에서 다듬거나 참고용으로 쓰기).

실행: py tools/export_champion_model.py [챔피언 id ...]     (생략하면 전부)
결과: assets/models/champions/<id>/procedural.obj, procedural.mtl   (model.obj 는 건드리지 않는다)
내보낸 모델을 쓰려면 data/champions/*.json 의 "model" 을 {"file": "assets/models/champions/<id>/procedural.obj", "scale": 1.0, "keep_origin": true}
처럼 바꾸면 된다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.client.champion_models import CHAMPION_BUILDERS  # noqa: E402
from game.client.geometry import export_obj  # noqa: E402
from game.shared.constants import ASSET_DIR  # noqa: E402


def main():
    ids = sys.argv[1:] or list(CHAMPION_BUILDERS)
    for cid in ids:
        if cid not in CHAMPION_BUILDERS:
            print("없는 챔피언 id:", cid, "(가능:", ", ".join(CHAMPION_BUILDERS), ")")
            continue
        out_dir = os.path.join(ASSET_DIR, "models", "champions", cid)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "procedural.obj")
        builder = CHAMPION_BUILDERS[cid]()
        export_obj(builder, path, "procedural.mtl")
        print("생성:", path, f"({len(builder.verts) // 3} 삼각형)")


if __name__ == "__main__":
    main()
