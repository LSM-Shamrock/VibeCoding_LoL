"""조작키 설정: 행동 → 물리 키(scancode). keybinds.json 에 저장된다.

scancode 로 저장하므로 한글 입력 모드나 자판 배열과 상관없이 같은 위치의 키로 동작한다.
"""
import json
import os

import pygame

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(ROOT, "keybinds.json")

# (행동, 설정 창에 보일 이름) — 화면에 나오는 순서
ACTIONS = [
    ("Q", "스킬 Q"), ("W", "스킬 W"), ("E", "스킬 E"), ("R", "스킬 R"),
    ("D", "점멸"), ("F", "표식"), ("recall", "귀환"),
    ("attack_move", "공격 이동"), ("stop", "정지"),
    ("shop", "상점"), ("score", "점수판"),
    ("cam_lock", "카메라 고정 전환"), ("cam_center", "카메라 내 챔피언"),
]
DEFAULTS = {
    "Q": (pygame.KSCAN_Q, "Q"), "W": (pygame.KSCAN_W, "W"), "E": (pygame.KSCAN_E, "E"), "R": (pygame.KSCAN_R, "R"),
    "D": (pygame.KSCAN_D, "D"), "F": (pygame.KSCAN_F, "F"), "recall": (pygame.KSCAN_B, "B"),
    "attack_move": (pygame.KSCAN_A, "A"), "stop": (pygame.KSCAN_S, "S"),
    "shop": (pygame.KSCAN_P, "P"), "score": (pygame.KSCAN_TAB, "Tab"),
    "cam_lock": (pygame.KSCAN_Y, "Y"), "cam_center": (pygame.KSCAN_SPACE, "Space"),
}
RESERVED = {pygame.KSCAN_ESCAPE}     # ESC 는 설정 창 열기/닫기 전용


def key_name(e):
    """키 이벤트를 화면에 보일 이름으로 (알파벳은 물리 위치 기준 대문자)."""
    sc = getattr(e, "scancode", 0)
    if pygame.KSCAN_A <= sc <= pygame.KSCAN_Z:
        return chr(ord("A") + sc - pygame.KSCAN_A)
    if pygame.KSCAN_1 <= sc <= pygame.KSCAN_9:
        return str(sc - pygame.KSCAN_1 + 1)
    if sc == pygame.KSCAN_0:
        return "0"
    name = pygame.key.name(e.key) if e.key else ""
    return name.title() if name else f"#{sc}"


class KeyBinds:
    def __init__(self):
        self.binds = dict(DEFAULTS)
        self.spells_swapped = False     # True 면 D 키에 표식, F 키에 점멸 (챔피언 선택 화면에서 변경)

    @classmethod
    def load(cls):
        kb = cls()
        try:
            with open(PATH, encoding="utf-8") as f:
                data = json.load(f)
            kb.spells_swapped = bool(data.pop("_spells_swapped", False))
            for action, (sc, name) in data.items():
                if action in DEFAULTS:
                    kb.binds[action] = (int(sc), str(name))
            # 저장 파일에 없는 새 행동(예: 귀환)의 기본 키와 겹치면, 겹친 쪽을 그 행동의 기본 키로 되돌린다
            for new in (a for a in DEFAULTS if a not in data):
                for other, (sc, _) in kb.binds.items():
                    if other != new and sc == DEFAULTS[new][0]:
                        kb.binds[other] = DEFAULTS[other]
        except (OSError, ValueError, TypeError):
            pass
        return kb

    def save(self):
        try:
            with open(PATH, "w", encoding="utf-8") as f:
                data = {a: list(v) for a, v in self.binds.items()}
                data["_spells_swapped"] = self.spells_swapped
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def action(self, e):
        """키 이벤트에 해당하는 행동 (없으면 None)."""
        sc = getattr(e, "scancode", 0)
        return next((a for a, (s, _) in self.binds.items() if s == sc), None)

    def name(self, action):
        return self.binds[action][1]

    def assign(self, action, e):
        """행동에 새 키를 지정한다. 이미 다른 행동이 쓰던 키면 서로 맞바꾼다. 실패 시 False."""
        sc = getattr(e, "scancode", 0)
        if not sc or sc in RESERVED:
            return False
        old = self.binds[action]
        for other, (s, _) in self.binds.items():
            if s == sc and other != action:
                self.binds[other] = old
        self.binds[action] = (sc, key_name(e))
        self.save()
        return True

    def spell_at(self, slot):
        """D/F 자리(키)에 들어 있는 주문 id ("D" 점멸, "F" 표식)."""
        if self.spells_swapped:
            return "F" if slot == "D" else "D"
        return slot

    def swap_spells(self):
        self.spells_swapped = not self.spells_swapped
        self.save()

    def reset(self):
        self.binds = dict(DEFAULTS)
        self.save()
