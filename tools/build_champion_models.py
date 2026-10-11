"""KayKit 캐릭터 팩(CC0)으로 챔피언 7명의 3D 모델 파일을 만든다.

assets/models/champions/<챔피언id>/model.obj (+ model.mtl, model_texture.png) 를 새로 쓴다.
게임에는 이미 만들어진 파일이 들어 있으므로, 모델을 바꾸거나 다시 만들고 싶을 때만 실행하면 된다.

필요한 것: numpy, pillow, 그리고 아래 두 팩 (GitHub 에서 받을 수 있는 CC0 무료 팩)
    https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0
    https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Skeletons-1.0

사용법
    py tools/build_champion_models.py <Adventures 폴더> <Skeletons 폴더> [챔피언id ...]

각 모델이 하는 일
  1. glb 안의 Idle 동작 한 장면으로 자세를 굳힌다 (tools/bake_gltf_pose.py)
  2. 한 모델에 한꺼번에 들어 있는 무기·방패 중 챔피언에게 맞는 것만 남긴다
  3. 같은 몸(마법사 등)을 쓰는 챔피언끼리 구분되도록 텍스처 색을 바꾼다
  4. 키를 맞추고 발밑 중앙이 원점이 되도록 옮긴다  → JSON 에서는 "scale": 1.0, "keep_origin": true
"""
import importlib.util
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bk = _load("bake_gltf_pose", os.path.join(HERE, "bake_gltf_pose.py"))
import bake_skin as bs  # noqa: E402

# 챔피언 JSON 의 model.anim 에 적히지 않아도 항상 굽는 기본 동작 (대기·이동·피격·사망·공중·기절·귀환·승리)
DEFAULT_ANIM = {"idle": "Idle", "run": "Running_A", "hit": "Hit_A", "death": "Death_A", "spawn": "Jump_Land",
                "air": "Jump_Idle", "stun": "Hit_B", "recall": "Spellcasting", "win": "Cheer"}

# 팩마다 한 모델 안에 들어 있는 장비(무기·방패 등) 메시 이름 — 쓸 것만 'keep' 으로 남기고 나머지는 뺀다
EQUIP = {
    "1H_Sword_Offhand", "Badge_Shield", "Rectangle_Shield", "Round_Shield", "Spike_Shield", "1H_Sword", "2H_Sword",
    "1H_Axe_Offhand", "Barbarian_Round_Shield", "1H_Axe", "2H_Axe", "Mug",
    "Spellbook", "Spellbook_open", "1H_Wand", "2H_Staff",
    "Knife_Offhand", "1H_Crossbow", "2H_Crossbow", "Knife", "Throwable",
}

# 챔피언별 설정
#   pack/file  원본 모델          keep  남길 장비          hide  뺄 몸 부품(모자·망토 등)
#   height     캐릭터 키(게임 유닛, 모자·투구 포함, 장비 제외)
#   recolor    텍스처 색 바꾸기 규칙 목록 (아래 recolor() 참고)
#   scythe     True 면 코드로 만든 낫을 오른손에 붙인다
CHAMPIONS = {
    "vanguard": dict(pack="adv", file="Knight.glb", keep=["1H_Sword", "Rectangle_Shield"], height=2.1),
    "reaper": dict(pack="skel", file="Skeleton_Rogue.glb", keep=[], height=2.0, scythe=True,
                   recolor=[dict(h=(300, 25), smin=0.2, set_h=268, s_mul=0.85, v_mul=0.78)]),
    "monk": dict(pack="adv", file="Barbarian.glb", keep=[], hide=["Barbarian_Hat", "Barbarian_Cape"], height=2.0,
                 recolor=[dict(h=(170, 250), smin=0.1, set_h=28, s_mul=2.0, s_min=0.75, v_mul=1.35)]),
    "acrobat": dict(pack="adv", file="Rogue.glb", keep=["Knife", "Knife_Offhand"], height=2.0,
                    recolor=[dict(h=(100, 180), smin=0.2, set_h=346, s_mul=1.0)]),
    "hunter": dict(pack="adv", file="Rogue_Hooded.glb", keep=["1H_Crossbow"], height=2.0),
    "cleric": dict(pack="adv", file="Mage.glb", keep=["2H_Staff"], hide=["Mage_Hat"], height=2.0,
                   recolor=[dict(h=(215, 290), smin=0.12, s_mul=0.14, v_mul=0.42, v_add=0.58),
                            dict(h=(291, 345), smin=0.2, set_h=45, s_mul=0.95, v_mul=1.35),
                            dict(h=(60, 175), smin=0.2, set_h=48, s_mul=0.9, v_mul=1.1)]),
    "druid": dict(pack="adv", file="Mage.glb", keep=["1H_Wand"], height=2.2,
                  recolor=[dict(h=(215, 290), smin=0.12, set_h=108, s_mul=0.9, v_mul=0.95),
                           dict(h=(291, 345), smin=0.2, set_h=28, s_mul=0.8, v_mul=0.75)]),
}


