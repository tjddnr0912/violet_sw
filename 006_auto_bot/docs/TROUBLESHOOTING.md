# 006_auto_bot 트러블슈팅

각 항목은 6필드(증상/원인/해결/복구절차/관련 사고/재발 감지) + Claude 진단 미스 기록 구조를 따른다.

---

## 데이터 파이프라인 봇 "완료" 보고 시 발행 범위 ≠ 수집 범위 간과

- **증상**: 부동산봇이 백필로 119시군구 4종을 적재했는데 주간 블로그 디제스트는 서울 25구만 발행. 코드는 정상 동작(설계상 v1 발행 범위가 `SEOUL_GU`).
- **원인**: 수집(`ALL_REGIONS`=119)과 발행(`run()`→`SEOUL_GU`=25)의 범위가 분리돼 있었음(v1 의도). `config.py`에 명시돼 있으나 "작업 완료" 보고 시 그 불일치를 사용자에게 안 짚음.
- **해결**: v2(2026-06-04)에서 `run()`을 `ALL_REGIONS`로 확장(전국 단일 글, 권역 요약). → [docs/REALESTATE_BOT.md](REALESTATE_BOT.md).
- **복구 절차**: (a) 발행물에서 비서울 권역 섹션 존재 확인 (b) 없으면 `run()`이 SEOUL_GU로 도는지 점검 (c) ALL_REGIONS로 배선.
- **관련 사고**: 2026-06-04
- **재발 감지**: 디제스트 발행 후 `## 경기`/`## 6대 광역시` 섹션 grep. 없으면 발행 범위가 수집보다 좁아진 것.

### Claude 진단 미스 (2026-06-04 세션, 부동산봇 완성도 보고)

- **Claude 처음 가설**: 오피스텔 전월세 노출 + 부동산봇 명명 정리를 마치고 "부동산봇 작업 완료"로 보고. 주간 발행이 서울 25구 한정인 점을 "미완성"으로 플래그하지 않음(백필은 119구인데).
- **실제 원인 (사용자 지적)**: "봇이 완성이 안된것 같아 ... 블로그 게시글이 서울에 한정되어있어." 수집(119구)과 발행(서울25)의 범위 불일치를 사용자가 포착.
- **방향 전환 지점**: 사용자의 "블로그 게시글이 서울에 한정되어있어" 메시지 → 전국 확장(v2) 브레인스토밍·구현 착수.
- **교훈 (데이터 수집·가공·발행 파이프라인 봇 "완료" 보고 전)**:
  - 첫 의심 영역: **발행/출력 범위 == 수집/적재 범위인지** 대조. 수집만 광범위하고 발행이 좁으면 사용자는 "미완성"으로 본다.
  - 빨리 배제할 가설: "코드가 에러 없이 돈다 = 완료" — 설계상 범위 분리는 정상 동작이지만 사용자 기대(수집한 데이터를 다 활용)와 어긋날 수 있음.
  - 핵심 진단 명령: `grep -n "SEOUL_GU\|ALL_REGIONS" weekly_realestate_bot.py` (백필과 발행 `run()`이 같은 범위인지).

---

## 마이그레이션 옵션 비교 시 원본 설계의 implicit value 무시

- **증상**: Gemini grounding hidden quota 발견 후 backend 마이그레이션 옵션을 비교할 때, Claude가 "Native WebSearch 단순 재작성"(옵션 B)을 운영 단순성·인프라 일관성 근거로 강하게 추천. 사용자가 직접 "여기서 chain 구조가 없어지는건 아쉬워. 이게 포함됐던 이유는 할루시네이션을 없애고, 여러 각도에서의 의견을 더 담아보려고 했던 목적이 있었어"라고 corrective 지적할 때까지 chain의 본래 설계 가치(다관점 검증 + hallucination 방지)를 옵션 비교에 명시적으로 반영하지 않음.
- **원인**: 마이그레이션 옵션 분석 시 "기능적 동등성"(quota 회피, 같은 결과)에 집중하고 **원본 설계가 가졌던 implicit value**(왜 이 chain/wrapper/패턴이 만들어졌나? 단순 fallback 외에 다른 의도는?)를 옵션 표 trade-off에 명시 안 함. Chain은 단순 quota fallback이 아니라 모델·각도 다양화로 hallucination을 감소시키는 도구였는데, 이를 옵션 B 단순 적용에서 잃음.
- **해결**: 옵션 B+로 확장 — Native WebSearch + WebFetch + **Phase 1.5(1차 source 검증)** + Phase 3 query 다양화로 원본 chain의 가치를 다른 방식으로 보존. `~/.claude/skills/research/SKILL.md` 재작성에 NEW Phase 1.5 추가 (WebFetch로 핵심 출처 원문 직접 fetch → snippet vs 원문 대조 → hallucination 검출), Phase 3 다양화 축(키워드/언어/시각/도구) 명시. 라이브 테스트로 검증.
- **복구 절차**:
  - (a) 마이그레이션 또는 큰 리팩토링 옵션 비교 시, 원본 설계가 가졌던 **명시되지 않은 implicit value**를 먼저 식별: "왜 이 chain/wrapper/패턴이 만들어졌나? 단순 quota fallback 외에 다른 의도는?"
  - (b) 사용자에게 옵션 제시할 때 그 가치 보존 여부를 명시적 trade-off 컬럼에 추가 ("Pros/Cons" 외에 "원본 설계의 implicit value 보존 여부" 컬럼)
  - (c) 만약 옵션 채택 후 사용자가 "아쉬워" / "원래 의도는 X였는데" 류 corrective 발화하면 즉시 옵션 확장(예: B+) 또는 재설계
