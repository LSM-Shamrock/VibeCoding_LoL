"""Optional real OpenGL + imported texture + battle HUD integration check.

Run from the project root: python -m tests.render_check
"""
from pathlib import Path
import argparse
import tempfile
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pygame
import trimesh
from OpenGL.GL import glGetError, GL_NO_ERROR, glReadPixels, GL_RGB, GL_UNSIGNED_BYTE

from frostbridge.app import App
from frostbridge.content import CHAMPIONS, ROOT
from frostbridge.simulation import World


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--fullscreen",action="store_true")
    parser.add_argument("--wide",action="store_true",help="Check dimming outside the 16:9 UI")
    args=parser.parse_args()
    original_mage=CHAMPIONS["mage"]["model"]
    original_warden=CHAMPIONS["warden"]["model"]
    with tempfile.TemporaryDirectory(dir=ROOT/"assets"/"models") as temporary:
        directory=Path(temporary)
        texture=Image.new("RGBA",(4,4),(105,45,200,255))
        for x in range(4):
            for y in range(4):
                if (x+y)%2:
                    texture.putpixel((x,y),(90,230,220,255))
        material=trimesh.visual.material.PBRMaterial(baseColorTexture=texture)
        mesh=trimesh.creation.box(extents=[1,3,1])
        mesh.visual=trimesh.visual.TextureVisuals(uv=(mesh.vertices[:,[0,1]]+2)/4,material=material)
        mesh.vertex_normals=trimesh.geometry.weighted_vertex_normals(len(mesh.vertices),mesh.faces,mesh.face_normals,mesh.face_angles,use_loop=True)
        path=directory/"textured.glb"
        mesh.export(path)
        CHAMPIONS["mage"]["model"]=path.relative_to(ROOT).as_posix()
        CHAMPIONS["warden"]["model"]="assets/models/example_crystal.obj"
        app=None
        try:
            app=App(hidden=not args.fullscreen,size=(1600,720) if args.wide else (1280,720))
            if args.fullscreen:
                assert not pygame.display.is_fullscreen(),"Lobby must start windowed"
                windowed_size=app.renderer.size
                app.renderer.set_game_mode(True)
                assert pygame.display.is_fullscreen()
                assert app.renderer.size==pygame.display.get_desktop_sizes()[0]
            app.client=SimpleNamespace(id="0",close=lambda:None)
            players=[dict(id=str(i),name=f"Hero {i}",team=i//5,champion=list(CHAMPIONS)[i%6],bot=True) for i in range(10)]
            world=World(players)
            # Compile both imported models while every hero is alive.
            app.renderer.draw_world(world.snapshot(),None,1/60)
            for _ in range(1350):
                world.update(1/30)
            snapshot=world.snapshot()
            hero=next(u for u in snapshot["units"] if u["id"]=="0")
            room={"host":"0"}
            output=ROOT/"artifacts"
            output.mkdir(exist_ok=True)
            app.renderer.follow=False
            app.renderer.camera=[0,0]
            for name in ("battle","shop","scoreboard","menu","victory"):
                app.ui.begin([], (0,0), transparent=True)
                app.shop=name=="shop"
                app.scoreboard=name=="scoreboard"
                app.menu=name=="menu"
                if name=="victory":
                    snapshot["winner"]=0
                app.renderer.draw_world(snapshot,hero,1/60)
                width,height=app.renderer.size
                probes=[(2,2),(width-3,2),(2,height-3),(width-3,height-3)]
                before=[np.frombuffer(glReadPixels(x,y,1,1,GL_RGB,GL_UNSIGNED_BYTE),dtype=np.uint8).astype(float) for x,y in probes] if name=="menu" else []
                app.hud(snapshot,hero,room)
                app.renderer.overlay(app.ui.surface,modal_layers=app.ui.modal_layers)
                if name=="menu":
                    for (x,y),pixel in zip(probes,before):
                        actual=np.frombuffer(glReadPixels(x,y,1,1,GL_RGB,GL_UNSIGNED_BYTE),dtype=np.uint8).astype(float)
                        expected=pixel*(60/255)+np.array([1,6,12])*(195/255)
                        assert np.max(np.abs(actual-expected))<4,"Modal dimming did not cover the entire display"
                app.renderer.screenshot(output/f"{name}.png")
                pygame.display.flip()
            assert "mage" in app.renderer.model_lists,"GLB was not rendered"
            assert "warden" in app.renderer.model_lists,"OBJ was not rendered"
            assert app.renderer.textures,"Base color texture was not uploaded"
            assert not app.renderer.asset_errors,app.renderer.asset_errors
            assert glGetError()==GL_NO_ERROR,"OpenGL reported an error"
            for x,z in [(0,0),(-20,3),(15,-4)]:
                ground=app.renderer.ground(app.renderer.project(x,0,z))
                assert np.linalg.norm(np.array(ground)-[x,z])<.001,"Picking projection mismatch"
            if args.fullscreen:
                for _ in range(2):
                    app.renderer.set_game_mode(False)
                    assert not pygame.display.is_fullscreen(),"Lobby must restore windowed mode"
                    assert app.renderer.size==windowed_size,"Window size was not restored"
                    app.renderer.draw_world(snapshot,hero,1/60)
                    app.renderer.overlay(app.ui.surface)
                    pygame.display.flip()
                    app.renderer.set_game_mode(True)
                    app.renderer.draw_world(snapshot,hero,1/60)
                    assert glGetError()==GL_NO_ERROR,"GL context lost during mode switch"
                app.renderer.set_game_mode(False)
                print("MODE PASS: windowed lobby -> fullscreen game -> restored window (repeated)")
            print("RENDER PASS: textured GLB, OBJ, battle, shop, scoreboard, victory, ground picking")
        finally:
            if app:
                app.close()
            CHAMPIONS["mage"]["model"]=original_mage
            CHAMPIONS["warden"]["model"]=original_warden


if __name__=="__main__":
    main()