# ------------------------------------------------------------------ 색 바꾸기
def _rgb2hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    h = np.zeros(mx.shape)
    m = d > 1e-6
    safe = np.where(m, d, 1.0)
    i = m & (mx == r)
    h[i] = ((g - b)[i] / safe[i]) % 6
    i = m & (mx == g) & (mx != r)
    h[i] = (b - r)[i] / safe[i] + 2
    i = m & (mx == b) & (mx != r) & (mx != g)
    h[i] = (r - g)[i] / safe[i] + 4
    s = np.where(mx > 1e-6, d / np.where(mx > 1e-6, mx, 1.0), 0.0)
    return h / 6.0, s, mx


def _hsv2rgb(h, s, v):
    h6 = (h % 1.0) * 6.0
    i = np.floor(h6).astype(int) % 6
    f = h6 - np.floor(h6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    out = np.zeros(h.shape + (3,))
    for k, (rr, gg, bb) in enumerate([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]):
        m = i == k
        out[m, 0], out[m, 1], out[m, 2] = rr[m], gg[m], bb[m]
    return out


def recolor(img, rules):
    """규칙에 맞는 색상 범위의 픽셀만 바꾼다. 피부·금속처럼 채도가 낮은 색은 smin 으로 보호된다.

    규칙: h=(시작, 끝) 색상 각도(0~360, 시작>끝이면 0도를 가로지름), smin=이 채도 이상만,
          set_h=색상을 이 각도로 / shift_h=각도만큼 이동, s_mul·s_min=채도 배율·최소값, v_mul·v_add=밝기 배율·더하기
    """
    a = np.asarray(img.convert("RGBA"), dtype=np.float64) / 255.0
    h, s, v = _rgb2hsv(a[..., :3])
    h0, s0, v0 = h.copy(), s.copy(), v.copy()
    done = np.zeros(h.shape, dtype=bool)
    for r in rules:
        lo, hi = r["h"]
        deg = h0 * 360.0
        inside = (deg >= lo) & (deg <= hi) if lo <= hi else (deg >= lo) | (deg <= hi)
        m = inside & (s0 >= r.get("smin", 0.15)) & (v0 >= r.get("vmin", 0.0)) & ~done & (a[..., 3] > 0)
        if not m.any():
            continue
        done |= m
        if "set_h" in r:
            h[m] = r["set_h"] / 360.0
        if "shift_h" in r:
            h[m] = (h0[m] + r["shift_h"] / 360.0) % 1.0
        ns = s0[m] * r.get("s_mul", 1.0)
        if "s_min" in r:
            ns = np.maximum(ns, r["s_min"])
        s[m] = np.clip(ns, 0, 1)
        v[m] = np.clip(v0[m] * r.get("v_mul", 1.0) + r.get("v_add", 0.0), 0, 1)
    rgb = _hsv2rgb(h, s, v)
    out = np.concatenate([rgb, a[..., 3:4]], axis=-1)
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")


# ------------------------------------------------------------------ 코드로 만든 낫 (카론)
def scythe_parts(hand, unit):
    """오른손 위치에 세워 든 낫. 손 위치만 쓰고 방향은 월드 기준(기둥은 위로, 날은 앞(+Z)으로).
    unit: 원본 모델 단위 -> 최종 단위 배율의 역수 (최종 단위로 설계한 크기를 원본 단위로 되돌린다)"""
    from game.client import champion_models as cm
    from game.client.geometry import MeshBuilder

    b = MeshBuilder()
    wood, steel, trim = (0.26, 0.2, 0.17), (0.82, 0.8, 0.9), (0.55, 0.38, 0.8)
    cm.bar(b, (0, -0.62, 0), (0, 1.55, 0), 0.07, wood)
    cm.curve(b, [(0, 1.55, 0), (0.08, 1.58, 0.36), (0.06, 1.53, 0.7), (-0.08, 1.45, 0.98), (-0.3, 1.36, 1.15)],
             0.34, 0.014, steel, 0.05, 0.02)
    b.octahedron((0, 1.57, -0.02), 0.07, 0.17, trim)
    b.octahedron((0, -0.64, 0), 0.05, 0.16, trim)
    arr = b.array().astype(np.float64)
    pos = arr[:, 0:3] * unit + hand[:3, 3]
    nrm = arr[:, 3:6]
    col = arr[:, 6:9]
    parts = []
    keys = {}
    for t in range(len(arr) // 3):
        keys.setdefault(tuple(np.round(col[t * 3], 3)), []).append(t)
    for ck, tris in keys.items():
        sel = np.concatenate([np.arange(t * 3, t * 3 + 3) for t in tris])
        parts.append(("Scythe", pos[sel], nrm[sel], np.zeros((len(sel), 2)), np.arange(len(sel)), (None, tuple(ck))))
    return parts


# ------------------------------------------------------------------ 한 명 만들기
def find_chars_dir(root):
    for dp, dn, fn in os.walk(root):
        if dp.replace("\\", "/").endswith("Characters/gltf"):
            return dp
    raise SystemExit(f"Characters/gltf 폴더를 찾을 수 없음: {root}")


def _norm_matrix(s, cx, by0, cz):
    """원본 월드 좌표 -> 게임 좌표 (키 맞추기 + 발밑 중앙 정렬)"""
    N = np.eye(4)
    N[:3, :3] *= s
    N[:3, 3] = -s * np.array([cx, by0, cz])
    return N


def champion_clips(cid):
    """챔피언 JSON 의 model.anim 에서 필요한 동작 이름을 모은다 (기본 동작 포함)."""
    names = list(DEFAULT_ANIM.values())
    try:
        for p in os.listdir(os.path.join(ROOT, "data", "champions")):
            if not p.endswith(".json"):
                continue
            with open(os.path.join(ROOT, "data", "champions", p), encoding="utf-8") as f:
                d = json.load(f)
            if d.get("id") == cid:
                for k, v in (d.get("model", {}).get("anim") or {}).items():
                    for item in (v if isinstance(v, list) else [v]):
                        names.append(item["clip"] if isinstance(item, dict) else item)
    except OSError:
        pass
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def build_skin(cid, cfg, path, hide, N, s, images, outdir):
    """뼈대 애니메이션 데이터(model.skin.npz)를 굽는다."""
    custom = []
    if cfg.get("scythe"):
        hand = bk.bone_world(path, "Idle", 0.0)["handslot.r"]
        custom = scythe_parts(hand, 1.0 / s)
    tex_files = {tex: "model_texture.png" for (gi, tex) in images if gi == 0}
    arrays, meta = bs.bake_skin(path, hide, champion_clips(cid), N, custom_parts=custom, tex_files=tex_files)
    return bs.save_skin(os.path.join(outdir, "model.skin.npz"), arrays, meta)


def build_one(cid, cfg, dirs, outroot):
    path = os.path.join(dirs[cfg["pack"]], cfg["file"])
    keep = set(cfg.get("keep", []))
    hide = ["=" + n for n in (EQUIP - keep)] + ["=" + n for n in cfg.get("hide", [])]
    parts, images = bk.bake(path, "Idle", 0.0, hide)
    body = [p for p in parts if p[0] not in EQUIP]
    allp = np.concatenate([p[1] for p in body])
    by0, by1 = allp[:, 1].min(), allp[:, 1].max()
    s = cfg["height"] / (by1 - by0)
    bodypart = [p for p in body if p[0].endswith("_Body")][0]
    cx = (bodypart[1][:, 0].min() + bodypart[1][:, 0].max()) / 2
    cz = (bodypart[1][:, 2].min() + bodypart[1][:, 2].max()) / 2
    if cfg.get("scythe"):
        hand = bk.bone_world(path, "Idle", 0.0)["handslot.r"]
        parts = parts + scythe_parts(hand, 1.0 / s)
    out = []
    for name, p, n, uv, idx, mat in parts:
        q = (p - np.array([cx, by0, cz])) * s
        out.append((name, q, n, uv, idx, mat))
    if cfg.get("recolor"):
        images = {k: recolor(im, cfg["recolor"]) for k, im in images.items()}
    outdir = os.path.join(outroot, cid)
    bk.write_obj(out, images, outdir, "model")
    skin_size = build_skin(cid, cfg, path, hide, N=_norm_matrix(s, cx, by0, cz), s=s, images=images, outdir=outdir)
    allq = np.concatenate([p[1] for p in out])
    print(f"{cid:9s} {cfg['file']:18s} 키 {allq[:, 1].max():.2f}  가로 {np.ptp(allq[:, 0]):.2f}  깊이 {np.ptp(allq[:, 2]):.2f}"
          f"  (아래쪽 {allq[:, 1].min():+.2f})  스킨 {skin_size / 1024:.0f}KB -> {os.path.relpath(outdir, ROOT)}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    dirs = {"adv": find_chars_dir(sys.argv[1]), "skel": find_chars_dir(sys.argv[2])}
    want = sys.argv[3:] or list(CHAMPIONS)
    outroot = os.path.join(ROOT, "assets", "models", "champions")
    for cid in want:
        build_one(cid, CHAMPIONS[cid], dirs, outroot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