- **관련 사고**: 2026-05-27 PM (research skill backend 마이그레이션, [[research-skill-websearch]])
- **재발 감지**: 마이그레이션 plan에서 옵션 표가 "기능적 동등성"에만 만족할 때 — Pros/Cons 컬럼에 "원본 설계의 implicit 가치 보존 여부"가 없으면 의심. 사용자 corrective 발화 후에 옵션을 재구성하지 말고, 옵션 제시 전에 implicit value 자문할 것.

### Claude 진단 미스 (2026-05-27 PM 세션, research skill 옵션 비교)

- **Claude 처음 가설**: research skill 마이그레이션 옵션 B(Native WebSearch 단순 재작성)가 (i) self-call 어색함 없음, (ii) 봇과 인프라 일관, (iii) ask_gemini.sh 외부 wrapper 불필요 — 따라서 "옵션 B (추천)"으로 강하게 push. 사용자에게 비교 옵션 4개(A/B/C/D) 제시했지만 그 표의 어느 컬럼도 "chain의 본래 가치 보존 여부"를 명시하지 않음. Trade-off는 "운영 단순성", "subprocess overhead", "self-call 어색함" 같은 inrastructure 차원에 머무름.
- **실제 원인 (사용자 지적)**: chain의 본래 목적은 (a) 다관점 cross-check, (b) hallucination 방지였는데, 옵션 B 단순 적용 시 단발 WebSearch 호출 1회로 끝나서 두 효과 모두 잃음. 사용자가 "여기서 chain 구조가 없어지는건 아쉬워. 이게 포함됐던 이유는 할루시네이션을 없애고, 여러 각도에서의 의견을 더 담아보려고 했던 목적이 있었어"라고 명시한 후 Claude가 우려 정당성 인정하고 옵션 B+(WebFetch 1차 source 검증 + query 다양화)로 재설계.
- **방향 전환 지점**: 사용자 메시지 "추천 B가 마음에 들긴 하는데, 여기서 chain 구조가 없어지는건 아쉬워. 이게 포함됐던 이유는 할루시네이션을 없애고, 여러 각도에서의 의견을 더 담아보려고 했던 목적이 있었어". 이 발화 이후 Claude가 옵션 표를 재구성(B+/E/F/G) + "Chain의 진짜 가치 재정리" 섹션 신설.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: 마이그레이션 옵션 표 작성 시 "**원본 설계의 implicit value**" 컬럼 의무. quota/성능/비용/인프라 차원 외에 "이 wrapper/chain/패턴이 가졌던 다른 가치는?"을 자문하고 답을 trade-off에 명시
  - 빨리 배제할 가설: "기능적으로 같은 결과를 내면 OK" — implicit value(예: hallucination 방지, 다관점 cross-check, 재현성, 학습 효과)가 사라지는 옵션은 그것만으로 정당화 불가. 보존 여부를 별도 검토해야 함
  - 핵심 진단 명령: 옵션 제시 **전**에 사용자에게 "이 [chain/wrapper/패턴]을 처음 만든 의도가 뭐였어요? 단순 [quota fallback / 비용 절감 / X] 외에 다른 목적이 있었나요?"를 한 번 물어볼 것. 사용자 의도와 implicit value를 명시화하면 옵션 비교가 정확해짐
  - 안티패턴: 옵션 제시 후에야 사용자 corrective 받고 재구성. 사전에 묻는 게 훨씬 효율적이고 신뢰도 높음

