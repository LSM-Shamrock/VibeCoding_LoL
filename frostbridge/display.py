"""Aspect-preserving UI coordinates and screen-relative camera controls."""
from dataclasses import dataclass
import math

UI_SIZE = (1280, 720)
CAMERA_OFFSET = (-16, 39, 31)
MINIMAP_RECT = (1066, 534, 192, 160)
HUD_RECT = (300, 598, 634, 116)
MINIMAP_PANEL = (1054, 506, 218, 208)
SCORE_RECT = (942, 8, 330, 32)


def over_hud(position):
    x,y=position
    return any(left <= x < left+width and top <= y < top+height
               for left,top,width,height in (HUD_RECT,MINIMAP_PANEL,SCORE_RECT))


def minimap_basis():
    ex, ey, ez = CAMERA_OFFSET
    horizontal = math.hypot(ex, ez)
    pitch = ey/math.sqrt(horizontal**2+ey**2)
    a, b = ez/horizontal, -ex/horizontal
    c, d = ex/horizontal*pitch, ez/horizontal*pitch
    width, height = MINIMAP_RECT[2:]
    scale = min(width/(2*(abs(a)*59+abs(b)*7.4)),
                height/(2*(abs(c)*59+abs(d)*7.4)))
    return a, b, c, d, scale


def world_to_minimap(x, z):
    a, b, c, d, scale = minimap_basis()
    left, top, width, height = MINIMAP_RECT
    return (left+width/2+(a*x+b*z)*scale,
            top+height/2+(c*x+d*z)*scale)


def minimap_to_world(position):
    a, b, c, d, scale = minimap_basis()
    left, top, width, height = MINIMAP_RECT
    sx = (position[0]-left-width/2)/scale
    sy = (position[1]-top-height/2)/scale
    determinant = a*d-b*c
    return ((d*sx-b*sy)/determinant, (-c*sx+a*sy)/determinant)


@dataclass(frozen=True)
class UILayout:
    size: tuple

    @property
    def scale(self):
        return min(self.size[0]/UI_SIZE[0], self.size[1]/UI_SIZE[1])

    @property
    def offset(self):
        return ((self.size[0]-UI_SIZE[0]*self.scale)/2,
                (self.size[1]-UI_SIZE[1]*self.scale)/2)

    def to_ui(self, position):
        x, y = self.offset
        return ((position[0]-x)/self.scale, (position[1]-y)/self.scale)

    def to_screen(self, position):
        x, y = self.offset
        return (x+position[0]*self.scale, y+position[1]*self.scale)


def edge_direction(position, size, margin=18):
    x, y = position
    width, height = size
    if not (0 <= x < width and 0 <= y < height):
        return 0, 0
    return (int(x >= width-margin)-int(x < margin),
            int(y >= height-margin)-int(y < margin))


def pan_camera(camera, horizontal, vertical, dt, speed=24):
    """Translate along projected screen axes, keeping diagonal speed constant."""
    length = math.hypot(horizontal, vertical)
    if not length:
        return list(camera)
    ex, _, ez = CAMERA_OFFSET
    factor = speed*dt/(math.hypot(ex, ez)*length)
    dx = (horizontal*ez+vertical*ex)*factor
    dz = (-horizontal*ex+vertical*ez)*factor
    return [max(-59, min(59, camera[0]+dx)),
            max(-18, min(18, camera[1]+dz))]
