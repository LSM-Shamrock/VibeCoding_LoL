"""뼈대 애니메이션이 있는 .glb 캐릭터를 게임용 스키닝 데이터(.skin.npz)로 굽는다.

게임 클라이언트는 이 파일을 읽어 GPU 스키닝으로 캐릭터를 움직인다 (game/client/skin.py).
OBJ 는 뼈대를 담을 수 없어서, 정점 + 뼈 가중치 + 동작별 뼈 행렬을 numpy .npz 한 파일로 저장한다.

    정점 좌표는 원본 모델(뼈대를 묶은 기본 자세) 좌표 그대로이고,
    뼈 행렬(동작의 한 프레임마다 하나) 에 "키 맞추기 + 발밑 중앙 정렬" 변환까지 이미 곱해 두었다.
    그래서 게임에서는 행렬을 정점 셰이더에 넘기기만 하면 되고, 결과는 정적 OBJ 모델과 같은 크기·위치가 된다.

이 모듈은 tools/build_champion_models.py 가 불러 쓴다. 직접 실행하지 않는다.
"""
import json
import math
import os

import numpy as np
from PIL import Image

import bake_gltf_pose as bk

MAX_JOINTS = 32            # 셰이더의 뼈 개수 한도 (game/client/gl.py 의 MESH_SKIN_VS 와 같아야 한다)
FPS = 30

# 이름이 이렇게 끝나거나 같으면 반복 재생하는 동작으로 표시해 둔다
LOOP_NAMES = ("Idle", "Idle_B", "Idle_Combat", "Unarmed_Idle", "2H_Melee_Idle", "Jump_Idle", "Blocking", "Spellcasting",
              "Running_A", "Running_B", "Running_C", "Walking_A", "Walking_B", "Walking_C", "Walking_D_Skeletons",
              "Running_Strafe_Left", "Running_Strafe_Right", "1H_Ranged_Aiming", "2H_Ranged_Aiming",
              "Sit_Floor_Idle", "Sit_Chair_Idle", "Lie_Idle")


def _mat_t(t):
    m = np.eye(4)
    m[:3, 3] = t
    return m


def collect_parts(g, rest, hide, custom_parts, attach_bone_for_custom, M_custom_idle):
    """메시를 (재질 묶음별) 정점 배열로 모은다. 뼈 번호는 노드 번호 기준 -> 나중에 재번호.

    반환: groups {키: dict(pos, nrm, uv, joints(노드번호 4개), weights)}  — 모두 풀어헤친(삼각형당 3정점) 배열"""
    nodes = g.j["nodes"]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    skin = g.j["skins"][0]
    skin_joints = skin["joints"]
    skin_set = set(skin_joints)

    def bone_of(ni):
        k = parent.get(ni)
        while k is not None and k not in skin_set:
            k = parent.get(k)
        if k is None:
            raise SystemExit(f"{nodes[ni].get('name')}: 붙일 뼈를 찾을 수 없음")
        return k

    groups = {}

    def add(key, pos, nrm, uv, idx, joints, weights):
        gdict = groups.setdefault(key, {"pos": [], "nrm": [], "uv": [], "j": [], "w": []})
        f = idx
        gdict["pos"].append(pos[f])
        gdict["nrm"].append(nrm[f])
        gdict["uv"].append(uv[f])
        gdict["j"].append(joints[f])
        gdict["w"].append(weights[f])

    for ni, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        mesh = g.j["meshes"][node["mesh"]]
        name = node.get("name") or mesh.get("name", "")
        if any((name == h[1:]) if h.startswith("=") else (h.lower() in name.lower()) for h in hide):
            continue
        for prim in mesh["primitives"]:
            if prim.get("mode", 4) != 4:
                continue
            at = prim["attributes"]
            pos = g.accessor(at["POSITION"]).astype(np.float64)
            nrm = g.accessor(at["NORMAL"]).astype(np.float64) if "NORMAL" in at else np.tile([0, 1.0, 0], (len(pos), 1))
            uv = g.accessor(at["TEXCOORD_0"]).astype(np.float64) if "TEXCOORD_0" in at else np.zeros((len(pos), 2))
            idx = g.accessor(prim["indices"])[:, 0].astype(np.int64) if "indices" in prim else np.arange(len(pos))
            tex, col = bk.material_info(g, prim.get("material"))
            key = ("tex", tex) if tex is not None else ("col", tuple(round(c, 4) for c in col))
            if "skin" in node and "JOINTS_0" in at:
                J = g.accessor(at["JOINTS_0"]).astype(np.int64)
                W = g.accessor(at["WEIGHTS_0"]).astype(np.float64)
                W = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
                nodeJ = np.array(skin_joints)[J]                    # 스킨 안의 번호 -> 노드 번호
                add(key, pos, nrm, uv, idx, nodeJ, W)
            else:
                # 뼈에 붙은 장비/모자/망토: 가장 가까운 조상 뼈에 가중치 1로 붙인다
                b = bone_of(ni)
                M = rest[ni]
                wp = pos @ M[:3, :3].T + M[:3, 3]
                wn = nrm @ M[:3, :3].T
                wn /= np.maximum(np.linalg.norm(wn, axis=1, keepdims=True), 1e-9)
                J = np.zeros((len(pos), 4), dtype=np.int64)
                J[:, 0] = b
                W = np.zeros((len(pos), 4))
                W[:, 0] = 1.0
                add(key, wp, wn, uv, idx, J, W)
    for cp in custom_parts:
        # 코드로 만든 장비(낫): 기본 자세 월드 좌표 -> 뼈 기준 좌표로 되돌려 해당 뼈에 붙인다
        name, wp, wn, uv, idx, (tk, col) = cp
        inv = np.linalg.inv(M_custom_idle)
        bp = wp @ inv[:3, :3].T + inv[:3, 3]
        bn = wn @ inv[:3, :3].T
        bn /= np.maximum(np.linalg.norm(bn, axis=1, keepdims=True), 1e-9)
        J = np.zeros((len(bp), 4), dtype=np.int64)
        J[:, 0] = attach_bone_for_custom
        W = np.zeros((len(bp), 4))
        W[:, 0] = 1.0
        add(("col", tuple(round(c, 4) for c in col)), bp, bn, uv, idx, J, W)
    return groups


