"""뼈대(스킨) 가 있는 .glb 캐릭터를 '특정 동작의 한 장면'으로 굳혀서 OBJ + MTL + PNG 로 내보낸다.

게임의 모델 로더는 뼈대 애니메이션을 아직 지원하지 않는다. KayKit 처럼 T자 자세로 저장된 리깅 모델은
그대로 불러오면 팔을 벌린 채 서 있으므로, 모델에 들어 있는 애니메이션(예: Idle)의 한 프레임을 계산해
정지 메시로 구워 둔다. 무기·장비처럼 뼈에 붙어 있는 메시도 같은 자세로 함께 구워진다.

사용법 (numpy, pillow 만 필요)
    py tools/bake_gltf_pose.py 입력.glb 출력폴더 [--name 이름] [--anim Idle] [--time 0.0]
                               [--hide 패턴 ...] [--list]

    --list   모델에 들어 있는 애니메이션 이름과 메시 이름을 보여 준다.
    --hide   이름에 패턴이 들어간 메시를 뺀다 (예: --hide Axe Shield). '=이름' 은 이름이 정확히 같은 것만.
             (KayKit 모델에는 무기·방패 여러 종류가 한꺼번에 들어 있어서 쓸 것만 남기고 나머지를 빼야 한다)
    --extra  뼈에 붙일 장비 .gltf/.glb 를 'handslot.r=파일' 형식으로 추가한다 (예: --extra handslot.r=staff.gltf).

결과: 출력폴더/이름.obj, 이름.mtl, 이름_texture.png  (앞이 +Z, Y 가 위쪽 — 게임 로더 기준)
"""
import argparse
import io
import json
import math
import os
import struct
import sys

import numpy as np
from PIL import Image

_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
_NORM_MAX = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}


