# 바이오하자드 (1996, Steam판) 한글 패치

Steam판 `4249100_Biohazard`의 **일본어 실행 파일(BIOHAZARD)** 을 기반으로 한 한글화 패치와, 그 제작 도구입니다.

## 사용자용: 설치 방법

1. `bh1_kor_patch.exe` 를 실행합니다. 게임 폴더(Steam 라이브러리의 `4249100_Biohazard`)를 자동으로 찾습니다.
   찾지 못하면 exe를 게임 폴더에 넣고 실행하거나, 경로를 인자로 줍니다: `bh1_kor_patch.exe "D:\...\4249100_Biohazard"`
2. Steam에서 게임을 시작하고, 런처의 Language 목록에서 **korean** 을 선택합니다. **japanese** 를 고르면 원래 일본어판이 실행됩니다.
3. 제거: `bh1_kor_patch.exe -uninstall` (런처를 원본으로 되돌리고 `korean` 폴더를 지웁니다. 한글판 세이브는 남겨 둡니다).

참고
- 한글판은 `korean` 폴더에 따로 설치되고 `japanese` 폴더는 수정하지 않습니다. 바뀌지 않은 데이터는 하드 링크로 공유합니다.
- 세이브는 `korean\SAVE` 에 따로 저장됩니다(처음 설치할 때 일본어판 세이브를 복사).
- 패치에는 원본과의 차이(XOR diff)만 들어 있으며, 설치 전에 원본 파일의 해시를 검사합니다.
- 일본어판으로 만든 기존 세이브는 슬롯의 지역명이 깨져 보일 수 있습니다(게임 진행에는 지장 없음).
- 한글 번역은 일본어 원문을 기준으로 했고, 컷신 음성(영어)에 한글 자막이 표시됩니다.

## 동작 원리

| 항목 | 방법 |
|---|---|
| 실행 파일 | Enigma Protector로 패킹되어 있어 직접 수정하지 않음. `version.dll` 프록시가 게임 창 생성 시점(보호기 검사가 끝난 뒤)에 메모리를 패치 |
| 방(RDT) 대사 | RDT는 건드리지 않음. 대사 조회 함수(0x4919d7)를 후킹해 DLL에 내장된 한글 문장을 반환 |
| 아이템/메뉴/시스템 메시지 | exe 내부 문자열 포인터(336곳)를 한글 문자열로 교체 |
| 폰트 | 폰트 페이지 0/1(PBFONT0/1/3N.TIM)에 자주 쓰는 309자를 고정 배치. 나머지 359자는 메시지가 열릴 때 DLL이 페이지 1의 동적 영역(200칸)에 그려 넣고 텍스처를 다시 올림 |
| 반각 공백 | 렌더러에 코드 `FF`(7px 공백) 추가 |
| 문서(파일) | 일본어판은 문서가 이미지(`Item_m2/TEXTM_*.TIM`)라서 나눔명조로 다시 렌더링 |
| UI 이미지 | 인벤토리 버튼(STATUS.TIM), 키 설정 도움말(OPTKEY03.TIM) 수정 |
| 언어 분리 | `japanese` 를 `korean` 폴더로 미러링(데이터는 하드 링크, 바뀐 파일과 `version.dll` 만 실제 파일). 게임은 작업 폴더 기준 상대 경로(`./jpn/...`, `SAVE\`)로 데이터를 읽음 |
| 런처 | .NET 런처(4249100_Launcher.exe)의 언어 목록·시작 처리·dxcfg.ini 저장 대상에 `korean` 을 추가 (`tools/launcher_patch`, Mono.Cecil로 IL 수정). 레지스트리/.reg 처리는 japanese와 같게 취급 |

## 개발자용: 빌드

필요: Python 3.11 (Pillow), zig 0.12 (32비트 DLL 컴파일), .NET 8 SDK (런처 패치 도구), Go 1.20 (패처)

```
python build.py [게임폴더]          # 폰트, 문자열 표, 방 대사, 이미지, build/version.dll, build/4249100_Launcher.exe
python tools/make_patch.py [게임폴더] # patcher/payload 생성 (원본과의 XOR diff)
cd patcher && go build -ldflags="-s -w" -o ../build/bh1_kor_patch.exe . && cd ..
python tools/make_dist.py           # dist/BH1_KOR_Patch_v<버전>.zip
```

게임 폴더(기본값 `./4249100_Biohazard`, git에는 포함하지 않음)의 `japanese` 폴더는 **원본 상태**여야 합니다.
1.2부터는 설치해도 `japanese` 가 바뀌지 않으므로 한글판이 설치된 폴더에서도 빌드할 수 있습니다(런처 원본은 `kopatch_backup` 에서 읽음).

### 버전

- 버전 번호는 `VERSION` 파일에 있고, 패처 화면과 배포 zip 이름에 쓰입니다.
- 변경 내역은 `CHANGELOG.md`, 릴리스는 `v1.0` 같은 git 태그로 표시합니다.
- 새 버전의 패처는 이전 버전이 설치된 폴더에 그대로 덮어 설치할 수 있습니다. 1.0/1.1(japanese 폴더에 덮어쓰던 방식)은 원본으로 되돌린 뒤 `korean` 폴더에 설치합니다.

### 번역 파일

- `translations/rdt_messages.json` — 방 대사 871개 (일본어 원문 `jp`, 북미판 참고 `en`, 번역 `ko`)
- `translations/exe_strings.json` — 아이템 이름·설명, 시스템 메시지, 메뉴 250개
- `translations/documents.json` — 문서 43장(반쪽 화면 86개)
- `translations/GUIDE.md` — 용어집·문체·제어 태그 규칙

검사: `python tools/check_tr.py translations/rdt_messages.json`, `python tools/check_docs.py`

### 도구

- `tools/extract_rdt.py`, `tools/extract_exe.py` — 원문 추출 (exe 쪽은 실행 중 메모리 덤프 필요)
- `tools/jptable.py` — 일본어판 폰트 글리프 → 문자 표
- `tools/kocodec.py` — 한글 문장 → 게임 바이트 코드, 가운데 정렬 재계산
- `dll/kopatch.c` — 런타임 패처
- `tools/launcher_patch/` — 런처에 `korean` 항목을 추가하는 IL 패치 도구 (C#, Mono.Cecil)

## 라이선스

- 갈무리11 (Galmuri) 폰트: SIL Open Font License 1.1 (`fonts/Galmuri-OFL.txt`)
- 나눔명조·나눔고딕: SIL Open Font License 1.1
- 게임 데이터는 포함하지 않습니다. BIOHAZARD는 CAPCOM의 상표입니다.
