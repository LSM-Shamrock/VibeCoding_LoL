import argparse
import logging
import math
import os
from pathlib import Path
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

from .content import CHAMPIONS, ITEMS, PORT, ROOT
from .network import GameClient, GameServer
from .render import Renderer
from .display import edge_direction, pan_camera, world_to_minimap, minimap_to_world, MINIMAP_RECT, UI_SIZE, MINIMAP_PANEL, SCORE_RECT, over_hud
from .ui import UI, BG, PANEL, LINE, WHITE, MUTED, CYAN, GOLD, RED, BLUE
from .hud import draw_champion_hud


class App:
    def __init__(self, hidden=False, size=UI_SIZE):
        pygame.display.init()
        pygame.font.init()
        self.renderer = Renderer(size=size,hidden=hidden)
        self.ui = UI()
        self.client = None
        self.server = None
        self.running = True
        self.capacity = 5
        self.room_page = 0
        self.toast = ""
        self.toast_until = 0
        self.shop = False
        self.menu = False
        self.scoreboard = False
        self.phase = "home"
        self.last_phase = ""
        self.move_at = 0
        self.quick = False
        self.quick_step = 0
        self.mouse = (0,0)
        self.clock = pygame.time.Clock()

    def tell(self, message):
        self.toast = message
        self.toast_until = time.monotonic()+5

    def send(self, op, **payload):
        if self.client and self.client.connected:
            self.client.send(op, **payload)

    def connect(self, local=False, quick=False):
        try:
            if self.client:
                self.client.close()
            if local:
                if not self.server:
                    self.server = GameServer("0.0.0.0", PORT).start()
                host, port = "127.0.0.1", self.server.port
                self.ui.fields["address"] = f"{host}:{port}"
            else:
                address = self.ui.fields["address"].strip()
                host, sep, raw_port = address.partition(":")
                port = int(raw_port) if sep else PORT
                if not 1 <= port <= 65535:
                    raise ValueError("포트는 1~65535 사이여야 합니다.")
            self.client = GameClient(host, port, self.ui.fields["name"])
            self.quick, self.quick_step = quick, 0
            self.ui.focus = None
            pygame.key.stop_text_input()
        except (OSError, ValueError) as error:
            self.client = None
            self.tell(f"연결 실패: {error}")

    def disconnect(self):
        if self.client:
            self.client.close()
        self.client = None
        self.quick = False

    def home(self):
        ui = self.ui
        ui.header("서리 다리 · 싱글 레인 아레나")
        if ui.button("게임 종료",(1098,24,138,40),size=16):
            self.running=False
        ui.text("A BRIDGE. TWO TEAMS. ONE VICTORY.", 62, 128, 16, CYAN, True)
        ui.text("FROST", 54, 160, 86, WHITE, True)
        ui.text("BRIDGE", 54, 246, 86, WHITE, True)
        ui.line((62,365),(120,365),CYAN,3)
        ui.text("한 줄의 전장, 끝없는 교전", 62, 388, 27, WHITE, True)
        ui.paragraph("팀을 모으고, 영웅을 선택하고, 상대의 넥서스를 무너뜨리세요.\n얼어붙은 다리 위에서 전투가 시작됩니다.",62,435,610,19,line_height=31)
        for x, number, label in [(62,"01—05","팀별 플레이어"),(280,"6","선택 가능한 영웅"),(490,"3D","실시간 전장")]:
            ui.text(number,x,520,30,CYAN,True)
            ui.text(label,x,562,15,MUTED)
        if ui.button("혼자 시작 · 봇 연습",(62,635,286,48)):
            self.connect(local=True,quick=True)
        ui.text("로컬 서버와 1 대 1 연습 방을 만듭니다.",367,648,15,MUTED)
        ui.panel((786,118,450,506),(13,25,39))
        ui.text("전장에 합류",818,146,29,WHITE,True)
        ui.text("서버를 열거나 친구의 서버에 접속하세요.",818,194,16,MUTED)
        ui.field("name","플레이어 이름",(818,257,386,50),18)
        ui.field("address","서버 주소  IP:PORT",(818,351,386,50),80)
        if ui.button("서버에 접속  →",(818,427,386,52),primary=True):
            self.connect()
        if ui.button("내 PC에서 서버 열기",(818,493,386,48)):
            self.connect(local=True)
        ui.text("같은 네트워크의 친구는 내 PC의 IP로 접속",818,575,14,MUTED)
        ui.text("PROTOTYPE 0.1  /  PYGAME + OPENGL",818,655,13,MUTED)

    def lobby(self, state):
        ui = self.ui
        ui.header("01 / 로비",self.ui.fields["address"])
        ui.text("함께할 전장을 찾으세요",44,112,32,WHITE,True)
        ui.text("방에 입장하거나 새로운 전투를 만드세요.",44,158,17,MUTED)
        if ui.button("연결 종료",(1098,114,138,40),size=16):
            self.disconnect()
        ui.panel((44,193,360,477))
        ui.text("새로운 방",70,217,25,WHITE,True)
        ui.field("room_name","방 이름",(70,290,308,50),28)
        ui.text("팀별 인원",70,369,16,MUTED)
        for i in range(1,6):
            if ui.button(str(i),(70+(i-1)*63,404,55,48),primary=self.capacity==i):
                self.capacity=i
        ui.text(f"{self.capacity} vs {self.capacity}  ·  최대 {self.capacity*2}명",70,474,20,CYAN)
        ui.paragraph("빈 자리에 봇을 추가할 수 있습니다. 방장이 시작하면 캐릭터를 선택합니다.",70,515,300,16)
        if ui.button("방 만들기  +",(70,601,308,48),primary=True):
            self.send("create",name=ui.fields["room_name"],capacity=self.capacity)
        rooms=state["rooms"]
        ui.text(f"진행 중인 방  {len(rooms):02}",438,198,19,WHITE,True)
        self.room_page=min(self.room_page,max(0,(len(rooms)-1)//5))
        visible=rooms[self.room_page*5:self.room_page*5+5]
        if not visible:
            ui.panel((438,238,798,365),(12,24,37))
            ui.text("아직 열린 방이 없습니다",837,375,26,WHITE,True,center=True)
            ui.text("첫 번째 방을 만들고 봇이나 친구를 초대하세요.",837,429,17,MUTED,center=True)
        for index,room in enumerate(visible):
            y=238+index*78
            ui.panel((438,y,798,74))
            ui.text(room["name"],461,y+10,20,WHITE,True)
            phase={"room":"대기 중","select":"캐릭터 선택","game":"게임 중"}[room["phase"]]
            ui.text(f"{room['capacity']} vs {room['capacity']}     {len(room['players'])}/{room['capacity']*2}명     {phase}",461,y+43,14,MUTED)
            enabled=room["phase"]=="room" and len(room["players"])<room["capacity"]*2
            if ui.button("입장 →",(1104,y+17,112,40),enabled=enabled,size=16):
                self.send("join",room=room["id"])
        if len(rooms)>5:
            if ui.button("이전",(965,654,100,38),enabled=self.room_page>0,size=16):
                self.room_page-=1
            if ui.button("다음",(1080,654,100,38),enabled=(self.room_page+1)*5<len(rooms),size=16):
                self.room_page+=1

    def room(self, room):
        ui=self.ui
        host=room["host"]==self.client.id
        ui.header("02 / 대기실",self.ui.fields["address"])
        ui.text(room["name"],44,108,32,WHITE,True)
        ui.text(f"{room['capacity']} vs {room['capacity']}  ·  양 팀을 채우면 방장이 시작할 수 있습니다.",44,153,17,MUTED)
        if ui.button("방 나가기",(1098,110,138,42),size=16):
            self.send("leave")
        for team,x in [(0,44),(1,660)]:
            tint=BLUE if team==0 else RED
            ui.panel((x,185,576,387))
            ui.text("BLUE / 푸른 서리" if team==0 else "RED / 붉은 황혼",x+24,204,23,tint,True)
            players=[p for p in room["players"] if p["team"]==team]
            for slot in range(room["capacity"]):
                y=249+slot*60
                ui.panel((x+20,y,536,55),(12,23,35),None,6)
                if slot<len(players):
                    player=players[slot]
                    ui.portrait(player["champion"],(x+27,y+6,43,43))
                    suffix="  ·  나" if player["id"]==self.client.id else ""
                    ui.text(player["name"]+suffix,x+85,y+7,18)
                    badge="BOT" if player["bot"] else "방장" if player["id"]==room["host"] else "플레이어"
                    ui.text(badge,x+85,y+32,12,tint)
                    if player["bot"] and host and ui.button("제거",(x+475,y+10,66,34),size=14):
                        self.send("remove_bot",player=player["id"])
                else:
                    ui.text(f"빈 자리 {slot+1}",x+40,y+16,16,MUTED)
            if ui.button("+ 봇 추가",(x+355,200,195,39),enabled=host and len(players)<room["capacity"],size=16):
                self.send("bot",team=team)
        ui.text("단일 공격로  /  귀환 불가  /  넥서스 파괴 시 승리",44,594,16,MUTED)
        if ui.button("팀 변경",(44,647,160,50)):
            self.send("team")
        if ui.button("빈 자리 봇 채우기",(220,647,235,50),enabled=host):
            self.send("fill")
        full=len(room["players"])==room["capacity"]*2
        if ui.button("캐릭터 선택 시작  →" if host else "방장이 시작하기를 기다리는 중",(817,647,419,50),primary=True,enabled=host and full):
            self.send("start")

    def selection(self,room):
        ui=self.ui
        player=next(p for p in room["players"] if p["id"]==self.client.id)
        selected=player["champion"]
        spec=CHAMPIONS[selected]
        ui.header("03 / 캐릭터 선택",self.ui.fields["address"])
        ui.text("당신의 영웅을 선택하세요",44,107,32,WHITE,True)
        locked=sum(p["locked"] for p in room["players"])
        ui.text(f"선택 완료 {locked} / {len(room['players'])}  ·  전원이 선택하면 전투가 시작됩니다.",44,155,17,MUTED)
        for index,(key,champion) in enumerate(CHAMPIONS.items()):
            x=44+(index%3)*202
            y=183+(index//3)*194
            active=key==selected
            ui.panel((x,y,186,183),PANEL,CYAN if active else LINE,8)
            ui.portrait(key,(x+7,y+7,172,112))
            ui.text(champion["role"],x+14,y+126,13,champion["color"])
            if ui.button(champion["name"],(x+84,y+128,94,44),primary=active,enabled=not player["locked"],size=20):
                self.send("pick",champion=key)
        ui.panel((681,183,555,377))
        ui.text(spec["title"],708,200,16,spec["color"])
        ui.text(spec["name"],706,224,35,WHITE,True)
        ui.text(f"{spec['role']}  /  체력 {spec['hp']}  /  공격 거리 {spec['range']}",708,275,15,MUTED)
        ui.line((708,308),(1208,308))
        for i,skill in enumerate(spec["skills"]):
            y=320+i*57
            ui.panel((708,y+3,35,35),(28,46,62),LINE,5)
            ui.text("QWER"[i],725,y+6,20,CYAN,True,center=True)
            ui.text(skill["name"]+("  ·  레벨 6 해금" if i==3 else ""),756,y,17,WHITE,True)
            ui.text(skill["description"],756,y+29,13,MUTED)
        ui.text("팀 구성",44,582,16,MUTED)
        for index,p in enumerate(room["players"]):
            x=44+index*117
            ui.panel((x,610,109,43),(17,34,47),CYAN if p["locked"] else LINE,5)
            ui.text(CHAMPIONS[p["champion"]]["name"],x+10,614,15,BLUE if p["team"]==0 else RED)
            ui.text("준비 완료" if p["locked"] else "선택 중",x+10,636,10,MUTED)
        if ui.button("대기실로" if room["host"]==self.client.id else "방 나가기",(44,674,170,40),size=16):
            self.send("cancel_select" if room["host"]==self.client.id else "leave")
        if ui.button("선택 해제" if player["locked"] else "선택 완료  →",(892,669,344,47),primary=True):
            self.send("lock")

    def action(self,action,**kwargs):
        self.send("action",action=action,**kwargs)

    def match_input(self,events,world,me,dt):
        if not me:
            return
        for event in events:
            if event.type==pygame.KEYDOWN:
                if event.key==pygame.K_ESCAPE:
                    if self.shop:
                        self.shop=False
                    else:
                        self.menu=not self.menu
                elif event.key==pygame.K_p:
                    self.shop=not self.shop
                elif self.shop and pygame.K_1 <= event.key <= pygame.K_6:
                    self.action("buy",item=list(ITEMS)[event.key-pygame.K_1])
                elif not self.shop and not self.menu and not self.scoreboard:
                    aim=self.renderer.ground(self.mouse)
                    slots=[pygame.K_q,pygame.K_w,pygame.K_e,pygame.K_r,pygame.K_d,pygame.K_f]
                    if event.key in slots:
                        self.action("cast",slot=slots.index(event.key),point=aim)
                    elif event.key==pygame.K_a:
                        self.action("attack_move",point=aim)
                    elif event.key==pygame.K_s:
                        self.action("stop")
            if event.type==pygame.MOUSEWHEEL and not self.shop and not self.menu:
                self.renderer.zoom=max(13,min(33,self.renderer.zoom-event.y*1.5))
        keys=pygame.key.get_pressed()
        focused=pygame.key.get_focused()
        self.scoreboard=focused and keys[pygame.K_TAB]
        self.renderer.follow=bool(focused and keys[pygame.K_SPACE])
        if self.shop or self.menu or self.scoreboard or world["winner"] is not None:
            return
        if not focused:
            return
        cx=int(keys[pygame.K_RIGHT])-int(keys[pygame.K_LEFT])
        cz=int(keys[pygame.K_DOWN])-int(keys[pygame.K_UP])
        if pygame.mouse.get_focused():
            edge_x,edge_y=edge_direction(pygame.mouse.get_pos(),self.renderer.size)
            cx=max(-1,min(1,cx+edge_x))
            cz=max(-1,min(1,cz+edge_y))
        if not self.renderer.follow:
            self.renderer.camera=pan_camera(self.renderer.camera,cx,cz,dt)
        for event in events:
            if not self.renderer.follow and event.type==pygame.MOUSEBUTTONDOWN and event.button==1 and pygame.Rect(MINIMAP_RECT).collidepoint(event.pos):
                x,z=minimap_to_world(event.pos)
                self.renderer.camera=[max(-59,min(59,x)),max(-7.4,min(7.4,z))]
        right_click=any(e.type==pygame.MOUSEBUTTONDOWN and e.button==3 for e in events)
        if (right_click or pygame.mouse.get_pressed()[2]) and 0<self.mouse[1]<720 and not over_hud(self.mouse) and time.monotonic()>=self.move_at:
            self.move_at=time.monotonic()+.12
            candidates=[]
            for unit in world["units"]:
                if unit["hp"]<=0 or unit["team"]==me["team"] or not unit["vulnerable"]:
                    continue
                px,pz=self.renderer.positions.get(unit["id"],(unit["x"],unit["z"]))
                sx,sy=self.renderer.project(px,1.2,pz)
                d=math.dist(self.mouse,(sx,sy))
                if d<max(20,unit["radius"]*13):
                    candidates.append((d,unit["id"]))
            if candidates:
                self.action("attack",target=min(candidates)[1])
            else:
                self.action("move",point=self.renderer.ground(self.mouse))

    def hud(self,world,me,room):
        ui=self.ui
        heroes=[u for u in world["units"] if u["kind"]=="hero"]
        for unit in world["units"]:
            if unit["hp"]<=0:
                continue
            px,pz=self.renderer.positions.get(unit["id"],(unit["x"],unit["z"]))
            height=5.3 if unit["kind"]=="tower" else 3.2 if unit["kind"] in ("hero","nexus") else 2
            sx,sy=self.renderer.project(px,height,pz)
            if not 10<sx<1270 or not 25<sy<700 or over_hud((sx,sy)):
                continue
            w=86 if unit["kind"]=="hero" else 59
            ui.bar((sx-w/2,sy,w,6),unit["hp"],unit["max_hp"],BLUE if unit["team"]==0 else RED)
            if unit["kind"]=="hero":
                ui.text(f"{unit['name']}  {unit['level']}",sx,sy-21,12,WHITE,center=True)
                ui.bar((sx-w/2,sy+8,w,3),unit["mana"],unit["max_mana"],(91,132,220))
        ui.panel(SCORE_RECT,(9,18,25,235),(69,68,53),4)
        kills=[sum(h["kills"] for h in heroes if h["team"]==t) for t in (0,1)]
        ui.text(str(kills[0]),963,15,15,BLUE,True)
        ui.text("/",988,15,14,MUTED)
        ui.text(str(kills[1]),1004,15,15,RED,True)
        if me:
            ui.text(f"{me['kills']} / {me['deaths']} / {me['assists']}",1053,16,13,WHITE)
        t=int(world["time"])
        ui.text(f"{t//60:02}:{t%60:02}",1228,14,16,GOLD,center=True)
        for i,entry in enumerate(world["feed"][-4:]):
            if world["time"]-entry["time"]<9:
                ui.text(entry["text"],1012,56+i*25,12,GOLD)
        if not me:
            return
        if draw_champion_hud(ui,me,self.mouse):
            self.shop=not self.shop
        ui.panel(MINIMAP_PANEL,(8,18,25,248),(103,91,60),4)
        bridge=[world_to_minimap(x,z) for x,z in [(-59,-7.4),(59,-7.4),(59,7.4),(-59,7.4)]]
        pygame.draw.polygon(ui.surface,(43,64,80),bridge)
        pygame.draw.polygon(ui.surface,(96,129,150),bridge,1)
        ui.line(world_to_minimap(-59,0),world_to_minimap(59,0),(65,94,112))
        for unit in world["units"]:
            if unit["hp"]<=0:
                continue
            x,y=world_to_minimap(unit["x"],unit["z"])
            tint=BLUE if unit["team"]==0 else RED
            size=4 if unit["kind"]=="hero" else 3 if unit["kind"] in ("tower","nexus") else 1
            pygame.draw.circle(ui.surface,tint,(int(x),int(y)),size)
            if unit["id"]==me["id"]:
                pygame.draw.circle(ui.surface,WHITE,(int(x),int(y)),6,1)
        if me["hp"]<=0 and world["winner"] is None:
            ui.panel((443,114,394,95),(10,21,33,235),LINE,9)
            ui.text(f"{math.ceil(me['respawn'])}초 후 부활",640,128,28,WHITE,True,center=True)
            ui.text("상점을 이용할 수 있습니다.",640,174,15,GOLD,center=True)
        if self.shop:
            self.shop_panel(me)
        if self.scoreboard:
            self.scores(heroes)
        if self.menu and world["winner"] is None:
            ui.modal_shade()
            ui.panel((430,246,420,290))
            ui.text("전투 메뉴",640,274,30,WHITE,True,center=True)
            ui.text("메뉴를 열어도 전투는 계속됩니다.",640,327,15,MUTED,center=True)
            if ui.button("계속하기",(464,382,352,48),primary=True):
                self.menu=False
            if ui.button("방 나가기",(464,452,352,48),danger=True):
                self.send("leave")
                self.menu=False
        if world["winner"] is not None:
            ui.modal_shade()
            ui.panel((300,186,680,406))
            won=world["winner"]==me["team"]
            ui.text("VICTORY" if won else "DEFEAT",640,222,58,CYAN if won else RED,True,center=True)
            ui.text("상대 넥서스를 파괴했습니다." if won else "우리 팀의 넥서스가 파괴되었습니다.",640,310,22,WHITE,center=True)
            ui.text(f"{me['kills']} 처치   /   {me['deaths']} 데스   /   {me['assists']} 어시스트",640,366,20,GOLD,center=True)
            host=room["host"]==self.client.id
            if ui.button("다시 대기실로" if host else "방장의 재시작을 기다리는 중",(360,443,560,49),primary=True,enabled=host):
                self.send("rematch")
            if ui.button("로비로 나가기",(360,516,560,44)):
                self.send("leave")

    def shop_panel(self,me):
        ui=self.ui
        ui.modal_shade()
        ui.panel((208,138,864,489))
        ui.text("서리 상점",236,158,28,WHITE,True)
        ui.text(f"{int(me['gold'])} G   ·   {len(me['items'])} / 6 슬롯",650,169,20,GOLD)
        if ui.button("닫기",(932,157,112,37),size=15):
            self.shop=False
        allowed=me["hp"]<=0 or (me["shop_allowed"] and abs(me["x"]-(-55 if me["team"]==0 else 55))<6)
        ui.text("출발 전 또는 사망 중에 구매 가능합니다." if allowed else "전장에 출발했습니다. 사망한 뒤 다시 구매할 수 있습니다.",236,215,16,MUTED if allowed else GOLD)
        for index,(key,item) in enumerate(ITEMS.items()):
            x=232+(index%3)*276
            y=258+(index//3)*144
            ui.panel((x,y,264,131),(11,23,36),LINE,7)
            ui.text(f"{index+1}  {item['name']}",x+13,y+10,19,WHITE,True)
            ui.text(item["description"],x+13,y+44,13,MUTED)
            enabled=allowed and me["gold"]>=item["cost"] and len(me["items"])<6 and not(item.get("unique") and key in me["items"])
            if ui.button(f"{item['cost']} G 구매",(x+12,y+78,240,37),primary=True,enabled=enabled,size=16):
                self.action("buy",item=key)
        names=" · ".join(ITEMS[key]["name"] for key in me["items"])
        ui.text("보유: "+(names or "없음"),236,568,14,MUTED)

    def scores(self,heroes):
        ui=self.ui
        ui.modal_shade()
        ui.panel((245,154,790,485))
        ui.text("전투 현황",275,176,28,WHITE,True)
        ui.text("플레이어                                 레벨        K / D / A         골드",280,226,15,MUTED)
        for i,hero in enumerate(sorted(heroes,key=lambda h:h["team"])):
            y=267+i*34
            ui.text(hero["name"],281,y,16,BLUE if hero["team"]==0 else RED)
            ui.text(str(hero["level"]),638,y,16)
            ui.text(f"{hero['kills']} / {hero['deaths']} / {hero['assists']}",735,y,16)
            ui.text(str(int(hero["gold"])),941,y,16,GOLD)

    def quick_update(self,state):
        if not self.quick or not self.client.id:
            return
        room=state["room"]
        if self.quick_step==0 and not room:
            self.send("create",name="봇 연습 · 서리 다리",capacity=1)
            self.quick_step=1
        elif self.quick_step==1 and room:
            self.send("fill")
            self.send("start")
            self.quick=False

    def frame(self,dt):
        raw=pygame.event.get()
        size=pygame.display.get_window_size()
        self.renderer.size=(max(1,size[0]),max(1,size[1]))
        events=[]
        for event in raw:
            if event.type==pygame.QUIT:
                self.running=False
            if event.type in (pygame.MOUSEBUTTONDOWN,pygame.MOUSEBUTTONUP,pygame.MOUSEMOTION):
                data=event.dict.copy()
                data["pos"]=self.renderer.layout.to_ui(event.pos)
                event=pygame.event.Event(event.type,data)
            events.append(event)
        mx,my=pygame.mouse.get_pos()
        self.mouse=self.renderer.layout.to_ui((mx,my))
        if self.client:
            self.client.pump()
            for error in self.client.errors:
                self.tell(error)
            self.client.errors.clear()
            if not self.client.connected:
                self.disconnect()
        state=self.client.state if self.client else None
        room=state["room"] if state else None
        self.phase=room["phase"] if room else "lobby" if self.client else "home"
        if self.phase!=self.last_phase:
            self.renderer.set_game_mode(self.phase=="game")
            self.mouse=self.renderer.layout.to_ui(pygame.mouse.get_pos())
            # Do not reuse clicks mapped against the previous window size.
            events=[event for event in events if event.type not in
                    (pygame.MOUSEBUTTONDOWN,pygame.MOUSEBUTTONUP,pygame.MOUSEMOTION)]
            self.shop=self.menu=self.scoreboard=False
            self.ui.focus=None
            if self.phase=="game":
                self.renderer.positions.clear()
                self.renderer.follow=False
                me=next((u for u in state["world"]["units"] if u["id"]==self.client.id),None)
                if me:
                    self.renderer.camera=[me["x"],me["z"]]
            self.last_phase=self.phase
        pygame.event.set_grab(self.phase=="game" and pygame.key.get_focused())
        self.ui.begin(events,self.mouse,transparent=self.phase=="game")
        if self.phase=="home":
            self.home()
        elif self.phase=="lobby":
            self.lobby(state)
        elif self.phase=="room":
            self.room(room)
        elif self.phase=="select":
            self.selection(room)
        elif self.phase=="game" and state["world"]:
            world=state["world"]
            me=next((u for u in world["units"] if u["id"]==self.client.id),None)
            self.match_input(events,world,me,dt)
            self.renderer.draw_world(world,me,dt,self.renderer.ground(self.mouse))
            self.hud(world,me,room)
        if state:
            self.quick_update(state)
        if self.renderer.asset_errors:
            self.tell(self.renderer.asset_errors.pop(0))
        if time.monotonic()<self.toast_until:
            self.ui.panel((220,84,840,48),(42,34,31),GOLD,8)
            self.ui.text(self.toast[:85],640,97,16,GOLD,center=True)
        self.renderer.overlay(self.ui.surface,opaque=self.phase!="game",modal_layers=self.ui.modal_layers)

    def close(self):
        if self.client:
            self.client.close()
        if self.server:
            self.server.stop()
        self.renderer.close()
        pygame.quit()

    def run(self,smoke=False):
        start=time.monotonic()
        captured=set()
        smoke_at=start+.4
        screenshot_dir=ROOT/"artifacts"
        if smoke:
            screenshot_dir.mkdir(exist_ok=True)
            self.server=GameServer("127.0.0.1",0).start()
        while self.running:
            dt=min(.1,self.clock.tick(60)/1000)
            self.frame(dt)
            if smoke and time.monotonic()>=smoke_at:
                if self.phase not in captured:
                    self.renderer.screenshot(screenshot_dir/f"{self.phase}.png")
                    captured.add(self.phase)
                if self.phase=="home":
                    self.connect(local=True)
                elif self.phase=="lobby":
                    self.send("create",name="테스트 전장",capacity=5)
                elif self.phase=="room":
                    self.send("fill")
                    self.send("start")
                elif self.phase=="select":
                    self.send("pick",champion="mage")
                    self.send("lock")
                elif self.phase=="game":
                    self.action("buy",item="crystal")
                    self.action("attack_move",point=[0,1])
                    self.running=False
                smoke_at=time.monotonic()+.8
            pygame.display.flip()
            if smoke and time.monotonic()-start>15:
                raise RuntimeError(f"Smoke test timed out in {self.phase}: {self.toast}")
        if smoke:
            if captured!={"home","lobby","room","select","game"}:
                raise RuntimeError(f"Incomplete smoke test: {captured}")
            print("SMOKE PASS: home -> lobby -> room -> select -> OpenGL game; screenshots: artifacts/")


def main():
    parser=argparse.ArgumentParser(description="Frostbridge · 서리 다리")
    parser.add_argument("--smoke-test",action="store_true",help="Run a hidden end-to-end rendering check")
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(levelname)s: %(message)s")
    app=None
    try:
        app=App(hidden=args.smoke_test)
        app.run(smoke=args.smoke_test)
    except pygame.error as error:
        raise SystemExit(f"그래픽 초기화 실패: {error}\nOpenGL 2.1 이상을 지원하는 그래픽 드라이버가 필요합니다.") from error
    finally:
        if app:
            app.close()


if __name__=="__main__":
    main()
