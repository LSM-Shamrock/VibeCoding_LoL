"""Local static model import; independent of OpenGL so imports can be tested."""
from dataclasses import dataclass
import logging
import numpy as np
import trimesh

from .content import asset_path

log = logging.getLogger(__name__)


@dataclass
class MeshPart:
    vertices: np.ndarray
    normals: np.ndarray
    faces: np.ndarray
    colors: np.ndarray
    uv: np.ndarray | None = None
    image: object = None


def load_model(spec):
    """Bake scene transforms and rotation, center feet, normalize to 2.6 units.

    Static geometry and base-color textures are supported. Skeletal animation,
    skinning, PBR shaders and embedded lights are intentionally separate work.
    """
    path = asset_path(spec["model"])
    if not path.is_file():
        return []
    if path.suffix.lower() not in (".obj", ".glb", ".gltf"):
        raise ValueError("지원하는 모델 형식: GLB, glTF, OBJ")
    scene = trimesh.load_scene(path, process=False, allow_remote=False)
    rotations = np.radians(spec.get("model_rotation", [0, 0, 0]))
    rotate = trimesh.transformations.euler_matrix(*rotations)
    meshes = []
    for node in scene.graph.nodes_geometry:
        transform, geometry = scene.graph[node]
        source = scene.geometry[geometry]
        if not isinstance(source, trimesh.Trimesh) or not len(source.faces):
            continue
        mesh = source.copy()
        mesh.apply_transform(rotate @ transform)
        if "vertex_normals" not in mesh._cache:
            # Avoid an optional SciPy dependency for meshes without normals.
            triangles = mesh.vertices[mesh.faces]
            face_vectors = np.cross(triangles[:,1]-triangles[:,0], triangles[:,2]-triangles[:,0])
            normals = np.zeros_like(mesh.vertices)
            for corner in range(3):
                np.add.at(normals, mesh.faces[:,corner], face_vectors)
            lengths = np.linalg.norm(normals, axis=1)
            normals /= np.maximum(lengths[:,None], 1e-12)
            mesh.vertex_normals = normals
        meshes.append(mesh)
    if not meshes:
        raise ValueError("모델에 삼각형 메시가 없습니다.")
    if sum(len(mesh.faces) for mesh in meshes) > 300_000:
        raise ValueError("모델은 30만 삼각형 이하로 줄여 주세요.")
    bounds = np.array([mesh.bounds for mesh in meshes])
    minimum, maximum = bounds[:, 0].min(axis=0), bounds[:, 1].max(axis=0)
    if not np.isfinite(bounds).all() or maximum[1]-minimum[1] < 0.00001:
        raise ValueError("유효하지 않은 모델 크기입니다. model_rotation을 확인하세요.")
    offset = np.array([(minimum[0]+maximum[0])/2, minimum[1], (minimum[2]+maximum[2])/2])
    scale = 2.6/(maximum[1]-minimum[1])*float(spec.get("model_scale", 1))
    parts = []
    for mesh in meshes:
        uv, texture = None, None
        if mesh.visual.kind == "texture":
            material = mesh.visual.material
            uv = np.asarray(mesh.visual.uv, dtype=np.float32) if mesh.visual.uv is not None else None
            texture = getattr(material, "baseColorTexture", None)
            if texture is None:
                texture = getattr(material, "image", None)
            factor = getattr(material, "baseColorFactor", None)
            if factor is None:
                factor = getattr(material, "diffuse", [255, 255, 255, 255])
            color = np.asarray(factor, dtype=float)[:4]
            if color.max() > 1:
                color /= 255
            colors = np.tile(color, (len(mesh.vertices), 1))
        elif mesh.visual.kind in ("vertex", "face"):
            colors = np.asarray(mesh.visual.vertex_colors, dtype=float)/255
        else:
            colors = np.tile([0.75, 0.82, 0.9, 1], (len(mesh.vertices), 1))
        parts.append(MeshPart(np.asarray((mesh.vertices-offset)*scale, dtype=np.float32),
                              np.asarray(mesh.vertex_normals, dtype=np.float32),
                              np.asarray(mesh.faces, dtype=np.uint32), colors, uv, texture))
    return parts
