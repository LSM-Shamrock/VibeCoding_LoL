import math
import unittest

from frostbridge.simulation import World, point


def make_world():
    return World([dict(id="blue", name="Blue", team=0, champion="mage"),
                  dict(id="red", name="Red", team=1, champion="warden")])


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.world = make_world()
        self.blue = self.world.units["blue"]
        self.red = self.world.units["red"]

    def test_points_reject_nonfinite_and_clamp_bounds(self):
        for bad in ([math.nan,0], [0,math.inf], [], "0,0"):
            with self.assertRaises((ValueError,TypeError)):
                point(bad)
        self.assertEqual(point([999,-999]), (59, -7.4))

    def test_movement_is_speed_limited(self):
        self.blue.x, self.blue.z = 0, 0
        self.world.command("blue", {"action":"move", "point":[10,0]})
        self.world.update(.1)
        self.assertAlmostEqual(self.blue.x, self.blue.speed*.1)

    def test_center_lane_minion_can_pass_friendly_buildings(self):
        self.world.spawn_wave()
        minion = next(u for u in self.world.units.values() if u.kind=="minion" and u.team==0 and u.z==0)
        for _ in range(600):
            self.world.update(1/30)
        self.assertGreater(minion.x, -15)

    def test_shop_closes_after_departure_even_when_returning(self):
        self.blue.gold=2000
        self.world.buy(self.blue,"sword")
        self.assertEqual(self.blue.items,["sword"])
        self.blue.x=-45
        self.world.update(.1)
        self.blue.x=-55
        with self.assertRaises(ValueError):
            self.world.buy(self.blue,"boots")
        self.blue.hp=0
        self.world.buy(self.blue,"boots")
        self.assertEqual(len(self.blue.items),2)

    def test_unique_items_gold_and_six_slot_limit(self):
        self.blue.gold=100000
        self.world.buy(self.blue,"boots")
        with self.assertRaises(ValueError):
            self.world.buy(self.blue,"boots")
        for _ in range(5):
            self.world.buy(self.blue,"sword")
        with self.assertRaises(ValueError):
            self.world.buy(self.blue,"sword")
        self.red.gold=0
        with self.assertRaises(ValueError):
            self.world.buy(self.red,"sword")

    def test_tower_inhibitor_nexus_dependency_and_victory(self):
        world=self.world
        self.assertFalse(world.vulnerable(world.units["n1"]))
        self.assertFalse(world.vulnerable(world.units["t1_1"]))
        for uid in ["t1_0","t1_1","i1","nt1_0","nt1_1","n1"]:
            target=world.units[uid]
            self.assertTrue(world.vulnerable(target),uid)
            world.hurt(target,1_000_000,self.blue)
            self.assertEqual(target.hp,0)
        self.assertEqual(world.winner,0)
        old_time=world.time
        world.update(10)
        self.assertEqual(world.time,old_time)

    def test_protected_structure_ignores_damage(self):
        nexus=self.world.units["n1"]
        hp=nexus.hp
        self.world.hurt(nexus,1_000_000,self.blue)
        self.assertEqual(nexus.hp,hp)

    def test_backdoor_protection_reduces_tower_damage(self):
        tower=self.world.units["t1_0"]
        self.world.hurt(tower,100,self.blue)
        without=tower.max_hp-tower.hp
        self.world.spawn_wave()
        minion=next(u for u in self.world.units.values() if u.kind=="minion" and u.team==0)
        minion.x,minion.z=tower.x-4,0
        before=tower.hp
        self.world.hurt(tower,100,self.blue)
        self.assertAlmostEqual(before-tower.hp,without*4)

    def test_inhibitor_respawns_and_produces_super_wave(self):
        inhibitor=self.world.units["i1"]
        inhibitor.hp=0
        inhibitor.respawn=.05
        self.world.spawn_wave()
        self.assertTrue(any(u.kind=="super" and u.team==0 for u in self.world.units.values()))
        self.world.update(.1)
        self.assertEqual(inhibitor.hp,inhibitor.max_hp)

    def test_death_revives_at_spawn_and_reopens_shop(self):
        self.blue.shop_allowed=False
        self.blue.hp=1
        self.world.hurt(self.blue,10000,self.red)
        self.assertEqual(self.blue.deaths,1)
        self.assertEqual(self.red.kills,1)
        self.assertGreater(self.blue.respawn,0)
        self.blue.respawn=.05
        self.world.update(.1)
        self.assertEqual(self.blue.hp,self.blue.max_hp)
        self.assertEqual(self.blue.x,-55)
        self.assertTrue(self.blue.shop_allowed)

    def test_spell_cooldowns_mana_and_ultimate_gate(self):
        before=self.blue.mana
        self.world.cast(self.blue,3,(0,0))
        self.assertEqual(self.blue.mana,before)
        self.world.cast(self.blue,0,(0,0))
        self.assertLess(self.blue.mana,before)
        spent=self.blue.mana
        self.world.cast(self.blue,0,(0,0))
        self.assertEqual(self.blue.mana,spent)
        self.blue.level=6
        self.world.cast(self.blue,3,(0,0))
        self.assertGreater(self.blue.cooldowns[3],0)

    def test_projectile_hits_enemy_and_snowball_can_dash(self):
        self.blue.x,self.blue.z=0,0
        self.red.x,self.red.z=5,0
        before=self.red.hp
        self.world.cast(self.blue,4,(10,0))
        for _ in range(8):
            self.world.update(1/30)
        self.assertLess(self.red.hp,before)
        self.assertEqual(self.blue.mark,"red")
        self.world.cast(self.blue,4,(10,0))
        self.assertLess(abs(self.blue.x-self.red.x),2)

    def test_no_fountain_full_heal(self):
        self.blue.hp=100
        self.world.update(.5)
        self.assertLess(self.blue.hp,102)

    def test_bots_play_and_snapshots_are_json_serializable(self):
        import json
        self.blue.bot=self.red.bot=True
        for _ in range(1800):
            self.world.update(1/30)
        json.dumps(self.world.snapshot(),allow_nan=False)
        self.assertGreater(self.world.wave,1)
        self.assertLess(abs(self.blue.x),50)
        self.assertTrue(self.blue.items)


if __name__=="__main__":
    unittest.main()