---

## Gemini 3.x `google_search` grounding 별도 quota 발견 → Claude WebSearch 전환

- **증상**: 2026-05-27 PM, Telegram deep research 호출이 4개 모델(`gemini-3.1-flash-lite` → `gemini-3.5-flash` → `gemini-3-flash-preview` → `gemini-2.5-flash`)에서 순차로 429 반환. fallback chain 마지막 모델만 성공. AI Studio dashboard의 RPM/TPM/RPD는 거의 0%인데도 거부.
- **원인**: **Gemini 3.x의 `google_search` grounding tool은 모델 generate_content API와 별개의 quota bucket을 사용한다.** 무료 티어 한도가 매우 빡빡해 일상 사용으로 즉시 소진. Dashboard에는 모델 API quota만 노출되고 grounding quota는 표시 안 됨. 2.5-flash만 살아남는 이유는 per-prompt pricing이라 grounding이 prompt charge에 포함되기 때문 ([공식 docs](https://ai.google.dev/gemini-api/docs/google-search)).
- **해결**: grounding 호출 4곳(telegram quick/deep, news gap-fill, sector search) 모두 **Claude CLI + WebSearch**로 이전. `claude -p` 모드에서 web_search 도구 자동 활성화. 모델은 호출 시점 `--model` flag로 선택 + `--fallback-model`로 overload 자동 대비. 신규 wrapper `shared/claude_search.py`.
- **복구 절차**:
  - (a) Anthropic API key가 Claude CLI 인증으로 설정되어 있는지 확인 (`claude --version` 후 `claude -p "test"` 성공 여부)
  - (b) `printf 'tiny prompt' | python -c "from shared.claude_search import claude_websearch; r=claude_websearch('Use web search. What day is today?', model='haiku'); print(r.text[:100], len(r.sources))"`로 라이브 검증
  - (c) `pytest 003_test_code/` 72 pass 확인
  - (d) 봇 재시작 후 텔레그램 deep research로 실호출 검증
- **관련 사고**: 2026-05-27 PM (사용자 텔레그램 deep research에서 4개 모델 동시 429 보고 → dashboard 검토 → 모든 quota 여유 확인 → grounding 별도 quota 가설 → grounding ON/OFF 분리 실측으로 확정)
- **재발 감지**: `tail -f logs/telegram_bot_*.log | grep -E "quota/unavailable|429"` 로 모니터링. grounding 호출이 다시 다수 429 누적되면 quota 정책 변경 가능성.

### Claude 진단 미스 (2026-05-27 PM 세션)

**미스 #3 — Dashboard 신호 과신, grounding 별도 quota 가능성 무시**

- **Claude 처음 가설**: 오전에 만든 모델 fallback chain의 첫 모델(`gemini-3.1-flash-lite`)이 429라 "무료 티어 quota 소진" → "PST midnight reset 또는 billing 활성화" 권장. Dashboard 보고도 "각 모델별 quota bucket 별개라 4개 다 동시에 소진 가능"으로만 설명.
- **실제 원인**: 사용자가 dashboard 스크린샷을 직접 보여줌 — `gemini-3.1-flash-lite` 10/500 RPD, `gemini-3.5-flash` 0/20 RPD, `gemini-2.5-flash` 6/20 RPD로 모두 여유. 즉 quota가 비어있는데도 429. **원인은 grounding tool 자체의 별도 quota bucket이었고, 이건 dashboard에 노출 안 됨.** 사용자 지적 후 grounding ON/OFF로 분리해 단발 호출 → grounding OFF 시 4개 모두 정상, grounding ON 시 3.x 계열 전부 429 → 확정.
- **방향 전환 지점**: 사용자가 "이거 이상한데 한번 검토해봐"라며 dashboard 이미지 첨부한 시점. 그 전엔 "free tier quota 소진"이라는 일반 설명에 머물러 있었음.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: 429가 났는데 dashboard quota가 비어있으면 **도구별 hidden quota** 또는 **feature-specific quota** 의심. 모델 API quota 외에 grounding/code execution/file API 등이 별개 bucket인 경우 흔함
  - 빨리 배제할 가설: "각 모델 quota가 동시에 우연히 소진" — 4개가 0.5초 안에 다 429라는 건 모델 API quota가 아니라 **공통 의존성**(여기선 google_search grounding) 거부 신호
  - 핵심 진단 명령:
    ```python
    # 가설 검증: tool ON/OFF 분리해서 단발 호출
    for tid in CHAIN:
        for grounding in (False, True):
            try:
                r = client.models.generate_content(
                    model=tid, contents="Reply '1'.",
                    config=types.GenerateContentConfig(
                        max_output_tokens=8,
                        **({"tools":[types.Tool(google_search=types.GoogleSearch())]}
                           if grounding else {})
                    ),
                )
                print(f"{tid} grounding={grounding}: OK")
            except Exception as e:
                code = "429" if "429" in str(e) else "other"
                print(f"{tid} grounding={grounding}: {code}")
    ```
    이렇게 grid로 돌리면 hidden quota를 즉시 isolate. dashboard만 보면 안 보이는 패턴.

---

## Gemini `-p` CLI 종료 대응 — API + 모델 fallback chain 마이그레이션

- **증상**: 2026-06에 Google이 `gemini` CLI binary를 종료 예고. 그 전까지 봇 6개 경로가 `subprocess.run(["gemini", "-p", ...])` 또는 `shared.gemini_cli.call_gemini_cli`(내부적으로 subprocess)에 의존 중이라 종료 직후 다음 호출이 다음과 같이 깨짐:
  - 텔레그램 deep mode round 1부터 `FileNotFoundError` 또는 exit 127
  - 텔레그램 `/quick` 동일
  - 뉴스봇 `_gap_fill_via_cli` → 5차원 게이트가 영구 fail
  - 섹터봇 quota 초과 시 fallback이 사라져 그냥 API 실패로 종료
- **원인**: CLI는 단순 subprocess wrapper일 뿐, Google API의 직접 호출 가능 경로(`google-genai` SDK)가 이미 더 안정적. CLI를 1차 정보원으로 둔 설계가 시한부였음.
- **해결**:
  - `shared/gemini_cli.py` 완전 재작성: `call_gemini_with_fallback()` 신규 + 기존 함수명들은 backward-compat alias로 보존. 내부는 `google-genai` SDK + `types.Tool(google_search=types.GoogleSearch())` grounding + 모델 fallback chain (`gemini-3.1-flash-lite` → `gemini-3.5-flash` → `gemini-3-flash-preview` → `gemini-2.5-flash`).
  - `shared/research_orchestrator._run_gemini_round` + `telegram_gemini_bot.run_gemini` subprocess 호출 제거.
  - `news_bot/summarizer.py`, `sector_bot/searcher.py`, `sector_bot/analyzer.py`의 `_use_cli_fallback` 플래그·`_*_via_cli` 메서드 제거 → wrapper로 일원화.
  - `~/.claude/skills/research/scripts/ask_gemini.sh`도 동일 패턴으로 변환 (내부적으로 isolated venv의 `ask_gemini.py` 호출).
- **복구 절차**:
  - (a) `GEMINI_API_KEY`가 ENV 또는 `~/.gemini/api_key` 파일에 있는지 확인 (`zsh -c 'echo ${GEMINI_API_KEY:0:6}...${GEMINI_API_KEY: -4}'`)
  - (b) 운영 코드에서 subprocess 잔존 0건 검증: `grep -rnE 'subprocess\.(run|Popen)\s*\(\s*\[\s*["'\'']gemini["'\'']' 001_code/ --include="*.py"`
  - (c) `pytest 003_test_code/ --ignore=003_test_code/test_news_fetch.py` → 73 pass 확인
  - (d) 라이브 smoke: `printf '한 줄로만 답하라. 1+1?' | python -c "from shared.gemini_cli import call_gemini_with_fallback; print(call_gemini_with_fallback('1+1?', use_grounding=False).text)"`
- **관련 사고**: 2026-05-27 (예방적 마이그레이션, 6월 CLI 종료 D-30+ 시점)
- **재발 감지**: `import subprocess` + `gemini` 같은 줄에 등장하면 grep으로 즉시 검출. CI에 `! grep -rqE 'subprocess.*\bgemini\b' 001_code/ --include="*.py"` 추가 권장.

### Claude 진단 미스 (2026-05-27 세션)

**미스 #1 — 잔여 점검 범위 누락**

- **Claude 처음 가설**: 1차 grep으로 운영 코드(`001_code/`)의 `subprocess + gemini` 호출 0건을 확인하고 "마이그레이션 완료, 잔존 없음"으로 보고.
- **실제 원인**: 사용자가 "다시 한번 전체 점검 해봐"라고 요청한 뒤 광범위 grep을 돌렸을 때 (a) 테스트 코드 4개(`test_research_orchestrator.py`)가 옛 subprocess monkeypatch에 의존해 fail, (b) `test_shared_gemini_cli.py` + `test_sector_orchestrator.py`의 `_use_cli_fallback` sentinel 테스트 2개도 의미 상실, (c) `docs/ARCHITECTURE.md`·`SECTOR_BOT.md`·`NEWS_BOT.md`에 옛 CLI fallback 설명 잔존, (d) `research_orchestrator.py` 2곳의 `except (GeminiRoundError, subprocess.TimeoutExpired, FileNotFoundError)`에서 subprocess 예외가 dead 분기로 남아있음을 발견. 6 failed / 65 passed.
- **방향 전환 지점**: 사용자가 "다시한번 전체 점검 해봐"라고 명시한 시점. 1차 grep이 너무 좁았음(`001_code/` + `--include="*.py"`만 봄).
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: 마이그레이션 후 "잔존 없음" 선언 전에 **테스트 코드 + docs/ + dead except 분기**까지 grep 필수
  - 빨리 배제할 가설: "운영 코드만 깨끗하면 완료" — 회귀 테스트가 옛 가정에 묶여 있으면 CI 깨짐. 문서가 옛 동작 설명하면 신규 합류자 헷갈림
  - 핵심 진단 명령:
    ```bash
    # 운영 + 테스트 + docs 모두
    grep -rnE 'subprocess\.(run|Popen).*<old-cmd>|<old-cmd>\s+-<flag>' \
      001_code/ 003_test_code/ docs/ --include='*.py' --include='*.md' --include='*.sh'
    # 죽은 except 분기
    grep -rnE 'except\s*\([^)]*subprocess\.[A-Z]' 001_code/ --include='*.py'
    # 실제 회귀 테스트
    pytest 003_test_code/ --tb=line -q
    ```

**미스 #2 — `.zshenv` 자동 로드 사실을 설명에서 누락**

- **Claude 처음 가설**: `~/.zshenv`에 `GEMINI_API_KEY` export 추가 안내 후 "새 shell 띄우거나 `source ~/.zshenv`" 라고 단순 안내. 결과: 사용자가 ".zshenv는 내가 항상 source 해줘야해? 그렇다면 .zshrc에서 자동으로 source 해주는 것을 추가해" 라고 잘못된 가정에 도달.
- **실제 원인**: `~/.zshenv`는 zsh가 모든 invocation(interactive/non-interactive/login)에서 **자동 로드**하는 startup file. `~/.zshrc`(interactive 전용)와 명확히 구분되는데 Claude 첫 안내에 그 차이를 적지 않아 사용자가 수동 source 또는 .zshrc 추가가 필요하다고 오해.
- **방향 전환 지점**: 사용자가 .zshrc 추가 요청. Claude가 `zsh -c '...'` / `zsh -lc` / `zsh -ic` 세 모드 전부에서 auto-load 검증 후 "추가 불필요" 정정.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: shell startup file을 추천할 때 **자동 로드 메커니즘을 한 줄로 명시**. "추가만 하면 됨, source 불필요, 모든 새 zsh가 자동 로드" 식으로
  - 빨리 배제할 가설: "사용자가 dotfile 동작을 알 것이다" — `.zshenv`는 macOS default 환경에서도 자주 모름
  - 핵심 진단 명령:
    ```bash
    # 자동 로드 검증 (3 mode)
    zsh -c  'echo ${VAR:-NOT_LOADED}'   # non-interactive
    zsh -lc 'echo ${VAR:-NOT_LOADED}'   # login
    zsh -ic 'echo ${VAR:-NOT_LOADED}'   # interactive
    ```
  - 안티패턴: `.zshrc`에 `source ~/.zshenv` 추가 권유 → 중복 실행이고 zshenv가 zshrc보다 먼저 실행되므로 의미 없음

---

## 인라인 SVG 플로우차트 화살표가 박스에 안 닿음 / 다이어그램 깨짐

- **증상**: 봇이 만든 글의 의사결정 흐름 다이어그램에서 다이아몬드 옆구리에서 출발한 YES/NO 화살표가 결과 박스에 *연결되지 않고 허공에서 끝남*. 결과 박스가 SVG 영역 밖 별도 div로 빠지면서 시각적으로 어긋남.
- **원인**: SKILL.md 8번/9번 가이드가 "인라인 SVG로 노드+화살표 직접 좌표 계산"이었음. Claude가 매 호출마다 좌표를 재계산하면서 다음 3가지 실수 누적:
  - (A) 다이아몬드·화살표는 SVG, 결과 박스는 외부 HTML div로 *좌표계 분리* → 가장 빈번
  - (B) viewBox 고정인데 라벨 텍스트 길이 가변 → 시작점/끝점 어긋남
  - (C) 분기 ≥3이면 전체 레이아웃 재계산 필요한데 일부만 손봄
- **해결**: SKILL.md를 **Mermaid 코드블록 우선**으로 패치 (`flowchart TD` / `graph LR`). Blogger 테마와 Tistory 스킨에 Mermaid.js v11 글로벌 등록. 본문은 `<pre><code class="language-mermaid">` 양식만 작성 → JS가 자동 렌더. SVG 좌표 계산 0줄.
- **복구 절차**:
  - (a) `~/.claude/skills/blogger-html/SKILL.md` 8번/9번 섹션이 Mermaid 우선인지 확인
  - (b) Blogger 테마 → HTML 편집 → `</body>` 위 Mermaid CDN 스크립트 존재 확인 (`useMaxWidth` 또는 `import mermaid` 검색)
  - (c) Tistory: 꾸미기 → 스킨 편집 → html 편집 → 동일 확인
  - (d) 다음 봇 자동 실행 결과에서 `language-mermaid` 코드블록이 다이어그램으로 렌더링되는지
- **관련 사고**: 2026-05-17 (사용자 보고: 석회성건염 의사결정 다이어그램 — 화살표 박스 미연결), 2026-05-18 (검증 발행 4회로 Mermaid 도입 작동 확인)
- **재발 감지**: 발행물 raw HTML에서 `language-mermaid` 카운트 0이고 `<polygon`/`<line` 다수면 SVG 좌표 노가다로 회귀한 것. SKILL.md의 "Mermaid 코드블록을 우선 사용" 문구가 8번/9번 가이드에 남아있는지 확인.

### Claude 진단 미스 (2026-05-17 세션)

- **Claude 처음 가설 (도구 분석)**: 발행물의 다이어그램 상태를 *WebFetch* 도구로 확인 → "SVG 0개, Mermaid 스크립트 없음, border-left 카드 없음"이라는 잘못된 보고. 봇이 만든 시각화 자체가 빈약하다고 판단할 뻔함.
- **실제 원인**: WebFetch는 HTML→markdown 변환을 거치면서 인라인 `<svg>`, `<script>`, 인라인 style div를 모두 소실시킴. raw HTML 자체에는 SVG 27개·카드 24개가 멀쩡히 들어있었음.
- **방향 전환 지점**: 봇 출력 HTML 길이(50,000자+)와 WebFetch 결과(시각화 0)의 모순을 인지 → `curl -sL`로 raw HTML 직접 확인 후 정확한 카운트 확보.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: **Blogger·Tistory 발행물 분석에는 WebFetch 사용 금지**. raw HTML이 필요한 모든 검증은 `curl -sL -A "Mozilla/5.0" "$URL"` 로 가져온 뒤 `grep`/`python3 -c "import re"`로 추출
  - 빨리 배제할 가설: "봇 출력이 변경됐다" — WebFetch에서 시각화가 0개로 보여도 *도구 한계*일 가능성이 90%. 봇 코드 변경 없이 출력만 빈약해지는 일은 드뭄
  - 핵심 진단 명령:
    ```bash
    curl -sL -A "Mozilla/5.0" "$URL" | grep -ciE "language-mermaid|<svg|border-left"
    ```

---

## Gemini 429 (서버 용량 부족)

- **증상**: Gemini API가 `429 ResourceExhausted` 또는 "서버 용량 부족" 메시지 반환. 라운드/요약 도중 일부 호출만 실패.
- **원인**: Google 서버 일시적 과부하 또는 quota 초과 (Code Assist tier 일일 한도).
- **해결**: 자동 재시도 (지수 백오프 3회). 누적 결과로 fallback 요약 메시지 자동 전송.
- **복구 절차**: 자동 복구. 429가 1시간 이상 지속 시 → quota 초과 가능성, Google AI Studio 콘솔에서 잔여량 확인.
- **관련 사고**: 2026-03-13 (gemini-free-tier-quota), 2026-04-04 (gemini-empty-response), 2026-04-20 (gemini-503-cli-fallback)
- **재발 감지**: `logs/*_$(date +%Y%m%d).log`에서 `429`/`503`/`empty response` 빈도. 일일 5회 이상이면 quota 한계 의심.

---

## Claude CLI empty response

- **증상**: Claude CLI 호출이 성공 코드(0) 반환하지만 stdout 비어 있음. 분석 결과 누락.
- **원인**: Claude API 일시 장애 또는 CLI 내부 timeout.
- **해결**: 자동 재시도 (3회, 30초 간격). 모두 실패 시 fallback synthesis로 진행 (raw rounds concatenation).
- **복구 절차**: 자동. 수동 검증은 `claude --version` 후 단순 호출 (`echo hi | claude -p "echo back"`).
- **관련 사고**: 2026-03-26 (claude-cli-empty-retry), 2026-04-04
- **재발 감지**: `Claude CLI returned empty` 로그 빈도. 일일 0~1건이 정상.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: CLI 인스톨 문제 또는 PATH 미설정
- **실제 원인**: Anthropic API 측 일시 장애. CLI 자체는 정상.
- **방향 전환 지점**: 같은 명령을 30초 후 재실행하면 성공 — 인스톨 문제 아님 인식
- **교훈**:
  - 첫 의심 영역: **재시도 시 응답 변화 여부**
  - 빨리 배제할 가설: "CLI 설치 문제" — 한번이라도 정상 응답 받았으면 인스톨은 OK
  - 핵심 진단 명령: `echo "test" | claude -p "echo"` 로 minimal call 검증

---

## Blogger OAuth 인증 실패

- **증상**: Blogger 업로드 시 `invalid_grant` 또는 토큰 만료 에러.
- **원인**: 저장된 OAuth refresh token이 무효화됨 (장기간 미사용 또는 사용자가 권한 회수).
- **해결**: `credentials/blogger_token.pkl` 삭제 후 다음 실행 시 OAuth 플로우 재진행.
- **복구 절차**:
  ```bash
  rm credentials/blogger_token.pkl
  python news_bot/blogger_uploader.py --auth   # 또는 통합 봇 실행 시 자동 재인증
  ```
- **관련 사고**: 정기적 (refresh token 만료, 분기 단위)
- **재발 감지**: `invalid_grant` 로그 발생 즉시 알림.

---

## Telegram HTML parse error

- **증상**: Telegram 메시지가 도착 안 함 또는 plain text로만 도착.
- **원인**: 메시지 본문에 `<`, `>` 같은 HTML 메타 문자가 escape 안 됨, 또는 닫히지 않은 `<b>` 태그.
- **해결**: HTML parse 에러 감지 시 plain text fallback으로 자동 재전송.
- **복구 절차**: 자동. 수동 검증은 `python -c "from shared.telegram_bot import send_text; send_text('test &<>')"`.
- **관련 사고**: 2026-03-20 (telegram-underscore-escape), 2025-12-20 (telegram-html-parsing-error)
- **재발 감지**: `Telegram HTML parse error` 로그 빈도. 일일 0건이 정상.

---

## Sector Weekly Summary가 N-1/N 으로 나감 (스케줄 충돌)

- **증상**: 일요일 텔레그램 Weekly Summary가 `10/11` 등 마지막 섹터 1개 빠진 상태로 도착. 직후 마지막 섹터가 정상 업로드됨.
- **원인**: `investment_bot.py`의 Weekly Summary 시각이 마지막 섹터 시작 시각보다 **앞**에 등록돼 있었음. `config.py`의 sector 11(필수 소비재) `scheduled_time="18:40"` vs 통합 봇의 Weekly Summary `18:30` → summary가 sector 11 시작 전에 트리거. (단독 실행 모드 `weekly_sector_bot.py:263`은 `19:20`으로 올바름.)
- **해결**: `investment_bot.py:127`의 Weekly Summary `18:30 → 19:20`, `:132`의 Comprehensive Report `19:00 → 19:40`. 단독 실행·문서·통합 모드 3자 일치.
- **복구 절차**: 코드 수정 후 다음 일요일까지 대기 (당일 데이터는 sector 파일 모두 정상이므로 `python weekly_sector_bot.py --comprehensive`로 수동 재생성 가능).
- **관련 사고**: 2026-05-10
- **재발 감지**: `[WeeklySummary] Triggered` 로그 시각이 마지막 섹터 `Completed` 시각보다 앞이면 alert. `tail logs/investment_bot_*.log | grep -E "Sector-11.*Completed|WeeklySummary] Triggered"`로 순서 확인.

---

## Comprehensive Report 업로드 Broken pipe

- **증상**: 종합 투자 평가 보고서 단계에서 `Upload failed: [Errno 32] Broken pipe`. 텔레그램으로 ❌ 실패 메시지 도착. 섹터 파일과 종합 MD/HTML은 정상 생성됨.
- **원인**: 마지막 섹터 업로드 이후 30분 이상 idle 후 cached `service.posts().insert()`를 그대로 호출. 그 사이 HTTP/2 keep-alive 또는 SSL 세션이 서버 측에서 종료된 상태에서 종합 HTML(타 섹터의 4-5배, ~118KB)을 한 번에 송신 → 첫 패킷 직후 broken pipe. `is_authenticated()`는 토큰 유효성만 검사하고 실제 connection은 검증하지 않음.
- **해결**: `shared/blogger_uploader.py`에 `_insert_with_retry()` 추가. `BrokenPipeError`/`ConnectionResetError`/`ConnectionError`/`RemoteDisconnected`/`SSLError`/`socket.error` 발생 시 `self.service = None` 후 `authenticate()` 재호출하고 1회 재시도. 모든 호출자(섹터/뉴스/버핏/종합) 적용.
- **복구 절차**: 일시적 실패면 자동 재시도로 복구. 재시도도 실패하면 sector 파일이 모두 살아있는지 확인 후 `python weekly_sector_bot.py --comprehensive`로 수동 재생성.
- **관련 사고**: 2026-05-10
- **재발 감지**: `Connection lost` WARNING 로그 (재시도 발생 신호). 동일 세션에 2회 이상이면 네트워크 또는 Blogger 서버 이슈 의심.

---

## Sector bot resume 실패

- **증상**: `weekly_sector_bot.py --once` 실행 시 "다른 주에 시작" 메시지로 거부.
- **원인**: `state.json`이 이전 주에 시작된 상태 보존. 일요일이 아닌 시점에 `--once` 호출 시 state 충돌.
- **해결**: `--reset` 후 `--once` 실행.
- **복구 절차**:
  ```bash
  python weekly_sector_bot.py --reset
  python weekly_sector_bot.py --once
  ```
- **관련 사고**: 정기적 (수동 호출 시 빈번)
- **재발 감지**: `state mismatch` 로그.

---

## Sector state 손상

- **증상**: 섹터 봇 시작 시 JSON parse error 또는 비정상 상태.
- **원인**: `state.json`이 비정상 종료(SIGKILL, 디스크 full)로 손상.
- **해결**: state 파일 reset.
- **복구 절차**: `python weekly_sector_bot.py --reset` 후 다음 일요일 13:00 자동 실행 또는 즉시 `--once`.
- **관련 사고**: 드뭄
- **재발 감지**: 시작 시 JSON parse error 즉시 alert.

---

## Blog selection timeout

- **증상**: 사용자에게 블로그 선택 prompt 보냈는데 응답 없음 → 봇이 timeout 후 default blog 사용.
- **원인**: `BLOG_SELECTION_TIMEOUT`(기본 180초) 내 응답 없음. 정상 동작이지만 default blog가 의도와 다를 수 있음.
- **해결**: `.env`에서 `BLOG_SELECTION_TIMEOUT` 값 조정 또는 `DEFAULT_BLOG`를 가장 자주 쓰는 블로그로 설정.
- **복구 절차**: 잘못 업로드된 블로그에서 글 삭제 후 정확한 블로그에 재업로드.
- **관련 사고**: 사용자 운영 패턴
- **재발 감지**: 일일 default blog 사용 비율 추적.

---

## ModuleNotFoundError

- **증상**: 봇 시작 시 import 에러.
- **원인**: venv 미활성화 또는 dependency 누락.
- **해결**:
  ```bash
  cd 006_auto_bot/001_code
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- **복구 절차**: venv 재생성 필요 시 `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
- **관련 사고**: 환경 설정
- **재발 감지**: 시작 직후 ImportError → 즉시 fail-fast.

---

## 로그 파일 위치

```
logs/
├── investment_bot_YYYYMMDD.log  # 통합 오케스트레이터
├── news_bot_YYYYMMDD.log        # 뉴스봇
├── buffett_bot_YYYYMMDD.log     # 버핏봇
└── sector_bot_YYYYMMDD.log      # 섹터봇
```
