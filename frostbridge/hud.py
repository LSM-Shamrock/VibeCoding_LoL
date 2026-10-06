"""Compact arena HUD: abilities, resources, summoners and real inventory slots."""
import math
import pygame

from .content import CHAMPIONS, ITEMS
from .display import HUD_RECT
from .ui import WHITE, MUTED, CYAN, GOLD

FRAME=(103,91,60)
INK=(9,18,24,248)


def icon(surface,kind,rect,tint):
    """Original vector symbols; these can later be replaced by game art."""
    r=pygame.Rect(rect)
    cx,cy=r.center
    radius=min(r.width,r.height)*.32
    def p(x,y):
        return (round(cx+x*radius),round(cy+y*radius))
    if kind in ("bolt","sword"):
        pygame.draw.polygon(surface,tint,[p(.5,-1),p(.13,-.2),p(.62,-.2),p(-.55,1),p(-.15,.12),p(-.65,.12)])
    elif kind in ("shield","armor"):
        pygame.draw.polygon(surface,tint,[p(-.8,-.8),p(.8,-.8),p(.65,.4),p(0,1),p(-.65,.4)],2)
        pygame.draw.line(surface,tint,p(0,-.55),p(0,.65),2)
    elif kind=="heal":
        pygame.draw.line(surface,tint,p(-.85,0),p(.85,0),4)
        pygame.draw.line(surface,tint,p(0,-.85),p(0,.85),4)
    elif kind in ("dash","boots"):
        for shift in (-.45,.4):
            pygame.draw.lines(surface,tint,False,[p(-.4+shift,-.8),p(.3+shift,0),p(-.4+shift,.8)],3)
    elif kind=="cone" or kind=="bow":
        pygame.draw.arc(surface,tint,r.inflate(-r.width*.25,-r.height*.25),-.9,1.6,3)
        pygame.draw.line(surface,tint,p(-.7,.7),p(.7,-.7),2)
    elif kind=="snowball":
        for angle in (0,math.pi/3,2*math.pi/3):
            dx,dy=math.cos(angle)*.85,math.sin(angle)*.85
            pygame.draw.line(surface,tint,p(-dx,-dy),p(dx,dy),2)
        pygame.draw.circle(surface,tint,(cx,cy),3)
    elif kind=="crown":
        pygame.draw.polygon(surface,tint,[p(-1,-.5),p(-.6,.65),p(.6,.65),p(1,-.5),p(.4,-.05),p(0,-.9),p(-.4,-.05)],2)
    else:
        pygame.draw.polygon(surface,tint,[p(0,-1),p(.7,0),p(0,1),p(-.7,0)],2)
        pygame.draw.circle(surface,tint,(cx,cy),3)


def draw_champion_hud(ui,me,mouse):
    """Returns True when the gold/shop control is clicked."""
    ui.panel(HUD_RECT,INK,FRAME,6)
    ui.portrait(me["champion"],(309,610,64,88))
    ui.panel((350,685,25,22),(21,30,30),GOLD,3)
    ui.text(str(me["level"]),362,686,13,GOLD,True,center=True)
    ui.text(CHAMPIONS[me["champion"]]["name"],386,609,17,WHITE,True)
    for y,label,value in [(637,"공격",int(me["damage"])),(659,"방어",int(me["armor"])),(681,"주문",int(me["power"]))]:
        ui.text(label,386,y,11,MUTED)
        ui.text(str(value),447,y,12,WHITE)
    spec=CHAMPIONS[me["champion"]]
    tooltip=None
    for slot,key in enumerate("QWERDF"):
        x=482+slot*54 if slot<4 else 704+(slot-4)*38
        rect=pygame.Rect(x,610,48 if slot<4 else 34,48 if slot<4 else 43)
        skill=spec["skills"][slot] if slot<4 else None
        cd=me["cooldowns"][slot]
        locked=slot==3 and me["level"]<6
        mark=slot==4 and me["mark_time"]>0
        usable=me["hp"]>0 and not locked and (mark or cd<=0) and (not skill or me["mana"]>=skill["cost"])
        tint=spec["color"] if slot<4 else (192,227,243) if slot==4 else (240,203,91)
        kind=skill["kind"] if skill else "snowball" if slot==4 else "bolt"
        ui.panel(rect,(23,38,45) if usable else (13,23,31),FRAME,3)
        icon(ui.surface,kind,rect,tint if usable else (70,83,91))
        if cd>0 and not mark:
            ui.text(str(math.ceil(cd)),rect.centerx,rect.y+10,21,WHITE,True,center=True)
        elif locked:
            ui.text("6",rect.centerx,rect.y+10,21,MUTED,True,center=True)
        elif mark:
            ui.text("도약",rect.centerx,rect.y+10,11,CYAN,True,center=True)
        # Only the small bound-key badge stays; instructional sentences are hidden.
        ui.panel((x+2,rect.bottom-13,16,12),(6,12,17),None,2)
        ui.text(key,x+10,rect.bottom-15,10,WHITE,center=True)
        if rect.collidepoint(mouse):
            title=skill["name"] if skill else "표식 · 돌진" if slot==4 else "점멸"
            detail=skill["description"] if skill else "적중한 적에게 재사용하면 돌진합니다." if slot==4 else "마우스 방향으로 짧게 순간이동합니다."
            footer=f"마나 {skill['cost']}  ·  재사용 {skill['cooldown']}초" if skill else "재사용 45초" if slot==4 else "재사용 90초"
            tooltip=(title,detail,footer)
    ui.bar((482,664,292,15),me["hp"],me["max_hp"],(54,152,84))
    ui.text(f"{int(me['hp'])} / {int(me['max_hp'])}",628,663,11,WHITE,center=True)
    ui.bar((482,682,292,13),me["mana"],me["max_mana"],(49,106,190))
    ui.text(f"{int(me['mana'])} / {int(me['max_mana'])}",628,680,10,WHITE,center=True)
    ui.bar((482,702,292,3),me["xp"] if me["level"]<18 else 1,100+me["level"]*45 if me["level"]<18 else 1,(190,167,87))
    item_colors={"sword":(188,216,233),"crystal":(170,140,242),"armor":(112,175,205),"boots":(202,181,123),"bow":(145,208,153),"crown":(226,190,109)}
    for index in range(6):
        rect=pygame.Rect(798+(index%3)*39,608+(index//3)*38,34,34)
        ui.panel(rect,(14,25,31),FRAME,3)
        if index<len(me["items"]):
            key=me["items"][index]
            icon(ui.surface,key,rect,item_colors[key])
            if rect.collidepoint(mouse):
                tooltip=(ITEMS[key]["name"],ITEMS[key]["description"],"보유 아이템 · 지속 효과")
        else:
            pygame.draw.circle(ui.surface,(35,48,54),rect.center,2)
    clicked=ui.button(f"{int(me['gold']):,} G",(798,687,112,22),size=12)
    if pygame.Rect(798,687,112,22).collidepoint(mouse):
        tooltip=("상점", "아이템을 구매합니다.","출발 전 또는 사망 중 이용 가능")
    if tooltip:
        ui.panel((480,493,445,96),(8,17,24,250),FRAME,5)
        ui.text(tooltip[0],495,503,17,GOLD,True)
        ui.text(tooltip[1],495,534,13,WHITE)
        ui.text(tooltip[2],495,562,12,MUTED)
    return clicked
