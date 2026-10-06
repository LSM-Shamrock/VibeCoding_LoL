"""OpenGL 2.1 compatibility renderer, with a Pygame HUD texture."""
import logging
import math
import random
import pygame
import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import gluLookAt, gluProject, gluUnProject

from .assets import load_model
from .content import CHAMPIONS, MAP_X, MAP_Z
from .display import UILayout, CAMERA_OFFSET, UI_SIZE

TEAM = [(0.22, 0.74, 0.95), (1.0, 0.35, 0.46)]


def color(rgb):
    glColor3f(*rgb)


def cube(x, y, z, sx, sy, sz, tint):
    glPushMatrix()
    glTranslatef(x, y, z)
    glScalef(sx, sy, sz)
    color(tint)
    glBegin(GL_QUADS)
    for normal, vertices in [
        ((0, 1, 0), [(-.5,.5,-.5),(-.5,.5,.5),(.5,.5,.5),(.5,.5,-.5)]),
        ((0,-1,0), [(-.5,-.5,-.5),(.5,-.5,-.5),(.5,-.5,.5),(-.5,-.5,.5)]),
        ((0,0,1), [(-.5,-.5,.5),(.5,-.5,.5),(.5,.5,.5),(-.5,.5,.5)]),
        ((0,0,-1), [(-.5,-.5,-.5),(-.5,.5,-.5),(.5,.5,-.5),(.5,-.5,-.5)]),
        ((1,0,0), [(.5,-.5,-.5),(.5,.5,-.5),(.5,.5,.5),(.5,-.5,.5)]),
        ((-1,0,0), [(-.5,-.5,-.5),(-.5,-.5,.5),(-.5,.5,.5),(-.5,.5,-.5)])]:
        glNormal3f(*normal)
        for vertex in vertices:
            glVertex3f(*vertex)
    glEnd()
    glPopMatrix()


def crystal(x, y, z, radius, height, tint):
    color(tint)
    glBegin(GL_TRIANGLES)
    for i in range(6):
        a, b = i*math.tau/6, (i+1)*math.tau/6
        p = (x+math.cos(a)*radius, y, z+math.sin(a)*radius)
        q = (x+math.cos(b)*radius, y, z+math.sin(b)*radius)
        glNormal3f(math.cos((a+b)/2)*.8, .5, math.sin((a+b)/2)*.8)
        glVertex3f(*p)
        glVertex3f(x, y+height, z)
        glVertex3f(*q)
        glNormal3f(math.cos((a+b)/2)*.8, -.5, math.sin((a+b)/2)*.8)
        glVertex3f(*q)
        glVertex3f(x, y-height*.35, z)
        glVertex3f(*p)
    glEnd()


def ring(x, z, radius, tint, y=0.07, width=2):
    glDisable(GL_LIGHTING)
    color(tint)
    glLineWidth(width)
    glBegin(GL_LINE_LOOP)
    for i in range(48):
        angle = i*math.tau/48
        glVertex3f(x+math.cos(angle)*radius, y, z+math.sin(angle)*radius)
    glEnd()
    glEnable(GL_LIGHTING)


