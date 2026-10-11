# 효과음 출처

이 폴더의 효과음은 모두 **Kenney (www.kenney.nl)** 가 만든 **CC0 (퍼블릭 도메인)** 소리 팩에서 골랐습니다.
CC0 라서 개인·상업 프로젝트에 자유롭게 쓸 수 있고 출처 표기는 필수가 아니지만, 고마움을 담아 적어 둡니다.
각 폴더의 `License.txt` 는 받은 팩에 들어 있던 원본 라이선스 문서입니다.

| 폴더 | 팩 | 주소 | 쓰는 곳 |
|---|---|---|---|
| `interface/` | Interface Sounds | https://kenney.nl/assets/interface-sounds | 버튼·선택·확정·오류 같은 화면(UI) 소리 |
| `impact/` | Impact Sounds | https://kenney.nl/assets/impact-sounds | 기본 공격이 맞는 소리, 스킬 충돌·타격, 발소리 |
| `rpg/` | RPG Audio | https://kenney.nl/assets/rpg-audio | 칼 휘두르는 소리, 동전(상점·골드), 덫·줄 소리 |
| `scifi/` | Sci-fi Sounds | https://kenney.nl/assets/sci-fi-sounds | 레이저(포탑·원거리 공격), 보호막, 건물 폭발 |
| `digital/` | Digital Audio | https://kenney.nl/assets/digital-audio | 레벨 업, 이동기, 버프·치유 같은 마법 소리 |
| `voice/` | Voiceover Pack: Fighter | https://kenney.nl/assets/voiceover-pack-fighter | 아나운서 ("Fight!", "You win!" 등) |

어떤 상황에 어떤 소리를 쓰는지는 `data/sounds.json` 에 있고, 설명은 README 의 "효과음" 항목을 보세요.
소리를 바꾸려면 이 폴더에 `.ogg`(또는 `.wav`) 파일을 넣고 `data/sounds.json` 의 해당 소리 이름의 `files` 만 고치면 됩니다.
