import json
import socket
import time
import unittest

from frostbridge.network import Lobby, GameClient, GameServer


class LobbyTests(unittest.TestCase):
    def setUp(self):
        self.lobby=Lobby()
        self.lobby.command("a",dict(op="hello",name="Host"))
        self.lobby.command("a",dict(op="create",capacity=1,name="Room"))
        self.room=self.lobby.room_for("a")

    def test_only_host_can_start_or_add_bots(self):
        self.lobby.command("b",dict(op="join",room=self.room.id))
        with self.assertRaises(ValueError):
            self.lobby.command("b",dict(op="start"))
        with self.assertRaises(ValueError):
            self.lobby.command("b",dict(op="fill"))

    def test_team_capacity_and_balance(self):
        with self.assertRaises(ValueError):
            self.lobby.command("a",dict(op="start"))
        self.lobby.command("b",dict(op="join",room=self.room.id))
        with self.assertRaises(ValueError):
            self.lobby.command("c",dict(op="join",room=self.room.id))
        with self.assertRaises(ValueError):
            self.lobby.command("b",dict(op="team"))

    def test_all_humans_must_lock_before_match(self):
        self.lobby.command("b",dict(op="join",room=self.room.id))
        self.lobby.command("a",dict(op="start"))
        self.lobby.command("a",dict(op="pick",champion="mage"))
        self.lobby.command("a",dict(op="lock"))
        self.assertEqual(self.room.phase,"select")
        self.lobby.command("b",dict(op="lock"))
        self.assertEqual(self.room.phase,"game")
        self.assertEqual(self.room.world.units["a"].champion,"mage")

    def test_host_transfer_and_disconnected_player_becomes_bot(self):
        self.lobby.command("b",dict(op="join",room=self.room.id))
        self.lobby.command("a",dict(op="start"))
        self.lobby.command("a",dict(op="lock"))
        self.lobby.command("b",dict(op="lock"))
        self.lobby.leave("a")
        self.assertEqual(self.room.host,"b")
        self.assertTrue(self.room.world.units["a"].bot)
        self.lobby.leave("b")
        self.assertEqual(self.lobby.rooms,{})

    def test_every_supported_team_size(self):
        for capacity in range(1,6):
            lobby=Lobby()
            lobby.command("p",dict(op="create",capacity=capacity))
            lobby.command("p",dict(op="fill"))
            room=lobby.room_for("p")
            self.assertEqual(len(room.players),capacity*2)
            self.assertEqual(sum(p["team"]==0 for p in room.players),capacity)
            lobby.command("p",dict(op="start"))
            lobby.command("p",dict(op="lock"))
            self.assertEqual(room.phase,"game")

    def test_selection_disconnect_returns_remaining_players_to_room(self):
        self.lobby.command("b",dict(op="join",room=self.room.id))
        self.lobby.command("a",dict(op="start"))
        self.lobby.command("b",dict(op="lock"))
        self.lobby.leave("a")
        self.assertEqual(self.room.phase,"room")
        self.assertEqual(self.room.host,"b")
        self.assertIsNone(self.room.world)

    def test_match_commands_do_not_accept_client_stats(self):
        self.lobby.command("a",dict(op="fill"))
        self.lobby.command("a",dict(op="start"))
        self.lobby.command("a",dict(op="lock"))
        hero=self.room.world.units["a"]
        self.lobby.command("a",dict(op="action",action="move",point=[0,0],hp=99999,gold=99999))
        self.assertNotEqual(hero.hp,99999)
        self.assertNotEqual(hero.gold,99999)

    def test_rematch_resets_world(self):
        self.lobby.command("a",dict(op="fill"))
        self.lobby.command("a",dict(op="start"))
        self.lobby.command("a",dict(op="lock"))
        self.room.world.winner=0
        self.lobby.command("a",dict(op="rematch"))
        self.assertEqual(self.room.phase,"room")
        self.assertIsNone(self.room.world)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.server=GameServer("127.0.0.1",0).start()
        self.clients=[]

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.server.stop()

    def client(self,name):
        client=GameClient("127.0.0.1",self.server.port,name)
        self.clients.append(client)
        return client

    def wait_for(self,condition):
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            for client in self.clients:
                client.pump()
            if condition():
                return
            time.sleep(.01)
        self.fail("Timed out waiting for server state")

    def test_two_real_clients_enter_select_play_and_host_transfer(self):
        host=self.client("Host")
        guest=self.client("Guest")
        self.wait_for(lambda:host.id and guest.id)
        host.send("create",name="Network room",capacity=1)
        self.wait_for(lambda:host.state["room"])
        guest.send("join",room=host.state["room"]["id"])
        self.wait_for(lambda:guest.state["room"])
        guest.send("start")
        self.wait_for(lambda:guest.errors)
        self.assertIn("방장",guest.errors[-1])
        host.send("start")
        self.wait_for(lambda:guest.state["room"]["phase"]=="select")
        host.send("lock")
        guest.send("lock")
        self.wait_for(lambda:host.state["world"] and guest.state["world"])
        self.assertEqual(len([u for u in host.state["world"]["units"] if u["kind"]=="hero"]),2)
        host.close()
        self.wait_for(lambda:guest.state["room"]["host"]==guest.id)
        former=next(u for u in guest.state["world"]["units"] if u["id"]==host.id)
        self.assertTrue(former["bot"])

    def test_malformed_peer_does_not_crash_server(self):
        good=self.client("Good")
        self.wait_for(lambda:bool(good.id))
        with socket.create_connection(("127.0.0.1",self.server.port)) as raw:
            raw.sendall(b'null\n{"op": []}\n{bad json}\n')
            time.sleep(.05)
        good.send("create",capacity=1)
        self.wait_for(lambda:good.state["room"])
        self.assertTrue(self.server.thread.is_alive())

    def test_ten_clients_start_a_full_five_vs_five_match(self):
        clients=[self.client(f"Player{i}") for i in range(10)]
        self.wait_for(lambda:all(c.id for c in clients))
        clients[0].send("create",capacity=5)
        self.wait_for(lambda:clients[0].state["room"])
        rid=clients[0].state["room"]["id"]
        for client in clients[1:]:
            client.send("join",room=rid)
        self.wait_for(lambda:all(c.state["room"] and len(c.state["room"]["players"])==10 for c in clients))
        clients[0].send("start")
        self.wait_for(lambda:all(c.state["room"]["phase"]=="select" for c in clients))
        for client in clients:
            client.send("lock")
        self.wait_for(lambda:all(c.state["world"] for c in clients))
        units=clients[0].state["world"]["units"]
        self.assertEqual([sum(u["kind"]=="hero" and u["team"]==t for u in units) for t in (0,1)],[5,5])


if __name__=="__main__":
    unittest.main()
