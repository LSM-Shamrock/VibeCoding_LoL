from collections import defaultdict
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pygame

from frostbridge.app import App
from frostbridge.display import UILayout, edge_direction, pan_camera, UI_SIZE, world_to_minimap, minimap_to_world, CAMERA_OFFSET, over_hud


class LayoutTests(unittest.TestCase):
    def test_aspect_and_click_coordinates_at_common_resolutions(self):
        for size in [(1280,800),(1920,1080),(2560,1440),(3440,1440),(1024,768),(3840,2160)]:
            with self.subTest(size=size):
                layout=UILayout(size)
                origin=layout.to_screen((0,0))
                corner=layout.to_screen(UI_SIZE)
                self.assertAlmostEqual((corner[0]-origin[0])/(corner[1]-origin[1]),16/9)
                self.assertGreaterEqual(origin[0],0)
                self.assertGreaterEqual(origin[1],0)
                self.assertLessEqual(corner[0],size[0])
                self.assertLessEqual(corner[1],size[1])
                # Shop button, minimap, center, and world labels share the inverse.
                for point in [(1144,697),(100,714),(640,400),(-40,150)]:
                    restored=layout.to_ui(layout.to_screen(point))
                    self.assertAlmostEqual(restored[0],point[0])
                    self.assertAlmostEqual(restored[1],point[1])

    def test_minimap_inverse_and_camera_projection_agree(self):
        for x,z in [(-55,0),(55,0),(0,0),(-19,-3),(47,3.4)]:
            result=minimap_to_world(world_to_minimap(x,z))
            self.assertAlmostEqual(result[0],x)
            self.assertAlmostEqual(result[1],z)
        left=world_to_minimap(-59,0)
        right=world_to_minimap(59,0)
        ex,ey,ez=CAMERA_OFFSET
        expected_slope=ex/ez*ey/math.sqrt(ex*ex+ey*ey+ez*ez)
        self.assertAlmostEqual((right[1]-left[1])/(right[0]-left[0]),expected_slope)

    def test_16_9_monitor_has_no_ui_margins(self):
        self.assertEqual(UILayout((1920,1080)).offset,(0,0))

    def test_hud_blocks_world_clicks_only_in_occupied_regions(self):
        for point in [(600,640),(810,620),(1100,650),(1200,25)]:
            self.assertTrue(over_hud(point))
        for point in [(100,650),(640,400),(980,670)]:
            self.assertFalse(over_hud(point))

    def test_edges_use_physical_screen_not_centered_ui_bounds(self):
        size=(1920,1080)
        self.assertEqual(edge_direction((1,540),size),(-1,0))
        self.assertEqual(edge_direction((1919,0),size),(1,-1))
        self.assertEqual(edge_direction((960,1079),size),(0,1))
        self.assertEqual(edge_direction((100,540),size),(0,0))
        self.assertEqual(edge_direction((-1,540),size),(0,0))

    def test_camera_screen_directions_and_diagonal_speed(self):
        right=pan_camera([0,0],1,0,.1)
        up=pan_camera([0,0],0,-1,.1)
        diagonal=pan_camera([0,0],1,1,.1)
        self.assertGreater(right[0],0)
        self.assertGreater(right[1],0)
        self.assertGreater(up[0],0)
        self.assertLess(up[1],0)
        self.assertAlmostEqual(math.hypot(*right),math.hypot(*diagonal))


class CameraInputTests(unittest.TestCase):
    def setUp(self):
        self.app=App.__new__(App)
        self.app.renderer=SimpleNamespace(follow=False,camera=[0,0],size=(1920,1080),zoom=21.5)
        self.app.shop=self.app.menu=self.app.scoreboard=False
        self.app.mouse=(640,400)
        self.world={"winner":None}
        self.me={"id":"player"}
        self.keys=defaultdict(bool)
        self.mocks=[patch("pygame.key.get_pressed",return_value=self.keys),
                    patch("pygame.key.get_focused",return_value=True),
                    patch("pygame.mouse.get_focused",return_value=True),
                    patch("pygame.mouse.get_pos",return_value=(1919,540)),
                    patch("pygame.mouse.get_pressed",return_value=(False,False,False))]
        for mock in self.mocks:
            mock.start()
            self.addCleanup(mock.stop)

    def test_space_only_locks_while_held_and_overrides_edge_scroll(self):
        self.keys[pygame.K_SPACE]=True
        self.app.match_input([],self.world,self.me,.1)
        self.assertTrue(self.app.renderer.follow)
        self.assertEqual(self.app.renderer.camera,[0,0])
        self.keys[pygame.K_SPACE]=False
        self.app.match_input([],self.world,self.me,.1)
        self.assertFalse(self.app.renderer.follow)
        self.assertGreater(self.app.renderer.camera[0],0)

    def test_escape_menu_suppresses_scroll_and_releases_space(self):
        self.app.renderer.follow=True
        self.app.match_input([pygame.event.Event(pygame.KEYDOWN,key=pygame.K_ESCAPE)],self.world,self.me,.1)
        self.assertTrue(self.app.menu)
        self.assertFalse(self.app.renderer.follow)
        self.assertEqual(self.app.renderer.camera,[0,0])
        self.app.match_input([pygame.event.Event(pygame.KEYDOWN,key=pygame.K_ESCAPE)],self.world,self.me,.1)
        self.assertFalse(self.app.menu)
        self.assertGreater(self.app.renderer.camera[0],0)

    def test_focus_loss_clears_follow_and_disables_scroll(self):
        self.app.renderer.follow=True
        self.keys[pygame.K_SPACE]=True
        with patch("pygame.key.get_focused",return_value=False):
            self.app.match_input([],self.world,self.me,.1)
        self.assertFalse(self.app.renderer.follow)
        self.assertEqual(self.app.renderer.camera,[0,0])

    def test_right_minimap_click_moves_camera_to_corresponding_world_point(self):
        point=world_to_minimap(19,3)
        with patch("pygame.mouse.get_pos",return_value=(960,540)):
            self.app.match_input([pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=point)],self.world,self.me,.1)
        self.assertAlmostEqual(self.app.renderer.camera[0],19)
        self.assertAlmostEqual(self.app.renderer.camera[1],3)
