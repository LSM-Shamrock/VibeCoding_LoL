# 챔피언 3D 모델 출처

챔피언 7명의 모델은 Kay Lousberg 의 **KayKit 캐릭터 팩** (라이선스: **CC0 1.0 / 퍼블릭 도메인**, 상업적 이용 가능, 출처 표기 의무 없음)을
원본으로 합니다. 그래도 고마움을 표시하기 위해 남겨 둡니다.

- KayKit : Adventurers Character Pack 1.0 — https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0
  (https://kaylousberg.itch.io/kaykit-adventurers)
- KayKit : Skeletons Character Pack 1.0 — https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Skeletons-1.0
- 제작자 사이트: https://www.kaylousberg.com

| 챔피언 | 원본 모델 | 가공 |
|---|---|---|
| vanguard 바르고 | Adventurers / Knight | Idle 자세로 고정, 검+방패만 남김 |
| reaper 카론 | Skeletons / Skeleton Rogue | Idle 자세로 고정, 보라색으로 색 변경, 코드로 만든 낫 추가 |
| monk 무진 | Adventurers / Barbarian | 무기·모자·망토 제거, 승복 색(주황) 변경 |
| acrobat 꼭두 | Adventurers / Rogue | 단검 두 자루만 남김, 옷 색(붉은색) 변경 |
| hunter 아린 | Adventurers / Rogue Hooded | 석궁만 남김 |
| cleric 엘리아 | Adventurers / Mage | 모자 제거, 지팡이만 남김, 흰색·금색으로 색 변경 |
| druid 로웬 | Adventurers / Mage | 마법봉만 남김, 초록·갈색으로 색 변경 |

걷기·공격·스킬·사망 같은 **애니메이션도 같은 KayKit 팩에 들어 있는 동작**입니다. `model.skin.npz` 파일은 그 동작을 게임용으로 구운 것입니다
(`tools/bake_skin.py`, 원본 `.glb` 는 포함하지 않음).

가공은 `tools/build_champion_models.py` 로 다시 만들 수 있습니다 (README 참고).
`assets/models/kenney_blocky/` 의 모델은 Kenney (www.kenney.nl) 의 CC0 에셋입니다.
