"""마우스 커서 이미지(PNG) 만들기.

game-icons.net (CC BY 3.0) 의 SVG 로 세 가지 커서를 만듭니다 (출처는 assets/ui/CREDITS.md).
    assets/ui/cursors/default.png   평상시: 건틀릿 손
    assets/ui/cursors/attack.png    공격할 수 있는 대상 위: 칼
    assets/ui/cursors/target.png    대상 지정 스킬 조준 중: 조준경

평상시 손 커서는 Phosphor Icons (MIT, https://phosphoricons.com) 의 hand-pointing 입니다.

사용법 (프로젝트 폴더에서):
    git clone --depth 1 https://github.com/game-icons/icons.git <아무 폴더>/gameicons
    git clone --depth 1 https://github.com/phosphor-icons/core.git <아무 폴더>/phosphor
    pip install cairosvg pillow
    python tools/build_cursors.py --src <아무 폴더>/gameicons --phosphor <아무 폴더>/phosphor

클릭 지점(핫스팟)은 game/client/cursors.py 의 HOTSPOTS 에 있습니다. 모양을 바꾸면 거기도 맞춰 주세요.
"""
import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_icons import ROOT, svg_to_image  # noqa: E402

SIZE = 32
# 이름 -> (출처, 아이콘, 색, 좌우 뒤집기).  출처: "gi" = game-icons (작가/이름),  "ph" = Phosphor (assets/ 아래 경로)
CURSORS = {
    "default": ("ph", "fill/hand-pointing-fill", (246, 248, 255), False),
    "attack": ("gi", "lorc/broadsword", (255, 96, 84), True),
    "target": ("gi", "delapouite/crosshair", (255, 206, 84), False),
}


def load_svg(kind, srcs, rel, size, color):
    if kind == "gi":
        return svg_to_image(os.path.join(srcs["gi"], rel + ".svg"), size, color)
    import cairosvg
    from PIL import Image
    s = open(os.path.join(srcs["ph"], "assets", rel + ".svg"), encoding="utf-8").read()
    s = s.replace("currentColor", "#%02x%02x%02x" % color)
    png = cairosvg.svg2png(bytestring=s.encode("utf-8"), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def make(srcs, kind, rel, color, flip):
    from PIL import Image, ImageFilter
    big = 4
    n = SIZE * big
    glyph = load_svg(kind, srcs, rel, int(n * 0.9), color)
    outline = load_svg(kind, srcs, rel, int(n * 0.9), (14, 16, 24)).filter(ImageFilter.MaxFilter(13))
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    off = (n - glyph.width) // 2
    im.alpha_composite(outline, (off, off))
    im.alpha_composite(glyph, (off, off))
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    return im.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="game-icons/icons 저장소를 받아 둔 폴더")
    ap.add_argument("--phosphor", required=True, help="phosphor-icons/core 저장소를 받아 둔 폴더")
    args = ap.parse_args()
    out = os.path.join(ROOT, "assets", "ui", "cursors")
    os.makedirs(out, exist_ok=True)
    srcs = {"gi": args.src, "ph": args.phosphor}
    for name, (kind, rel, color, flip) in CURSORS.items():
        make(srcs, kind, rel, color, flip).save(os.path.join(out, name + ".png"))
    print("커서를 만들었습니다:", out)


if __name__ == "__main__":
    main()