class Renderer:
    def __init__(self, size=UI_SIZE, hidden=False):
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 2)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 1)
        pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        if hidden:
            flags |= pygame.HIDDEN
        pygame.display.set_mode(size, flags)
        pygame.display.set_caption("FROSTBRIDGE · 서리 다리")
        self.window = pygame.Window.from_display_module()
        self.hidden = hidden
        self.fullscreen = False
        self.windowed_size = size
        self.windowed_position = self.window.position
        self.size = pygame.display.get_window_size()
        self.camera = [-38.0, 0.0]
        self.zoom = 21.5
        self.follow = False
        self.positions = {}
        self.model_lists = {}
        self.hero_lists = {}
        self.textures = []
        self.asset_errors = []
        self.models_attempted = set()
        self.hud_texture = glGenTextures(1)
        self.hud_size = None
        self.view = self.projection = self.viewport = None
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_NORMALIZE)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.8, 0.88, 1.0, 1))
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, (0.4, 0.47, 0.56, 1))
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self.map_list = glGenLists(1)
        glNewList(self.map_list, GL_COMPILE)
        self.build_map()
        glEndList()
        for key, spec in CHAMPIONS.items():
            display_list = glGenLists(1)
            glNewList(display_list, GL_COMPILE)
            self.build_hero(spec)
            glEndList()
            self.hero_lists[key] = display_list

    def set_game_mode(self, in_game):
        """Switch the existing SDL window without recreating its GL context."""
        if self.hidden or self.fullscreen == in_game:
            return
        if in_game:
            self.windowed_size = self.window.size
            self.windowed_position = self.window.position
            self.window.set_fullscreen(desktop=True)
        else:
            self.window.set_windowed()
            self.window.size = self.windowed_size
            self.window.position = self.windowed_position
        self.fullscreen = in_game
        self.size = pygame.display.get_window_size()
        self.view = self.projection = self.viewport = None

    def load_champion(self, key):
        if key in self.models_attempted:
            return
        self.models_attempted.add(key)
        try:
            parts = load_model(CHAMPIONS[key])
            if not parts:
                return
            textured = []
            for part in parts:
                texture = None
                if part.image is not None and part.uv is not None:
                    texture = glGenTextures(1)
                    self.textures.append(texture)
                    glBindTexture(GL_TEXTURE_2D, texture)
                    bitmap = part.image.convert("RGBA")
                    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, bitmap.width, bitmap.height,
                                 0, GL_RGBA, GL_UNSIGNED_BYTE, bitmap.tobytes())
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                textured.append((part, texture))
            display_list = glGenLists(1)
            glNewList(display_list, GL_COMPILE)
            for part, texture in textured:
                if texture:
                    glEnable(GL_TEXTURE_2D)
                    glBindTexture(GL_TEXTURE_2D, texture)
                else:
                    glDisable(GL_TEXTURE_2D)
                glBegin(GL_TRIANGLES)
                for face in part.faces:
                    for index in face:
                        glColor4fv(part.colors[index])
                        glNormal3fv(part.normals[index])
                        if texture:
                            glTexCoord2f(float(part.uv[index, 0]), 1-float(part.uv[index, 1]))
                        glVertex3fv(part.vertices[index])
                glEnd()
            glDisable(GL_TEXTURE_2D)
            glEndList()
            self.model_lists[key] = display_list
        except Exception as error:
            logging.getLogger(__name__).warning("Model %s: %s", key, error)
            self.asset_errors.append(f"{CHAMPIONS[key]['name']}: 모델을 읽지 못해 기본 모델 사용")

    @staticmethod
    def build_map():
        rng = random.Random(44)
        cube(0, -1.8, 0, 126, 3.5, 19.5, (.14, .20, .27))
        for x in range(-60, 61, 4):
            for z in range(-8, 9, 4):
                shade = rng.uniform(0.0, 0.05)
                tint = (.29+shade, .39+shade, .46+shade)
                cube(x, -.12, z, 3.94, .25, 3.94, tint)
            for side in (-1, 1):
                cube(x, .12, side*9.2, 4, .45, 1.3, (.71, .84, .88))
                if x % 8 == 0:
                    cube(x, .8, side*9.1, 1.1, 1.8, 1.1, (.21, .3, .37))
                    crystal(x, 1.75, side*9.1, .48, 1.1, (.37, .8, .91))
                    cube(x, -4.6, side*6, 2.4, 4, 3, (.12, .2, .27))
        for x in range(-56, 57, 8):
            cube(x, .03, 0, 2.2, .035, .07, (.63, .69, .65))
        for team in (0, 1):
            x = -55 if team == 0 else 55
            ring(x, 0, 4.4, TEAM[team], width=3)
            ring(x, 0, 3.9, TEAM[team])
        for _ in range(90):
            x = rng.uniform(-67, 67)
            z = rng.choice((-1, 1))*rng.uniform(14, 45)
            crystal(x, rng.uniform(-12, -5), z, rng.uniform(1, 3), rng.uniform(3, 9), (.16, .27, .36))

    @staticmethod
    def build_hero(spec):
        tint = tuple(channel/255 for channel in spec["color"])
        dark = tuple(channel*.38 for channel in tint)
        key = spec["id"]
        width = 1.15 if key == "warden" else .8
        cube(-.25, .4, 0, .32, .8, .4, dark)
        cube(.25, .4, 0, .32, .8, .4, dark)
        cube(0, 1.2, 0, width, 1.1, .58, tint)
        cube(0, 2.05, 0, .62, .63, .6, (.75, .79, .8))
        cube(0, 2.14, .32, .46, .12, .06, tint)
        cube(0, 1.18, -.4, width*1.12, 1.5, .12, dark)
        if key == "warden":
            cube(-.83, 1.15, .22, .6, 1.4, .25, (.3,.55,.65))
            crystal(-.83, 1.2, .42, .25, .6, tint)
            cube(.75, 1, .3, .2, 1.7, .2, (.74,.82,.89))
        elif key in ("mage", "healer"):
            cube(.75, 1.1, .1, .12, 2.2, .12, (.42,.36,.29))
            crystal(.75, 2.4, .1, .35, .65, tint)
            crystal(0, 2.4, 0, .4, .5, dark)
        elif key == "ranger":
            cube(.7, 1.15, .3, .1, 1.7, .1, (.71,.59,.32))
            cube(.7, 1.15, .7, .08, 1.2, .08, tint)
        else:
            cube(.7, 1.2, .45, .17, 1.8, .25, (.75,.84,.9))
            if key == "shade":
                cube(-.7, 1.2, .45, .17, 1.5, .25, tint)

    def setup_world(self):
        width, height = self.size
        glViewport(0, 0, width, height)
        glClearColor(.025, .055, .09, 1)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = width/height
        glOrtho(-self.zoom*aspect, self.zoom*aspect, -self.zoom, self.zoom, 1, 220)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        x, z = self.camera
        ex, ey, ez = CAMERA_OFFSET
        gluLookAt(x+ex, ey, z+ez, x, 0, z, 0, 1, 0)
        glLightfv(GL_LIGHT0, GL_POSITION, (-25, 45, 20, 0))
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        self.view = glGetDoublev(GL_MODELVIEW_MATRIX)
        self.projection = glGetDoublev(GL_PROJECTION_MATRIX)
        self.viewport = glGetIntegerv(GL_VIEWPORT)

    def project(self, x, y, z):
        if self.view is None:
            return -100, -100
        sx, sy, _ = gluProject(x, y, z, self.view, self.projection, self.viewport)
        return self.layout.to_ui((sx, self.size[1]-sy))

    @property
    def layout(self):
        return UILayout(self.size)

    def ground(self, position):
        if self.view is None:
            return 0, 0
        x, top = self.layout.to_screen(position)
        y = self.size[1]-top
        near = np.array(gluUnProject(x, y, 0, self.view, self.projection, self.viewport))
        far = np.array(gluUnProject(x, y, 1, self.view, self.projection, self.viewport))
        ray = far-near
        hit = near+ray*(-near[1]/ray[1])
        return max(-MAP_X, min(MAP_X, float(hit[0]))), max(-MAP_Z, min(MAP_Z, float(hit[2])))

    def draw_world(self, world, me, dt, aim=None):
        for unit in world["units"]:
            target = (unit["x"], unit["z"])
            old = self.positions.get(unit["id"], target)
            factor = 1-math.exp(-18*dt)
            if math.dist(old, target) > 10:
                factor = 1
            self.positions[unit["id"]] = (old[0]+(target[0]-old[0])*factor, old[1]+(target[1]-old[1])*factor)
        valid_ids = {unit["id"] for unit in world["units"]}
        self.positions = {uid:p for uid,p in self.positions.items() if uid in valid_ids}
        if self.follow and me:
            position = self.positions.get(me["id"], (me["x"], me["z"]))
            self.camera = list(position)
        self.setup_world()
        glCallList(self.map_list)
        for relic in world["relics"]:
            ring(relic["x"], relic["z"], 1.1, (.24,.65,.56) if relic["timer"] <= 0 else (.19,.28,.3))
            if relic["timer"] <= 0:
                crystal(relic["x"], 1+math.sin(world["time"]*2)*.18, relic["z"], .5, .8, (.33, 1, .71))
            if relic["burst"] > 0:
                ring(relic["x"], relic["z"], 4, (.4, 1, .7), width=3)
        for unit in world["units"]:
            x, z = self.positions[unit["id"]]
            tint = TEAM[unit["team"]]
            if unit["hp"] <= 0:
                if unit["kind"] in ("tower", "inhibitor", "nexus"):
                    cube(x, .2, z, 2.3, .5, 2.3, (.18,.22,.28))
                continue
            if unit["kind"] == "hero":
                key = unit["champion"]
                self.load_champion(key)
                ring(x, z, .9, tint, width=2)
                if me and unit["id"] == me["id"]:
                    ring(x, z, 1.2, (.95,.86,.52), width=3)
                if unit["shield"] > 0:
                    ring(x, z, 1.3, (.65,.89,1), y=1.3, width=3)
                glPushMatrix()
                glTranslatef(x, .05, z)
                glRotatef(unit["facing"], 0, 1, 0)
                glCallList(self.model_lists.get(key, self.hero_lists[key]))
                glPopMatrix()
            elif unit["kind"] in ("minion", "super"):
                scale = 1.35 if unit["kind"] == "super" else .8
                cube(x, .55*scale, z, .7*scale, 1*scale, .7*scale, tint)
                crystal(x, 1.1*scale, z, .32*scale, .4*scale, (.71,.85,.92))
            elif unit["kind"] == "tower":
                cube(x, .3, z, 2.8, .6, 2.8, (.25,.32,.39))
                cube(x, 1.8, z, 1.7, 3, 1.7, (.36,.44,.52))
                cube(x, 3.1, z, 2.1, .45, 2.1, tint)
                crystal(x, 3.65, z, .75, 1.7, tint)
                if not unit["vulnerable"]:
                    ring(x, z, 1.8, (.47,.52,.6), y=.3)
            else:
                scale = 1.4 if unit["kind"] == "nexus" else 1
                cube(x, .25, z, 3.6*scale, .5, 3.6*scale, (.25,.34,.42))
                crystal(x, 1.1*scale, z, 1.25*scale, 2.4*scale, tint)
                ring(x, z, 2.4*scale, tint)
        for projectile in world["projectiles"]:
            tint = (.9,.97,1) if projectile["mark"] else TEAM[projectile["team"]]
            crystal(projectile["x"], 1, projectile["z"], projectile["radius"]*.7, .6, tint)
        glDisable(GL_LIGHTING)
        for effect in world["effects"]:
            tint = (.38,1,.71) if effect["kind"] == "heal" else TEAM[effect["team"]]
            progress = 1-effect["life"]/effect["duration"]
            if effect["kind"] == "attack":
                color(tint)
                glLineWidth(2)
                glBegin(GL_LINES)
                glVertex3f(effect["x"], 1.6, effect["z"])
                glVertex3f(effect["tx"], 1, effect["tz"])
                glEnd()
            else:
                ring(effect["x"], effect["z"], effect["radius"]*(.3+progress*.7), tint, y=.2, width=3)
        if aim and me and me["hp"] > 0:
            ring(aim[0], aim[1], .45, (.9,.82,.55), y=.12)
        glDisable(GL_LIGHTING)

    def overlay(self, surface, opaque=False, modal_layers=0):
        width, height = self.size
        glViewport(0, 0, width, height)
        if opaque:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, width, height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        # The HUD preserves 16:9, but modal dimming also covers monitor margins.
        if modal_layers:
            left, top = self.layout.offset
            right, bottom = width-left, height-top
            glDisable(GL_TEXTURE_2D)
            glColor4f(1/255,6/255,12/255,1-(1-195/255)**modal_layers)
            glBegin(GL_QUADS)
            for x1,y1,x2,y2 in [(0,0,left,height),(right,0,width,height),
                                  (left,0,right,top),(left,bottom,right,height)]:
                for vertex in [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]:
                    glVertex2f(*vertex)
            glEnd()
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.hud_texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        pixels = pygame.image.tobytes(surface, "RGBA", False)
        if self.hud_size != surface.get_size():
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, surface.get_width(), surface.get_height(),
                         0, GL_RGBA, GL_UNSIGNED_BYTE, pixels)
            self.hud_size = surface.get_size()
        else:
            glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, surface.get_width(), surface.get_height(), GL_RGBA, GL_UNSIGNED_BYTE, pixels)
        glColor4f(1,1,1,1)
        glBegin(GL_QUADS)
        ui_width, ui_height = UI_SIZE
        for uv, vertex in [((0,0),(0,0)),((1,0),(ui_width,0)),((1,1),(ui_width,ui_height)),((0,1),(0,ui_height))]:
            glTexCoord2f(*uv)
            glVertex2f(*self.layout.to_screen(vertex))
        glEnd()
        glDisable(GL_TEXTURE_2D)

    def screenshot(self, path):
        width, height = self.size
        glPixelStorei(GL_PACK_ALIGNMENT, 1)
        data = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
        surface = pygame.image.frombytes(data, (width, height), "RGB")
        pygame.image.save(pygame.transform.flip(surface, False, True), str(path))

    def close(self):
        for display_list in [self.map_list, *self.model_lists.values(), *self.hero_lists.values()]:
            glDeleteLists(display_list, 1)
        glDeleteTextures([self.hud_texture, *self.textures])