class Gltf:
    """glb / gltf 읽기 (필요한 만큼만)."""

    def __init__(self, path):
        self.dir = os.path.dirname(os.path.abspath(path))
        self.bin = None
        raw = open(path, "rb").read()
        if raw[:4] == b"glTF":
            off = 12
            while off < len(raw):
                clen, ctype = struct.unpack("<II", raw[off:off + 8])
                chunk = raw[off + 8:off + 8 + clen]
                off += 8 + clen
                if ctype == 0x4E4F534A:
                    self.j = json.loads(chunk)
                elif ctype == 0x004E4942:
                    self.bin = chunk
        else:
            self.j = json.loads(raw.decode("utf-8"))
        self._bufs = {}
        self._acc = {}

    def buffer(self, i):
        if i not in self._bufs:
            b = self.j["buffers"][i]
            uri = b.get("uri")
            if uri is None:
                self._bufs[i] = self.bin
            elif uri.startswith("data:"):
                import base64
                self._bufs[i] = base64.b64decode(uri.split(",", 1)[1])
            else:
                self._bufs[i] = open(os.path.join(self.dir, uri), "rb").read()
        return self._bufs[i]

    def view_bytes(self, i):
        bv = self.j["bufferViews"][i]
        o = bv.get("byteOffset", 0)
        return self.buffer(bv["buffer"])[o:o + bv["byteLength"]]

    def accessor(self, i):
        """접근자 i 의 배열 (읽기 전용으로 쓸 것 — 같은 배열을 다시 돌려준다)."""
        if i in self._acc:
            return self._acc[i]
        a = self.j["accessors"][i]
        bv = self.j["bufferViews"][a["bufferView"]]
        dt = np.dtype(_CT[a["componentType"]])
        n = _NC[a["type"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride") or dt.itemsize * n
        buf = self.buffer(bv["buffer"])
        arr = np.ndarray((a["count"], n), dtype=dt, buffer=buf, offset=off, strides=(stride, dt.itemsize))
        if a.get("normalized"):
            out = arr.astype(np.float64) / _NORM_MAX[a["componentType"]]
        else:
            out = arr.copy()
        self._acc[i] = out
        return out

    def image(self, i):
        im = self.j["images"][i]
        if "bufferView" in im:
            data = self.view_bytes(im["bufferView"])
        elif im["uri"].startswith("data:"):
            import base64
            data = base64.b64decode(im["uri"].split(",", 1)[1])
        else:
            data = open(os.path.join(self.dir, im["uri"]), "rb").read()
        return Image.open(io.BytesIO(data)).convert("RGBA")


# ------------------------------------------------------------------ 변환 도우미
def quat_matrix(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def trs_matrix(t, q, s):
    m = np.eye(4)
    m[:3, :3] = quat_matrix(q) * np.array(s)[None, :]
    m[:3, 3] = t
    return m


def slerp(a, b, t):
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    d = float(np.dot(a, b))
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        r = a + t * (b - a)
        return r / np.linalg.norm(r)
    th = math.acos(max(-1.0, min(1.0, d)))
    return (math.sin((1 - t) * th) * a + math.sin(t * th) * b) / math.sin(th)


def node_local(node, override):
    if "matrix" in node and not override:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    t = override.get("translation", node.get("translation", [0, 0, 0]))
    q = override.get("rotation", node.get("rotation", [0, 0, 0, 1]))
    s = override.get("scale", node.get("scale", [1, 1, 1]))
    return trs_matrix(t, q, s)


def sample_animation(g, anim, time):
    """애니메이션의 time 초 시점 값: {노드번호: {경로: 값}}"""
    out = {}
    for ch in anim["channels"]:
        tgt = ch["target"]
        if "node" not in tgt:
            continue
        smp = anim["samplers"][ch["sampler"]]
        ts = g.accessor(smp["input"])[:, 0]
        vs = g.accessor(smp["output"])
        mode = smp.get("interpolation", "LINEAR")
        if mode == "CUBICSPLINE":
            vs = vs[1::3]
        t = min(max(time, ts[0]), ts[-1])
        k = int(np.searchsorted(ts, t, side="right")) - 1
        k = max(0, min(len(ts) - 1, k))
        if k >= len(ts) - 1 or mode == "STEP":
            val = vs[k]
        else:
            f = (t - ts[k]) / max(1e-9, ts[k + 1] - ts[k])
            val = slerp(vs[k], vs[k + 1], f) if tgt["path"] == "rotation" else vs[k] * (1 - f) + vs[k + 1] * f
        out.setdefault(tgt["node"], {})[tgt["path"]] = [float(v) for v in val]
    return out


def world_matrices(g, pose):
    nodes = g.j["nodes"]
    world = [None] * len(nodes)
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i

    def get(i):
        if world[i] is None:
            local = node_local(nodes[i], pose.get(i, {}))
            world[i] = (get(parent[i]) @ local) if i in parent else local
        return world[i]

    for i in range(len(nodes)):
        get(i)
    return world


# ------------------------------------------------------------------ 메시 굽기
def material_info(g, mi):
    """재질 -> (텍스처 이미지 번호 또는 None, 기본 색)"""
    if mi is None:
        return None, (0.8, 0.8, 0.8)
    m = g.j["materials"][mi]
    pbr = m.get("pbrMetallicRoughness", {})
    tex = None
    if "baseColorTexture" in pbr:
        tex = g.j["textures"][pbr["baseColorTexture"]["index"]]["source"]
    col = pbr.get("baseColorFactor", [1, 1, 1, 1])[:3]
    if tex is None and not pbr.get("baseColorFactor") and m.get("emissiveFactor"):
        col = m["emissiveFactor"]          # 눈처럼 빛나는 재질은 방출 색을 그대로 쓴다
    return tex, tuple(float(c) for c in col)


def bake_nodes(g, world, hide=(), attach=None):
    """메시 노드를 월드 공간으로 변환. 반환: [(이름, pos, nrm, uv, idx, 재질키)]"""
    nodes = g.j["nodes"]
    out = []
    for ni, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        mesh = g.j["meshes"][node["mesh"]]
        name = node.get("name") or mesh.get("name", "")
        if any((name == h[1:]) if h.startswith("=") else (h.lower() in name.lower()) for h in hide):
            continue
        skin = g.j["skins"][node["skin"]] if "skin" in node else None
        if skin is not None:
            ibm = g.accessor(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
            jm = np.stack([world[j] @ ibm[k] for k, j in enumerate(skin["joints"])])
        for prim in mesh["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            at = prim["attributes"]
            pos = g.accessor(at["POSITION"]).astype(np.float64)
            nrm = g.accessor(at["NORMAL"]).astype(np.float64) if "NORMAL" in at else np.tile([0, 1.0, 0], (len(pos), 1))
            uv = g.accessor(at["TEXCOORD_0"]).astype(np.float64) if "TEXCOORD_0" in at else np.zeros((len(pos), 2))
            idx = g.accessor(prim["indices"])[:, 0].astype(np.int64) if "indices" in prim else np.arange(len(pos))
            if skin is not None and "JOINTS_0" in at:
                J = g.accessor(at["JOINTS_0"]).astype(np.int64)
                W = g.accessor(at["WEIGHTS_0"]).astype(np.float64)
                W = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
                M = np.einsum("ni,nijk->njk", W, jm[J])
            else:
                M = np.broadcast_to(world[ni] if attach is None else attach @ world[ni], (len(pos), 4, 4))
            p4 = np.concatenate([pos, np.ones((len(pos), 1))], axis=1)
            wp = np.einsum("njk,nk->nj", M, p4)[:, :3]
            wn = np.einsum("njk,nk->nj", M[:, :3, :3], nrm)
            wn /= np.maximum(np.linalg.norm(wn, axis=1, keepdims=True), 1e-9)
            out.append((name, wp, wn, uv, idx, prim.get("material")))
    return out


def find_node(g, name):
    for i, n in enumerate(g.j["nodes"]):
        if n.get("name") == name:
            return i
    raise SystemExit(f"뼈/노드를 찾을 수 없음: {name}")


def bake(path, anim_name="Idle", time=0.0, hide=(), extras=()):
    """반환: (parts, images)  parts=[(pos,nrm,uv,idx,(이미지키,색))], images={키: PIL}"""
    g = Gltf(path)
    pose = {}
    if anim_name and g.j.get("animations"):
        match = [a for a in g.j["animations"] if a.get("name") == anim_name]
        if not match:
            raise SystemExit(f"애니메이션 '{anim_name}' 없음. --list 로 확인하세요.")
        pose = sample_animation(g, match[0], time)
    world = world_matrices(g, pose)
    items = [(g, bake_nodes(g, world, hide))]
    for slot, fpath in extras:
        eg = Gltf(fpath)
        bone = world[find_node(g, slot)]
        ew = world_matrices(eg, {})
        items.append((eg, bake_nodes(eg, ew, hide, attach=bone)))
    parts, images = [], {}
    for gi, (gg, baked) in enumerate(items):
        for name, p, n, uv, idx, mat in baked:
            tex, col = material_info(gg, mat)
            key = None
            if tex is not None:
                key = (gi, tex)
                if key not in images:
                    images[key] = gg.image(tex)
            parts.append((name, p, n, uv, idx, (key, col)))
    return parts, images


def bone_world(path, anim_name="Idle", time=0.0):
    """같은 자세에서의 {뼈 이름: 4x4 월드 행렬}. 뼈에 코드로 만든 장비를 붙일 때 쓴다."""
    g = Gltf(path)
    pose = {}
    if anim_name and g.j.get("animations"):
        match = [a for a in g.j["animations"] if a.get("name") == anim_name]
        if match:
            pose = sample_animation(g, match[0], time)
    world = world_matrices(g, pose)
    return {n.get("name"): world[i] for i, n in enumerate(g.j["nodes"]) if n.get("name")}


def write_obj(parts, images, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    img_files, mats = {}, {}
    for key, im in images.items():
        fname = f"{name}_texture.png" if len(img_files) == 0 else f"{name}_texture{len(img_files) + 1}.png"
        im.save(os.path.join(outdir, fname))
        img_files[key] = fname
    lines = [f"# baked by tools/bake_gltf_pose.py", f"mtllib {name}.mtl"]
    voff = 0
    for pname, p, n, uv, idx, (key, col) in parts:
        mname = ("tex_" + img_files[key].rsplit(".", 1)[0]) if key is not None else "col_%02x%02x%02x" % tuple(int(c * 255) for c in col)
        mats[mname] = (img_files.get(key), col if key is None else (1.0, 1.0, 1.0))
        lines.append(f"o {pname}")
        lines += ["v %.5f %.5f %.5f" % tuple(v) for v in p]
        lines += ["vt %.5f %.5f" % (u, 1.0 - v) for u, v in uv]
        lines += ["vn %.4f %.4f %.4f" % tuple(v) for v in n]
        lines.append(f"usemtl {mname}")
        tri = idx.reshape(-1, 3) + 1 + voff
        for a, b, c in tri:
            lines.append(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}")
        voff += len(p)
    with open(os.path.join(outdir, name + ".obj"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    ml = []
    for mname, (tex, col) in mats.items():
        ml += [f"newmtl {mname}", "Ka 1.0 1.0 1.0", "Kd %.4f %.4f %.4f" % tuple(col), "Ks 0.0 0.0 0.0", "d 1.0", "illum 1"]
        if tex:
            ml.append(f"map_Kd {tex}")
        ml.append("")
    with open(os.path.join(outdir, name + ".mtl"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(ml))
    return len(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("glb")
    ap.add_argument("outdir", nargs="?")
    ap.add_argument("--name", default="model")
    ap.add_argument("--anim", default="Idle")
    ap.add_argument("--time", type=float, default=0.0)
    ap.add_argument("--hide", nargs="*", default=[])
    ap.add_argument("--extra", nargs="*", default=[], help="뼈이름=장비파일")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        g = Gltf(a.glb)
        print("애니메이션:", ", ".join(x.get("name", "?") for x in g.j.get("animations", [])))
        print("메시:", ", ".join((n.get("name") or "?") for n in g.j["nodes"] if "mesh" in n))
        return
    if not a.outdir:
        ap.error("출력폴더가 필요합니다")
    extras = [tuple(e.split("=", 1)) for e in a.extra]
    parts, images = bake(a.glb, a.anim, a.time, a.hide, extras)
    write_obj(parts, images, a.outdir, a.name)
    print(f"저장: {os.path.join(a.outdir, a.name)}.obj ({len(parts)} 조각)")


if __name__ == "__main__":
    sys.exit(main())
