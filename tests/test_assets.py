from pathlib import Path
import tempfile
import unittest

import numpy as np
import trimesh
from PIL import Image

from frostbridge.assets import load_model
from frostbridge.content import ROOT, asset_path


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/"assets"/"models")
        self.directory=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def spec(self,path):
        return dict(model=path.relative_to(ROOT).as_posix(),model_scale=1,model_rotation=[0,0,0])

    def test_obj_normalizes_and_places_feet_on_ground(self):
        path=self.directory/"hero.obj"
        trimesh.creation.box(extents=[2,4,1]).export(path,include_normals=False)
        parts=load_model(self.spec(path))
        vertices=np.concatenate([p.vertices for p in parts])
        self.assertAlmostEqual(float(vertices[:,1].min()),0)
        self.assertAlmostEqual(float(vertices[:,1].max()),2.6,places=5)
        self.assertEqual(sum(len(p.faces) for p in parts),12)

    def test_glb_preserves_scene_transforms_and_texture(self):
        mesh=trimesh.creation.box()
        material=trimesh.visual.material.PBRMaterial(baseColorTexture=Image.new("RGBA",(4,4),(20,200,100,255)))
        mesh.visual=trimesh.visual.TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),material=material)
        scene=trimesh.Scene()
        scene.add_geometry(mesh,node_name="left")
        matrix=np.eye(4)
        matrix[0,3]=3
        scene.add_geometry(mesh,node_name="right",transform=matrix)
        path=self.directory/"hero.glb"
        scene.export(path,include_normals=False)
        parts=load_model(self.spec(path))
        self.assertEqual(len(parts),2)
        vertices=np.concatenate([p.vertices for p in parts])
        self.assertGreater(float(np.ptp(vertices[:,0])),9)
        self.assertTrue(all(p.image is not None for p in parts))
        self.assertTrue(all(p.uv is not None for p in parts))

    def test_missing_file_has_procedural_fallback(self):
        self.assertEqual(load_model(dict(model="assets/models/missing.glb")),[])

    def test_asset_path_cannot_escape_assets(self):
        with self.assertRaises(ValueError):
            asset_path("data/champions.json")

    def test_corrupt_model_reports_failure(self):
        path=self.directory/"bad.glb"
        path.write_bytes(b"not a model")
        with self.assertRaises(Exception):
            load_model(self.spec(path))


if __name__=="__main__":
    unittest.main()