def bake_skin(path, hide, clip_names, N, custom_parts=(), custom_bone="handslot.r", inplace_prefixes=("Dodge",),
              images_by_tex=None, tex_files=None):
    """한 모델을 스키닝 데이터로 만든다.

    N: 최종 크기·위치를 맞추는 4x4 변환 (기본 자세 월드 좌표 -> 게임 좌표)
    images_by_tex: {텍스처 번호: 파일 이름} — 같은 번호의 재질은 이 파일을 쓴다
    반환: (arrays dict, meta dict)"""
    g = bk.Gltf(path)
    nodes = g.j["nodes"]
    names = [n.get("name") for n in nodes]
    rest = bk.world_matrices(g, {})
    skin = g.j["skins"][0]
    skin_joints = skin["joints"]
    ibm = g.accessor(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
    ibm_of = {n: ibm[k] for k, n in enumerate(skin_joints)}

    idle_anim = next(a for a in g.j["animations"] if a["name"] == "Idle")
    idle_pose = bk.sample_animation(g, idle_anim, 0.0)
    idle_world = bk.world_matrices(g, idle_pose)
    cb = names.index(custom_bone)
    M_custom_idle = idle_world[cb] @ ibm_of[cb]

    groups = collect_parts(g, rest, hide, custom_parts, cb, M_custom_idle)

    # 실제로 쓰이는 뼈만 추려 0..J-1 로 재번호
    used = set()
    for gd in groups.values():
        J = np.concatenate(gd["j"])
        W = np.concatenate(gd["w"])
        used |= set(np.unique(J[W > 1e-5]).tolist())
    used.add(cb)
    order = sorted(used, key=lambda n: skin_joints.index(n))
    if len(order) > MAX_JOINTS:
        raise SystemExit(f"뼈가 너무 많음: {len(order)} > {MAX_JOINTS}")
    remap = {n: k for k, n in enumerate(order)}

    parts_meta, arrays = [], {}
    for pi, (key, gd) in enumerate(groups.items()):
        pos = np.concatenate(gd["pos"])
        nrm = np.concatenate(gd["nrm"])
        uv = np.concatenate(gd["uv"])
        J = np.concatenate(gd["j"])
        W = np.concatenate(gd["w"])
        # 가중치 0 인 칸은 0번 뼈로 (곱해도 영향 없음), 큰 순서로 정렬은 불필요
        lut = np.zeros(len(nodes) + 1, dtype=np.int64)
        for n, k in remap.items():
            lut[n] = k
        Jr = np.where(W > 1e-5, lut[J], 0)
        arr = np.zeros((len(pos), 11), dtype=np.float32)
        arr[:, 0:3] = pos
        arr[:, 3:6] = nrm
        arr[:, 6:9] = 1.0
        if key[0] == "col":
            arr[:, 6:9] = key[1]
        arr[:, 9] = uv[:, 0]
        arr[:, 10] = 1.0 - uv[:, 1]            # OBJ 와 같은 V 방향 (게임이 이 방향을 기대한다)
        arrays[f"p{pi}_arr"] = arr
        arrays[f"p{pi}_jw"] = np.concatenate([Jr.astype(np.float32), W.astype(np.float32)], axis=1)
        tex = None
        if key[0] == "tex":
            tex = (tex_files or {}).get(key[1])
        parts_meta.append({"tex": tex, "n": int(len(pos))})

    # 동작 샘플링
    anim_by_name = {a["name"]: a for a in g.j["animations"]}
    clips_meta = {}
    hips = names.index("hips")
    for cname in clip_names:
        a = anim_by_name.get(cname)
        if a is None:
            continue
        dur = float(max(g.accessor(s["input"])[:, 0].max() for s in a["samplers"]))
        nframes = max(2, int(round(dur * FPS)) + 1)
        frames = np.zeros((nframes, len(order), 12), dtype=np.float32)
        hip0 = None
        strip = any(cname.startswith(p) for p in inplace_prefixes)
        for k in range(nframes):
            t = min(dur, k / FPS)
            world = bk.world_matrices(g, bk.sample_animation(g, a, t))
            NN = N
            if strip:
                hp = world[hips][:3, 3]
                if hip0 is None:
                    hip0 = hp.copy()
                NN = _mat_t([-(hp[0] - hip0[0]), 0.0, -(hp[2] - hip0[2])]) @ N
            for j, node in enumerate(order):
                M = NN @ world[node] @ ibm_of[node]
                frames[k, j] = M[:3, :4].reshape(-1)
        arrays[f"c_{cname}"] = frames
        clips_meta[cname] = {"frames": nframes, "dur": round(dur, 3), "loop": cname in LOOP_NAMES}

    # 기본 자세에서의 경계 (선택 화면·호버 판정 참고용)
    meta = {"fps": FPS, "joints": len(order), "joint_names": [names[n] for n in order], "parts": parts_meta,
            "clips": clips_meta}
    return arrays, meta


def save_skin(path, arrays, meta):
    np.savez_compressed(path, meta=np.array(json.dumps(meta, ensure_ascii=False)), **arrays)
    return os.path.getsize(path)
