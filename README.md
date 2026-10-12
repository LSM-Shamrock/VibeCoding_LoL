# 칼바람 아레나 (파이게임 3D)

리그 오브 레전드 '칼바람 나락'을 모티브로 한 3D 멀티플레이 게임입니다.
pygame(창·입력) + moderngl(OpenGL 3D 렌더링) 조합으로 만들었습니다.

## 실행

```bash
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

- **서버 열고 시작 (방장)**: 서버 주소를 비우고 시작하면 이 컴퓨터에서 서버를 띄우고, 로비 없이 내 방을 자동으로 만들어 바로 대기실로 갑니다. (한 호스트당 방 하나. 방장이 방을 나가면 서버도 닫힙니다.)
- **서버에 접속**: 친구가 연 서버 주소(타이틀 화면 아래에 표시되는 IP)로 접속하면 로비에서 방 목록이 보이고 입장합니다. 주소칸에 `192.168.0.5:6000` 처럼 포트까지 적어도 됩니다. 같은 네트워크(LAN)에서 동작하며, 포트 5555/TCP 를 방화벽에서 허용해야 합니다.
- 화면 없이 서버만 실행하려면 `py server.py [포트]`

## 게임 흐름

1. 방장은 로비 없이 바로 방이 만들어지고, 접속한 사람은 로비의 방 목록에서 입장(더블클릭 가능). 전용 서버(`py server.py`)에서는 로비에서 방을 직접 만들 수도 있습니다
2. 방에서 팀 이동, 방장은 빈자리에 **봇 추가/제거**, 팀 인원 변경
3. 방장이 **게임 시작** → 모든 플레이어가 챔피언 선택 후 확정 (40초 제한, 봇은 자동 선택)
4. 게임 플레이 → 넥서스 파괴 시 승패 표시 → 8초 뒤 방으로 복귀

## 조작

| 키 | 기능 |
|---|---|
| 우클릭 | 이동 / 적 클릭 시 공격 (누르고 있으면 계속 이동) |
| Q W E R | 누르는 동안 범위 표시, 떼면 마우스 방향으로 시전 (자기 주변 스킬은 즉시, 아군 지정 스킬은 마우스에서 가장 가까운 아군에게, 먼 거리 순간이동은 미니맵을 눌러도 가능) |
| Ctrl + Q/W/E/R | 스킬 레벨 업 (HUD 의 노란 + 버튼 클릭도 가능) |
| D / F | 챔피언 선택 화면에서 고른 소환사 주문 두 개 (기본: 점멸 / 표식). 표식은 맞힌 뒤 한 번 더 누르면 대상에게 돌진 |
| ESC | 설정 창: "조작키" 탭(키 바꾸기)과 "사운드" 탭(효과음 크기·끄기) |
| A + 좌클릭 | 공격 이동 |
| S | 정지 |
| B | 상점 |
| Tab | 점수판 |
| Y / Space / 휠 | 카메라 고정 토글 / 내 챔피언 보기 / 줌 |
| 화면 끝에 마우스 | 카메라 고정 해제 상태에서 그 방향으로 카메라 이동 (방향키도 가능) |
| 미니맵 | 좌클릭(누른 채 드래그 가능) 카메라 이동, 우클릭(누르고 있으면 계속) 이동 명령 |
| Alt + Enter | 전체 화면 / 창 모드 전환 |

로비·방·챔피언 선택은 창 모드, 인게임은 롤처럼 전체 화면(테두리 없는 바탕화면 해상도)으로 자동 전환되며,
인게임 중에는 화면 끝 카메라 이동을 위해 마우스 커서가 게임 화면 밖으로 나가지 않습니다 (Alt+Tab 으로 전환 가능).

## 구현된 칼바람 규칙

- 단일 라인: 외곽 포탑 → 내부 포탑 → 억제기 → 쌍둥이 포탑 → 넥서스 (앞 구조물을 부숴야 다음 구조물에 피해가 들어감)
- 레벨 3, 1400 골드로 시작, 귀환 없음
- **상점은 사망 중이거나 우물 안에서만** 이용 가능, 우물에서 체력 회복 없음
- **아이템 트리 (1단계 → 2단계)**: 2단계 아이템은 `data/items.json` 의 `from` 에 적힌 1단계 재료로 만듭니다. 재료를 가지고 있으면 사는 순간 자동으로 소모되고 그만큼 값이 깎입니다(총 가격은 그대로). 상점에서 아이템에 마우스를 올리면 오른쪽에 재료 트리가 보입니다.
- 라인의 **체력 회복 구슬(유물)**: 1분 후 생성, 먹으면 40초 후 재생성
- 30초마다 미니언 웨이브(근접 3, 원거리 3, 3웨이브마다 대포), 억제기 파괴 시 슈퍼 미니언, 억제기는 5분 후 재생성
- 포탑 어그로(아군 챔피언을 공격한 적 챔피언을 우선 공격), 연속 피격 시 포탑 피해 증가
- 킬/어시스트/선취점 골드, 미니언 막타 골드, 주변 경험치 공유, 패시브 골드·경험치
- 적 우물 레이저, 레벨 비례 부활 대기 시간
- 소환사 주문: 선택 화면에서 8종 중 2개를 골라 D / F 에 넣음 (아래 "소환사 주문" 참고)

## 소환사 주문

챔피언 선택 화면 가운데 아래의 두 칸(D, F)을 누르면 주문 목록이 열리고, 아이콘에 마우스를 올리면 설명이 보입니다.
이미 다른 칸에 있는 주문을 고르면 두 칸이 서로 바뀝니다. 고른 주문은 이 PC 의 `keybinds.json` 에 저장되어 다음에도 그대로입니다.

| 주문 | 효과 | 재사용 |
|---|---|---|
| 점멸 | 마우스 방향으로 400 만큼 순간이동 | 240초 |
| 표식 | 눈덩이를 던져 피해(10 + 레벨×5)와 표식, 3초 안에 다시 누르면 대상에게 돌진 | 40초 |
| 회복 | 내 체력 80 + 레벨×14 회복, 근처(600) 가장 체력이 낮은 아군은 절반, 둘 다 1초간 이동 속도 +30% | 240초 |
| 유체화 | 8초간 이동 속도 +30% | 210초 |
| 방어막 | 2초간 보호막 100 + 레벨×22 | 180초 |
| 정화 | 기절·속박·침묵·둔화·공중 띄움을 풀고 0.5초간 군중 제어 면역 (기절 중에도 사용 가능) | 210초 |
| 탈진 | 마우스에서 가장 가까운 적 챔피언(사거리 650)의 이동 속도 -30%, 주는 피해 -35% (2.5초) | 210초 |
| 점화 | 가장 가까운 적 챔피언(사거리 600)에게 5초간 고정 피해 50 + 레벨×20, 받는 회복량 -40% | 180초 |

- 숫자는 `game/shared/constants.py`, 이름·설명·아이콘 색은 `game/shared/spells.py`, 효과는 `game/server/sim.py` 의 `cast_spell` / `spell_*` 에 있습니다.
- 봇은 점멸과 무작위 주문 하나를 들고 나오며, 체력·교전 상황을 보고 알아서 씁니다.
- 새 주문을 만들려면 `spells.py` 의 `SPELLS` 에 항목을 넣고, `sim.py` 에 `spell_<id>(c, x, z)` 함수(성공하면 True)를 추가한 뒤
  `assets/ui/spells/<id>.png` 아이콘을 넣으면 됩니다.

## 스킬 이펙트 색

- 아군이 쓴 스킬의 이펙트(범위·투사체·장판·보호막 등)는 주로 **파랑**, 적이 쓴 스킬은 주로 **빨강**으로 보입니다.
  스킬 고유의 색은 조금만 섞여 있어서 종류는 모양과 색감으로 구별됩니다.
- 피해 없이 효과만 주는 스킬(회복·보호막·강화·이동·정화 등)은 피해를 주는 스킬보다 **더 연하고 투명하게** 그려집니다.
- 서버가 이펙트 이벤트에 `tm`(스킬을 쓴 팀)을 담아 보내고, 색 규칙은 `game/client/scenes/game.py` 맨 위의
  `TEAM_FX`, `SUPPORT_FX`, `SUPPORT_ALPHA` 에서 바꿀 수 있습니다.

## 스킬 스프라이트 이펙트
- `game/client/vfx.py`: 텍스처 쿼드 기반 VFX(바닥/빌보드, 파티클, 투사체 트레일). 스킬별로 컨셉에 맞는 이펙트(불꽃, 번개, 칼날, 치유 등)를 재생합니다.
- 스프라이트 31종은 `python tools/build_fx_sprites.py`(pillow+numpy)로 `assets/fx/`에 생성합니다.
- 팀색/지원 이펙트 반투명 규칙(`fx_color`)은 그대로 적용됩니다.

## 근접 챔피언 버프
- 01~04번 챔피언(근접 위주)의 체력/방어/공격 수치 상향, 스킬 피해 x1.2, 쿨타임 단축. 수치는 `data/champions/*.json`에서 조정합니다.

## 팀 프레임 UI (롤 방식)
- 미니맵의 챔피언 초상화는 둘레가 원형 체력 표시입니다 (12시부터 시계 방향으로 남은 체력만큼 팀 색, 내 챔피언은 초록).
- 시야 밖 어둠(전장의 안개)은 칸마다 거리에 따라 0~1로 부드럽게 계산해 가장자리가 번지듯 어두워집니다.
- 미니맵 위 오른쪽 정렬: 아군 초상화 아래에 짧은 체력/마나 바. 자신은 죽었을 때만 표시됩니다.
- 죽은 아군/적은 흑백 아이콘 + 부활까지 남은 초. 죽은 적은 아군 줄 위에 별도 표시됩니다.
- 아이콘은 `assets/ui/portraits/<챔피언id>.png` (3D 모델을 머리~어깨 구도로 렌더링). 모델을 바꾼 뒤 `python tools/build_portraits.py` 를 다시 실행하면 갱신됩니다. 파일이 없으면 색 사각형 + 첫 글자로 대신 나옵니다.

## BGM
- `assets/music/bgm_menu.ogg` (타이틀·로비·방·챔피언 선택), `bgm_game.ogg` (인게임, 결과가 나오면 서서히 꺼짐).
- 외부 음원 없이 `python tools/build_bgm.py` (numpy+scipy, ffmpeg 필요)로 직접 작곡·합성한 곡입니다 (메뉴: C장조 계열 밝은 곡 84bpm, 인게임: A단조 140bpm). 코드 진행/선율은 그 파일에서 고칠 수 있습니다.
- 일반 공격·미니언 공격 소리는 원래의 40% 크기입니다 (`game/client/scenes/game.py` 의 `ATTACK_SFX_VOL`, 미니언 투사체 소리는 `sounds.json` 의 `vol`).
- 음량은 ESC 설정의 소리 크기·음소거를 따라가며 효과음의 35% 크기로 나옵니다 (`audio.py` 의 `MUSIC_GAIN`).
- 다른 곡을 쓰려면 같은 이름의 `.ogg` 로 바꿔 넣으면 됩니다.

## 아이콘

스킬 32개, 소환사 주문 8개, 능력치 8개의 아이콘은 **game-icons.net (CC BY 3.0)** 의 그림에 색과 배경을 입혀 만든 PNG 입니다
(`assets/ui/skills/<챔피언>_<Q|W|E|R>.png`, `assets/ui/spells/<주문>.png`, `assets/ui/stats/<능력치>.png`).
어느 아이콘을 어디에 썼는지와 작가는 `assets/ui/CREDITS.md` 에 있습니다. 챔피언 선택 화면에서는 아이콘과 이름만 보이고,
마우스를 올리면 자세한 설명이 뜹니다. 게임 화면의 스킬·주문·능력치 패널에도 같은 아이콘을 씁니다.

### 마우스 커서와 안내 메시지

- 로비·방·선택 화면 등 인게임이 아닐 때는 일반 윈도우 커서입니다. 인게임에서는 시스템 커서 대신 `assets/ui/cursors/` 의 세 가지를 씁니다: 평상시 손(Phosphor Icons, MIT), 공격할 수 있는 적 위에서는 칼, 대상 지정 스킬(`"aim": "enemy"`/`"ally"`) 조준 중에는 조준경. 이미지는 `python tools/build_cursors.py --src <gameicons 폴더> --phosphor <phosphor 폴더>` 로 다시 만들 수 있고, 클릭 지점은 `game/client/cursors.py` 의 `HOTSPOTS` 입니다.
- 스킬 키를 뗐는데 발동하지 않으면 스킬 바 위에 이유가 뜹니다 (배우지 않음 / 기절 / 침묵 / 재사용 대기 / 마나 부족 / 사거리 안에 대상 없음).

아이콘을 바꾸려면 PNG 파일을 같은 이름으로 덮어쓰거나, `tools/build_icons.py` 위쪽 표의 "작가/아이콘 이름" 을 고치고
`python tools/build_icons.py --src <game-icons 저장소 폴더>` 로 다시 만드세요 (사용법은 스크립트 맨 위에 있습니다).
PNG 가 없으면 게임은 예전처럼 글자 아이콘으로 대신 보여 줍니다.

## 챔피언

지금 선택 화면에 나오는 챔피언은 **거미 여왕**, **이무기**, **용** 셋입니다. 보스러시 게임(`VibeCoding_BossRush_Pygame`)의 보스 세 마리를 챔피언으로 옮겼고,
기존 7명은 코드·모델·스킬을 그대로 두고 **선택 화면, 방, 봇 선택에서만 숨겨 두었습니다** (JSON 에 `"hidden": true`).
다시 보이게 하려면 `data/champions/01~07*.json` 의 `"hidden": true` 줄을 지우세요 (테스트 코드는 숨긴 챔피언도 직접 불러 씁니다).

### 거미 여왕 (`spider`) — 보스러시 "동굴 여왕 거미" 이식

절차적 애니메이션 보스를 챔피언으로 옮긴 첫 번째 사례입니다. 뼈대 모델 파일이 없고, 8개 다리의 2관절 IK·걸음 순서·자세 섞기(웅크림/점프/펼치기/탄막 …)를
매 프레임 계산해 부품마다 행렬을 그립니다 (`game/client/rigs/spider.py`, 보스 원본 단위 × `SC` 로 줄임). 폭발하며 흩어지는 사망 연출도 같이 옮겼습니다.
챔피언 JSON 에 `"model": {"rig": "spider"}` 라고 적으면 이 방식으로 그립니다 (`game/client/rigs/__init__.py` 의 `make_rig`).

| 스킬 | 이름 | 내용 |
|---|---|---|
| Q | 독침 뿌리기 | 앞쪽 부채꼴로 독침 5발 (`volley`). 범위 표시에 침이 날아가는 길이 선으로 나옴. 가까울수록 여러 발이 맞음 |
| W | 거미줄 장판 | 4.5초짜리 장판, 반경 2.2 (`zone` + `damage_per_sec`). 안의 적은 둔화 + 초당 독 피해 (보스의 R 장판을 줄이고 약하게 만든 것) |
| E | 새끼 거미 고치 | 마우스 위치에 시전 방향과 수직(T자)으로 고치 3개 (`cocoon`). 체력바가 있어 평타·스킬로 부술 수 있고(`cocoon_hp`), 6.5초 뒤 부화하면 새끼 거미(`spiderling`, 거미 여왕을 줄인 모양과 같은 다리 걸음)가 거미 여왕보다 살짝 느린 속도(`baby_speed` 3.3)로 가장 가까운 적에게 다가가 거미 여왕과 같은 거미줄 평타(`web_shot`, 사거리 3.2, 피해 `baby_ad` + 공격력의 `baby_ad_ratio`)로 공격합니다. 새끼 거미는 자폭하지 않고, 시간이 지나도 사라지지 않으며 적에게 죽어야 없어집니다 (`max_babies` 12마리까지) |
| R | 덮쳐 내려찍기 | 지정한 적 챔피언에게 0.3초 웅크렸다가 약 1초(`flight`) 동안 높이 뛰어올라 내려찍기 (`leap_slam` + `"aim": "enemy"`). 착지 지점 반경 `radius` 2.4 안은 즉시 광역 피해·둔화(지정 대상은 스턴), 그보다 넓은 반경 3.5 에 독 거미줄 장판(`zone` 하위 값). R 을 누르고 있으면 안쪽(진함)·바깥쪽(연함) 두 범위가 대상 위에 표시되고 (대상이 없으면 사거리 원이 빨개짐), 도약 중에도 착지 지점에 표시됩니다 |

아직 옮기지 않은 것: 포효, 경직(스태거) 연출 (알·새끼 거미는 E 스킬로 옮겼습니다).

### 이무기 (`serpent`) — 보스러시 "심연의 이무기" 이식

거미 여왕과 같은 절차적 리그 방식입니다 (`game/client/rigs/serpent.py`, 보스 원본 단위 × `SC` 0.20). 가늘고 긴 몸통은 **머리가 지나온 길(궤적)** 을 따라가는 관 모양으로 매 프레임 다시 만들고
(몸 둘레 고리 35개 · 흰 비늘 바탕에 청록 등 무늬와 옆구리 눈 무늬 텍스처), 몸이 자기 몸 위로 겹쳐 쌓이는 칸 계산, 땅속으로 가라앉을 때 머리부터 물결처럼 몸이 잠기는 파동,
사망 시 머리·몸 조각이 흩어지는 연출도 옮겼습니다. 챔피언 JSON 의 `"model": {"rig": "serpent"}`.

서 있을 때(대기·시전)는 **ㄴ자 자세** 입니다. 몸의 약 절반을 머리 아래로 곧게 세우고, 둥글게 꺾여 땅에 누운 나머지 몸은 S자로 구불거리며 꼬리로 이어져 뒤로 차지하는 길이가 짧습니다
(`_pose_curve`: 세운 높이 `lift`, 꺾임 반지름 `BEND_R`, S자 폭·촘촘함 `WAVE_A`·`WAVE_K`). 자세 값 `fold` 가 1 이면 이 모양, 0 이면 머리가 지나온 길을 그대로 따라가서
(이동·돌진) 달리다 멈추면 몸이 다시 접히고, 움직이기 시작하면 접힌 모양에서 이어서 펴집니다. 달리는 중에도 몸이 옆으로 물결치며 앞뒤 간격이 줄어듭니다.
머리가 높이 솟으므로 체력바·마우스 선택 높이는 리그의 `bar_h`·`pick_h` 로 정합니다.

| 스킬 | 이름 | 내용 |
|---|---|---|
| Q | 독 뱉기 | 독액 덩어리를 포물선(`flight` 0.7초)으로 뱉어 착지 지점(반경 2.2)에 피해 + 6초짜리 독 웅덩이 (`spit_pool`, 웅덩이는 `zone` 의 `style: "venom"`). 위에 선 적은 둔화 + 초당 피해 |
| W | 일직선 돌진 | 0.4초 몸을 쳐들며 예고선을 보여 준 뒤 사거리 7.5 를 직선으로 돌진 (`lunge`). 지나는 길의 적은 한 번씩 물어뜯겨 피해 + 둔화 (돌진 중 매 틱 `sweep_hit`) |
| E | 내려찍기 | 머리를 높이 쳐들었다가(0.75초, 목이 늘어남) 지정한 곳(사거리 5.5)에 내리꽂음 (`serpent_slam`). 반경 2.6 한가운데는 피해 + 기절, 이어 충격파 고리가 반경 5.2 까지 퍼지며 절반 피해 + 둔화 |
| R | 잠행 | 머리부터 땅속으로 가라앉아(0.6초, 이동 중 대상 지정 불가) 지정한 곳(사거리 14, 미니맵 가능)에서 솟구침 (`dive`, `"aim": "teleport"`). 반경 3.0 안의 적은 피해 + 공중으로 띄움. 도착 지점이 바닥에 표시됨 |

서버는 연출용 이벤트 (`lunge`, `serpent_rear`, `dive`, `dive_out`) 를 보내고, 리그가 `on_fx` 로 받아 자세를 바꿉니다 (`game/client/scenes/game.py` 의 `handle_fx`). 효과음은 `data/sounds.json`
(`atk_bite`, `cast_spit`, `fx_splat`, `fx_sink` 등).

아직 옮기지 않은 것: 경직(스태거) 연출.

### 용 (`dragon`) — 보스러시 "겁화의 용" 이식

세 번째 절차적 리그입니다 (`game/client/rigs/dragon.py` 가 움직임, `dragon_assets.py` 가 머리·날개·다리 부품과 무늬, 보스 원본 단위 × `SC` 0.075). 몸통은 이무기처럼
**가슴이 지나온 길(궤적)** 을 따라가는 팔각 관 109마디(꼬리는 처음의 0.6배)(등은 진홍 갑옷판·배는 황갈색, 갑옷판 이음매의 용암빛 텍스처)이고, 가슴 앞쪽은 목 곡선으로 머리까지 이어집니다.
네 다리는 2관절 IK 와 발걸음 순서(대각선 두 쌍)로 걷고, 서 있으면 몸이 곧게 펴집니다. 날개는 평소 등에 접혀 있다가 스킬 때 펴지고 퍼덕이며
(날개막은 매 프레임 다시 계산하는 면, 손가락 뼈대 4개), 입이 열리면 입속 불빛이 켜집니다. 죽으면 몸·날개 조각이 흩어집니다. 챔피언 JSON 의 `"model": {"rig": "dragon"}`.
몸이 길어서 선택 화면 카메라는 리그의 `preview_dist` 로 멀리 잡습니다.

| 스킬 | 이름 | 내용 |
|---|---|---|
| Q | 화염 뱉기 | 고개를 치켜들고 불덩이를 포물선(`flight` 0.8초)으로 뱉어 착지 지점(반경 2.0)에 피해 + 5초짜리 불길 웅덩이 (`spit_pool`, `style: "fire"` 라 웅덩이는 그을린 바닥 + 용암 균열 + 불꽃). 위에 선 적은 초당 피해 |
| W | 날개 폭풍 | 날개를 머리 위로 치켜들었다가 0.35초 뒤 앞으로 크게 휘둘러 **① 전방 부채꼴(사거리 6.5, 100°) 바람**(피해 + 둔화 + 밀어냄, 벽 기절)과 **② 한가운데로 굴러가는 회오리 투사체**(속도 9 · 사거리 9 · 폭 2.6, 관통, 피해 + 0.9초 에어본)를 함께 냄 (`tornado`). 회오리 모양은 보스러시 원본의 9겹 원뿔대 (`build_tornado_layer`). 준비 중 기절하면 불발 |
| E | 날개 후려치기 | 다른 스킬처럼 **누르고 있으면 반경 4.5 범위 표시, 떼면 시전** (`"aim": "circle"`). 날개를 뒤로 젖혔다가 0.45초 뒤 몸 둘레를 후려침 (`wing_sweep`). 피해 + 둔화 + 바깥으로 밀어냄. 준비 중 기절하면 불발 |
| R | 불꽃 비행 | 1초간 하늘 높이 날아오르는 동안 대상 지정 불가. 이어서 지정한 곳(사거리 16.5)까지 **수평으로** 날아가며 입에서 아래로 불을 쏟고(지나는 길: 바깥 바 폭 5 는 기본 피해, 안쪽 바 폭 3 은 2배 피해), 도착하면 내려앉아 반경 3.2 에 큰 피해 + 둔화 + 3초 불길 (`sky_dive`). 조준·시전 중 지면 표시는 자신↔착지 원 사이 바깥 바 + 안쪽 바 + 착지 원 (거미 R 처럼 시전 뒤에도 남음) |

평타는 입에서 나가는 작은 불꽃 투사체(`fire_bolt`, 사거리 4.2, `projectile_muzzle` 로 몸 앞쪽에서 출발)입니다. 서버는 `sky_dive` 이벤트로 오르는·내리꽂는 시간표를 보내고, 리그는 몸 전체를 들어 올려 기울이며 클라이언트가 불줄기를 그립니다. 연출 이벤트는 `gust_wind`·`gust`·`wing_wind`·`sky_dive`·`burn` 이고,
불 이펙트는 팀 색을 섞지 않고 불 색 그대로 그립니다 (`Vfx.neutral()`). 효과음은 `cast_fire`, `cast_wing`, `cast_roar`, `fx_fireburst`, `fx_gust`, `fx_meteor` (`data/sounds.json`).


### 기존 챔피언 7종 (기획서 기반, 현재 숨김)

| id | 이름 | 컨셉 |
|---|---|---|
| `vanguard` | 바르고 | 중갑 탱커 · 이니시에이터 (반격의 방어막, 밀치기, 미니맵으로 강습) |
| `reaper` | 카론 | 낫 브루저 (흡혈, 낫 휘두르기, 구조물 통과 이동, 영혼 속박) |
| `monk` | 무진 | 소리 탱커 (타종 표식 → 메아리 · 정적의 종 · 대종 낙하 감옥) |
| `acrobat` | 꼭두 | 외줄 광대 암살자 (갈고리 돌진, 단검 던지기, 줄 말뚝, 공중 외줄) |
| `hunter` | 아린 | 원거리 지속딜러 (관통 사격, 사냥 덫, 구르기, 관통 화살) |
| `cleric` | 엘리아 | 정통 힐러 (치유의 빛, 성역, 정화, 불멸의 기도) |
| `druid` | 로웬 | 유틸 힐러 (가시 덩굴, 꽃잎 보호막, 바람의 축복, 대자연의 정원) |

> 기획서에 **이름·수치(피해량, 마나, 체력 등)가 없는 항목은 임시값**입니다. 쿨타임·지속시간·범위처럼 기획서에 적힌 값은 그대로 넣었고,
> 쿨타임은 스킬 레벨과 상관없이 같은 값입니다 (`data/champions/*.json` 의 `cooldown` 배열을 바꾸면 레벨별로 다르게 할 수 있음).
> 캐릭터 이름·부제는 임시 이름이니 JSON 의 `name`, `title` 만 바꾸면 됩니다.

## 3D 모델

챔피언 7명은 **KayKit 캐릭터 팩(CC0)** 으로 만든 모델 파일(`assets/models/champions/<id>/model.obj`)을 씁니다.
출처와 라이선스는 `assets/models/champions/CREDITS.md` 에 있습니다.

| 챔피언 | 원본 모델 | 장비 / 색 |
|---|---|---|
| 바르고 | Knight | 검 + 방패 |
| 카론 | Skeleton Rogue | 코드로 만든 낫, 보라색 후드 |
| 무진 | Barbarian | 맨손 (모자·망토 제거), 주황색 승복 |
| 꼭두 | Rogue | 단검 두 자루, 붉은 옷 |
| 아린 | Rogue Hooded | 석궁 |
| 엘리아 | Mage | 지팡이, 흰색·금색 (모자 제거) |
| 로웬 | Mage | 마법봉, 초록·갈색 |

모델은 우선순위대로 불러옵니다: **모델 파일(`model.file`) → 코드로 만든 모델(`model.procedural`, `game/client/champion_models.py`) → 단순 인형**.
그래서 모델 파일을 지우거나 읽지 못하면 코드로 만든 모델이 대신 나옵니다.

### 모델 파일 직접 바꾸기

1. 모델 파일을 `assets/models/champions/<id>/` 에 복사 (예: `vanguard.glb`)
2. `data/champions/01_vanguard.json` 의 `model` 수정

```json
"model": {
  "file": "assets/models/champions/vanguard/vanguard.glb",
  "height": 2.0,
  "rotation_y": 0,
  "offset": [0, 0, 0],
  "up_axis": "y"
}
```

| 항목 | 설명 |
|---|---|
| `file` | 지원 형식: `.obj`(+`.mtl`, 텍스처), `.glb`, `.gltf`, `.ply`, `.stl` |
| `height` | 게임 안에서의 키(유닛). 모델 원래 크기와 상관없이 이 높이로 자동 맞춤, 발밑은 지면에, 중심은 원점으로 정렬 |
| `scale` | `height` 대신 배율을 직접 지정 (1.0 이면 모델 원래 크기 그대로) |
| `keep_origin` | `true` 면 모델이 만들어진 원점(발밑 중앙)을 그대로 쓴다. 무기가 한쪽으로 튀어나온 모델도 몸이 중앙에 서고 발도 지면에 맞는다 (기본 제공 모델이 이 방식) |
| `rotation_y` | 모델이 앞(+Z)을 보지 않으면 각도(도)로 보정. 예: 옆을 보면 90 또는 -90 |
| `up_axis` | 모델이 누워 있으면 `"z"` (블렌더에서 Z-up 으로 내보낸 경우) |
| `pixelated` | `true` 면 텍스처를 보간 없이 또렷하게 표시 (픽셀아트/복셀 스타일 모델용) |

미니언·포탑·억제기·넥서스도 `data/world_models.json` 에 같은 형식으로 파일을 지정하면 교체됩니다.
`.fbx` 는 지원하지 않으니 블렌더 등에서 `.glb` 로 변환해 주세요.

### 도구 (`tools/`)

- `bake_gltf_pose.py` — 뼈대가 있는 `.glb` 캐릭터를 **Idle 같은 동작 한 장면으로 굳혀** OBJ 로 내보낸다. 리깅 모델은 그대로 불러오면 팔을 벌린 T자로 서 있기 때문.
  `py tools/bake_gltf_pose.py 모델.glb 출력폴더 --name model --anim Idle` (`--list` 로 동작·부품 이름 확인, `--hide` 로 부품 제거)
- `bake_skin.py` — 같은 `.glb` 를 **뼈대 애니메이션 데이터(`model.skin.npz`)** 로 굽는다 (아래 "챔피언 모델 애니메이션").
- `build_champion_models.py` — 위 도구로 KayKit 팩에서 7명의 모델(+애니메이션)을 다시 만든다 (장비 고르기, 색 바꾸기, 낫 추가 포함).
  `py tools/build_champion_models.py <Adventures 폴더> <Skeletons 폴더>` — 두 팩은 GitHub 에서 받을 수 있다 (`CREDITS.md` 의 주소).
- `export_champion_model.py` — 코드로 만든 모델을 `procedural.obj` 로 내보내 블렌더에서 다듬을 수 있다 (`model.obj` 는 덮어쓰지 않음).

스킬 투사체·줄 말뚝·사냥 덫·대종 모양은 `champion_models.py` 에 있습니다.
(`assets/models/kenney_blocky/` 의 [Kenney Blocky Characters](https://kenney.nl) `character-m` (CC0) 은 참고용입니다.)

## 챔피언 모델 애니메이션

챔피언 7명은 KayKit 모델 안에 들어 있는 **뼈대(스켈레탈) 애니메이션**으로 움직입니다 (가만히 서기, 달리기, 공격, 스킬, 기절, 공중, 귀환, 사망, 부활, 승리).
`.glb` 의 동작을 미리 구워서 `assets/models/champions/<id>/model.skin.npz` 한 파일에 담아 두고, 게임에서는 그래픽카드가 뼈대를 움직입니다
(`game/client/skin.py` 가 읽고 재생, `game/client/champ_anim.py` 가 서버 상태 → 동작을 고름, `game/client/gl.py` 의 `MESH_SKIN_VS` 가 그림).
`model.skin` 이 없거나 읽지 못하면 예전처럼 정지 모델(`model.file`)에 코드로 만든 흔들림 모션을 줍니다.

동작 이름은 챔피언 JSON 의 `model.anim` 에서 정합니다:

```json
"model": {
  "file": "...", "skin": "assets/models/champions/vanguard/model.skin.npz",
  "anim": {
    "attack": ["1H_Melee_Attack_Slice_Diagonal", "1H_Melee_Attack_Chop"],
    "Q": "2H_Melee_Attack_Spinning",
    "R": {"clip": "Jump_Full_Short", "speed": 1.0, "max": 1.2}
  }
}
```

| 키 | 설명 |
|---|---|
| `attack` | 기본 공격 동작. 목록이면 돌아가며 쓴다. 공격 선딜에 맞게 재생 속도가 자동으로 정해짐 |
| `Q` `W` `E` `R` | 그 스킬을 쓸 때 동작. 없으면 `cast` |
| `cast` | 스킬 동작이 따로 없을 때의 기본 시전 동작 |
| `idle` `run` `death` `spawn` `air` `stun` `recall` `win` | 상태별 동작 (생략하면 `Idle` `Running_A` `Death_A` `Jump_Land` `Jump_Idle` `Hit_B` `Spellcasting` `Cheer`) |

값은 동작 이름이거나 `{"clip": 이름, "speed": 배속, "max": 최대 재생 시간(초)}` 입니다.
선택 화면에서는 기본 공격과 Q·W·E·R 동작을 차례로 보여 줍니다.

KayKit 의 다른 동작을 쓰려면 `model.anim` 에 동작 이름을 적고 `py tools/build_champion_models.py <Adventures 폴더> <Skeletons 폴더>` 를 다시 실행하세요
(JSON 의 `model.anim` 에 적힌 동작만 `model.skin.npz` 에 구워 넣습니다).
동작 이름 목록은 `py tools/bake_gltf_pose.py 모델.glb x --list` 로 볼 수 있습니다 (모델마다 76개 안팎).
`tools/bake_skin.py` 는 위 빌드 도구가 불러 쓰는 굽기 모듈입니다 (뼈 32개 이하, 30fps).

새로운 종류의 스킬이 필요하면 `game/server/abilities.py` 에 `@handler("새type")` 함수를 추가하면 됩니다.

## 효과음

효과음은 **Kenney CC0 소리 팩**에서 고른 `.ogg` 153개(`assets/sounds/`, 출처는 `assets/sounds/CREDITS.md`)를 씁니다.
어떤 상황에 어떤 소리를 낼지는 모두 `data/sounds.json` 에 있고, 코드는 `game/client/audio.py` 입니다.

| 상황 | 소리 |
|---|---|
| 화면(UI) | 버튼 클릭·마우스 올림, 챔피언 선택·확정, 상점 열고 닫기, 구매·판매, 채팅, 오류, 선택 마감 5초 전 똑딱 |
| 내 챔피언 | 레벨 업, 스킬 레벨 올림, 스킬을 못 쓸 때(쿨타임·마나 부족), 골드, 회복, 맞을 때, 처치, 연속 처치, 발소리 |
| 기본 공격 | 챔피언마다 휘두르는 소리(검·낫·주먹·단검·석궁·마법)와 맞는 소리가 다름 |
| 스킬 | 스킬 종류(`type`)마다 시전 소리, 충돌·폭발·덫·종·갈고리 같은 이펙트 소리 |
| 전장 | 포탑 레이저, 미니언 공격·죽음, 구조물 방어판 파괴·폭발, 귀환, 부활, 유물, 알림 |
| 아나운서 | 게임 시작("Fight!"), 선취점, 연속 처치, 승리·패배, 챔피언 선택 화면 시작 |

- 다른 챔피언·미니언·포탑의 소리는 **카메라에서 멀수록 작아지고** 화면 왼쪽·오른쪽에 따라 좌우로 들립니다. 내 챔피언의 소리는 항상 들립니다.
- 게임 속 소리(전투·스킬·발소리 …)는 화면(UI)·아나운서 소리보다 조금 작게 나고, 내 챔피언 바로 옆에서 나는 소리는 더 줄여 있습니다
  (`game/client/audio.py` 의 `WORLD_GAIN`, `NEAR_GAIN`, `NEAR_DIST`).
- 소리 크기는 게임 중 `ESC` 설정 창의 "사운드" 탭에서 막대로 바꿉니다 (`settings.json` 에 저장, "소리 끄기" 버튼도 있음).
- 소리를 바꾸려면 `assets/sounds/` 에 `.ogg`/`.wav` 를 넣고 `data/sounds.json` 의 `sounds` 에서 그 소리의 `files` 를 고치세요.
  (`vol` 음량, `pitch` 음높이 흔들림, `gap` 같은 소리 최소 간격, `range` 들리는 거리, `pri` 1 이면 다른 소리에 밀리지 않음)
- 챔피언의 기본 공격 소리는 `sounds.json` 의 `attack`, 스킬 시전 소리는 `cast`(스킬 `type` 별), 스킬 이펙트는 `fx` 에서 연결합니다.
  스킬 하나만 다른 소리를 쓰고 싶으면 챔피언 JSON 의 그 스킬에 `"sfx": "소리이름"` 을 적습니다.
- 사운드 장치가 없거나 파일이 없으면 소리만 안 나고 게임은 그대로 돌아갑니다.

## 맵 배경 (하늘 위의 신전 유적)

- 하늘(푸른 낮 하늘, 해, 플랫폼 아래로 펼쳐진 흰 구름 바다)은 이미지 없이 셰이더로 그립니다: `game/client/gl.py` 의 `SKY_FS`
  (하늘 색은 `horizon` / `mid` / `zenith`, 해 방향은 `sun_dir`, 구름 바다 높이는 `plane_y`). 게임 속 물체의 조명도 같은 파일 `MESH_FS` 에서 황혼빛(주황 햇빛 + 보랏빛 그림자)으로 줍니다.
- 사암 타일 길(폭이 변해도 항상 같은 크기의 정사각 타일 격자, 가장자리 타일만 길 윤곽대로 잘림 · 타일 색은 `PANEL_A` / `PANEL_B` 두 가지만 번갈아 씀 · 줄눈선은 깜빡임 때문에 그리지 않음), 낮은 석벽, 불을 켠 신전 기둥(군데군데 무너짐), 매달린 바위 기둥, 본진의 룬 제단,
  떠 있는 돌섬과 무너진 아치·기둥은 `game/client/procedural.py` 의 `build_map()` 이 만듭니다 (색은 파일 위쪽 `PANEL_A`, `MOSS`, `STONE` … 상수).
- 포탑·억제기·넥서스는 같은 석회암 색(`STONE`)에 팀 색 수정만 빛납니다. 미니맵 길도 사암 색입니다.

## 챔피언 추가

`data/champions/` 에 JSON 파일을 하나 더 만들면 선택 화면에 자동으로 나타납니다 (파일 이름 순서로 정렬, 봇도 서로 다른 챔피언을 고릅니다).
기존 JSON 을 복사해서 `id`, `name`, `stats`, `abilities` 를 고치면 됩니다. 패시브는 없어도 됩니다.
- `"hidden": true` — 선택 화면·봇·서버 선택 검사에서 빼고 코드만 남긴다.
- `"model": {"rig": "<이름>", "scale": 숫자}` — 모델 파일 대신 `game/client/rigs/` 의 절차적 리그로 그린다 (`make_rig`).
- 새 챔피언의 스킬 아이콘은 `python tools/build_icons.py --only <id>`, 초상화는 `python tools/build_portraits.py <id>` (id 를 빼면 전부 다시 만듦), 이펙트 그림은 `python tools/build_fx_sprites.py <이름...>` 으로 만듭니다.
스킬은 `type` 으로 동작이 정해지고(`game/server/abilities.py`), 값이 리스트면 스킬 레벨별 값입니다 (`cooldown`, `mana` 는 항상 리스트).

| type | 동작 | 주요 값 |
|---|---|---|
| `skillshot` | 직선 투사체. 관통·멀수록 강해지는 피해·둔화/기절/속박 가능 | `range`, `speed`, `width`, `damage`, `pierce`, `distance_bonus`, `distance_full`, `slow`, `stun`, `root`, `style` |
| `self_buff` | 자신에게 공속/이속 버프, `pierce` 면 기본 공격이 관통 | `duration`, `attack_speed_pct`, `move_speed_pct`, `pierce` |
| `dash` | 지정 방향 돌진 + 다음 공격 강화 | `range`, `speed`, `empower_magic` 또는 `empower_damage`(`_ad`) |
| `ground_aoe` | 지연 후 범위 피해 | `range`, `radius`, `delay`, `damage`, `stun` |
| `self_aoe` | 내 주변 즉시 범위 피해 | `radius`, `damage` |
| `counter_shield` | 받은 피해의 일부를 보호막으로 | `duration`, `ratio`, `shield_life` |
| `knockback` | 밀치기, 벽·구조물에 부딪히면 기절 | `range`, `width`, `knock_distance`, `wall_stun`, `damage` |
| `teleport_strike` | 먼 지점(미니맵 가능)으로 순간이동 + 에어본 | `range`, `radius`, `airborne`, `damage` |
| `lifesteal_buff` | 일정 시간 입힌 피해만큼 회복 | `duration`, `pct` |
| `ghost_walk` | 구조물 통과 + 이속 증가 | `duration`, `move_speed_pct` |
| `cone` | 부채꼴 피해 + '울림' 표식 | `range`, `angle`, `damage`, `mark_duration` |
| `echo_guard` | 받는 피해 일부를 나눠서 받기 + 표식당 방어력 | `duration`, `defer_pct`, `defer_time`, `armor_per_mark` |
| `silence_marked` | 표식이 있는 모든 적 침묵 | `radius`, `silence` |
| `cage` | 지연 후 대종이 떨어져 적을 가둠 (갇힌 대상은 밖의 아군 회복·보호막 불가) | `range`, `radius`, `delay`, `duration`, `max_targets`, `damage` |
| `hook_dash` | 갈고리를 걸어 돌진 (부쉬에서 사거리 증가, 빗나가면 쿨타임 환급) | `range`, `bush_range`, `speed`, `dash_speed`, `miss_refund`, `w_window` |
| `knife_throw` | 단검 던지기 (갈고리 적중 직후엔 부채꼴로 즉시) | `count`, `interval`, `speed`, `fan_angle`, `damage` |
| `anchor` | 말뚝 설치 → 다시 누르면 말뚝 위치로 복귀 (기본 공격 3번이면 부서짐) | `duration` |
| `rope_walk` | 공중 외줄을 타고 이동 (타깃 불가) → 내려오며 피해 | `length`, `duration`, `land_radius`, `damage` |
| `trap` | 보이지 않는 덫 (밟은 적 속박 + 위치 노출) | `range`, `trigger_radius`, `max_traps`, `root`, `reveal` |
| `ally_heal` | 가장 가까운 아군(나 포함) 회복 | `range`, `heal`, `heal_ap` |
| `cleanse` | 아군의 CC 제거 + 잠깐 CC 면역 | `range`, `immune` |
| `team_heal` | 주변 아군 회복 + 잠깐 불사 | `radius`, `heal`, `undying` |
| `zone` | 지속 장판 (아군 회복, 적 둔화/속박/초당 피해), `delay` 가 있으면 지연 후 생성 | `range`, `radius`, `duration`, `heal_per_sec`, `slow`, `root`, `damage_per_sec`(`_ad`, `damage_type`), `style` |
| `line_aoe` | 직선 즉시 범위 피해 + 둔화 + 자기 회복 | `range`, `width`, `damage`, `slow`, `heal` |
| `ally_shield` | 아군 보호막, 깨지면 주변 폭발 | `shield`, `duration`, `burst_damage`, `burst_radius` |
| `ally_buff` | 아군 공속/이속 | `duration`, `attack_speed_pct`, `move_speed_pct` |
| `volley` | 부채꼴로 여러 발을 동시에 발사 (거미 여왕 W) | `count`, `spread`, `range`, `speed`, `damage` |
| `leap_slam` | 지정 지점으로 도약해 착지 범위 피해 + 둔화 (점프 중 공중 상태). `"aim": "enemy"` 면 적 챔피언을 지정해 뛰어들고 `stun`, `zone`(착지 자리 장판 값) 도 쓸 수 있음 | `range`, `speed`, `radius`, `damage`, `slow`, `slow_duration`, `stun`, `zone` |
| `cocoon` | 시전 방향과 수직으로 나란히 고치를 놓고, 부화하면 새끼 거미가 적에게 다가가 거미줄 평타로 공격 | `range`, `count`, `spacing`, `hatch`, `cocoon_hp`, `baby_hp`, `max_babies`, `baby_speed`, `baby_ad`, `baby_ad_ratio` |
| `spit_pool` | 포물선으로 뱉은 덩어리가 착지해 피해 + 웅덩이 장판을 남김 (이무기 Q 독 `venom` / 용 Q 불 `fire`, `style` 이 모양을 정함) | `range`, `flight`, `radius`, `duration`, `damage`, `slow`, `damage_per_sec`, `style` |
| `lunge` | 짧은 예고 뒤 직선 돌진, 지나는 길의 적을 한 번씩 물어뜯어 피해 + 둔화 (이무기 W) | `range`, `width`, `windup`, `speed`, `damage`, `slow`, `slow_duration` |
| `serpent_slam` | 지연 뒤 한 지점을 내려찍어 피해 + 기절, 이어서 퍼지는 충격파가 피해 + 둔화 (이무기 E) | `range`, `radius`, `delay`, `wave_radius`, `wave_ratio`, `wave_slow`, `stun` |
| `dive` | 머리부터 잠겨 대상 불가 상태로 이동하다가 지정 지점에서 솟구쳐 피해 + 띄움 (이무기 R) | `range`, `sink`, `speed`, `travel_max`, `radius`, `damage`, `airborne` |
| `tornado` | `delay` 뒤 전방 부채꼴 바람(피해 + 둔화 + 밀어냄) + 관통 회오리 투사체(피해 + 에어본). 준비 중 기절하면 불발 (용 W, `"aim": "cone"`) | `range`, `cone_range`, `angle`, `speed`, `width`, `delay`, `damage`, `cone_damage`, `airborne`, `slow`, `knock_distance` |
| `wing_sweep` | `delay` 뒤 시전자 둘레에 피해 + 둔화 + 바깥으로 밀어냄 (용 E, `"aim": "self"`) | `radius`, `delay`, `damage`, `slow`, `knock_distance`, `wall_stun` |
| `sky_dive` | `rise` 동안 떠올라(대상 지정 불가) 지정 지점까지 수평 비행(`speed`), 길에 `path_damage`, 착지에 `damage` + 둔화 + `zone` 불길 (용 R) | `range`, `radius`, `rise`, `speed`, `height`, `path_width`, `damage`, `path_damage`, `zone` |

피해 계수는 `ad_ratio`, `bonus_ad_ratio`, `ap_ratio`, 피해 유형은 `damage_type`(`physical`/`magic`/`true`) 입니다.
회복·보호막처럼 피해가 아닌 수치는 `heal` + `heal_ap` 처럼 `<이름>` + `<이름>_ap`(주문력), `_ad`(공격력) 계수를 씁니다.
조준 방식(직선/부채꼴/바닥/아군/즉시)은 `type` 에 따라 자동으로 정해지며, 스킬에 `"aim": "ground"` 처럼 적어 바꿀 수 있습니다 (`game/shared/data.py`).
봇이 스킬을 쓰는 우선순위는 챔피언 JSON 의 `bot_priority` (예: `["R", "Q", "E", "W"]`)로 조절합니다.
새로운 종류의 스킬이 필요하면 `game/server/abilities.py` 에 `@handler("새type")` 함수를 추가하면 됩니다.

## 코드 구조

```
main.py / server.py            실행 진입점
data/                          챔피언, 아이템, 월드 모델, 효과음(sounds.json) 설정 (JSON)
assets/models/                 3D 모델 파일 (champions/ = KayKit 기반 챔피언 모델·애니메이션 + CREDITS.md)
assets/sounds/                 효과음 (Kenney CC0, CREDITS.md)
assets/ui/                     스킬·소환사 주문·능력치 아이콘 PNG (game-icons.net CC BY 3.0, CREDITS.md)
game/shared/                   공용: 상수, 맵 배치, 데이터 로더, 네트워크(줄 단위 JSON over TCP)
game/server/server.py          로비/방/챔피언 선택/게임 루프 (30틱, 15Hz 스냅샷)
game/server/sim.py             칼바람 규칙 시뮬레이션 (서버 권한)
game/server/abilities.py       스킬 종류(type)별 동작 처리 (장판·말뚝·외줄 등 포함)
game/server/bot.py             봇 AI
game/client/gl.py              moderngl 렌더러, 카메라, 2D 오버레이
game/client/models.py          3D 모델 로더 (OBJ / glTF / 뼈대 모델), 모델 라이브러리
game/client/skin.py            뼈대 애니메이션 데이터(.skin.npz) 읽기, 동작 재생기 (크로스페이드)
game/client/champ_anim.py      서버 상태(이동·공격·시전·기절·사망 …) → 챔피언 동작 고르기
game/client/rigs/              절차적 애니메이션 리그 (spider.py = 거미 여왕: 다리 IK·자세 섞기, serpent.py = 이무기: 궤적을 따라가는 몸통·S자 목, dragon.py + dragon_assets.py = 용: 네 다리 걷기·접히는 날개·긴 목)
game/client/audio.py           효과음 재생 (data/sounds.json, 거리·좌우 위치, 음량 설정)
game/shared/spells.py          소환사 주문 목록 (이름·설명·수치 표시)
tools/                         모델 변환·제작 도구 (bake_gltf_pose, bake_skin, build_champion_models, export_champion_model), 아이콘·초상화·BGM·이펙트 그림 제작 (build_icons, build_portraits, build_bgm, build_fx_sprites)
game/client/procedural.py      코드로 만든 미니언·구조물·맵 (새끼 거미 포함)
game/client/cursors.py         마우스 커서 (손 / 칼 / 조준경)
game/client/champion_models.py 코드로 만든 챔피언 7종(숨김), 스킬 투사체·장치 모델
game/client/scenes/            타이틀, 로비, 방, 챔피언 선택, 인게임 화면
```

## 알려진 한계

- 길찾기가 없어 구조물 주변은 단순 회피로 돌아갑니다 (라인이 일자라 큰 문제는 없음).
- 인터넷(외부망) 접속은 포트포워딩이 필요합니다. 기본은 같은 네트워크(LAN)용입니다.
- 클라이언트 예측이 없어 지연이 큰 환경에서는 조작이 늦게 느껴질 수 있습니다.
- 챔피언이 거미 여왕·이무기·용 셋뿐입니다 (기존 7명은 숨김). 경직(스태거) 연출은 옮기지 않았습니다.


### 테스트용 치트 (게임 중 키)
- **F9** 레벨 +1 (스킬 포인트도 +1, Ctrl+스킬키로 찍기) · **F8** 모든 스킬·스펠 쿨타임 초기화 · **F7** 마나 최대 · **F6** 체력 최대.
- 서버 명령 `cheat_lv`·`cheat_cd`·`cheat_mana`·`cheat_hp` (`Simulation.handle_command`).
