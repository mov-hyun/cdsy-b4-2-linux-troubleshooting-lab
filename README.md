# Linux Troubleshooting Lab — Codyssey B4-2

제공된 `agent-leak-app`을 Ubuntu에서 실행하고 메모리 누수/OOM, CPU 과점유, 교착상태를 외부 관측 자료로 분석한다. 설정 변경 전후의 실행 로그와 Linux 프로세스 관측값을 함께 보관한다.

## 읽는 순서

1. [과제 요구사항](docs/requirements.md)
2. [실험 진행과 명령어 해설](docs/experiment-guide.md)
3. [메모리 누수/OOM](reports/01-memory-oom.md), [CPU와 Watchdog](reports/02-cpu-watchdog.md), [교착상태](reports/03-deadlock.md), (선택) [스케줄링 추론](reports/04-scheduling.md)
4. [수치 요약](evidence/summary.json)과 `evidence/`의 원본 로그
5. [과제 요구사항 정밀 검토와 해석 한계](docs/assignment-review.md)
6. [공개 증거의 개인정보 마스킹 범위](docs/evidence-privacy.md)

## 실행 환경

- Windows의 WSL2, Ubuntu 24.04.3 LTS, x86_64
- 일반 사용자 `labuser` (uid 1000)
- 제공 파일: `agent-app-leak/agent-leak-app-x86`
- Bash, Python 3 표준 라이브러리, ps, top, pgrep, ss

제공 바이너리는 직접 준비한다. `.gitignore`는 제공 바이너리/압축 파일과 실행용 임시 폴더를 제외한다. 바이너리 내부 분석이나 디컴파일은 수행하지 않는다. 실행 파일의 SHA-256은 각 실험의 `environment.txt`에 기록한다. 공개 로그는 로컬 계정·호스트명·개인 경로를 마스킹한 사본이며 측정값과 장애 메시지는 유지했다.

## 재현

Ubuntu 터미널에서 이 프로젝트 디렉터리로 이동한 뒤 실행한다.

```bash
bash scripts/run-case.sh my-oom-before 50 100 false 90
bash scripts/run-case.sh my-oom-after 100 100 false 90
python3 scripts/summarize.py
```

스크립트는 `.runtime/agent`에 과제용 디렉터리와 지정된 테스트 키를 만든다. 기존 실험 폴더를 덮어쓰지 않으며 15034 포트가 사용 중이면 시작하지 않는다.

## 증거 해석

- `application.log`: 애플리케이션이 출력한 메시지. 자체 부하 표시값과 실제 CPU 점유율을 구분한다.
- `monitor.tsv`: 실행용 부모 및 작업용 자식 프로세스의 RSS(KiB), 평균 CPU, 상태, 스레드 수.
- `top-threads.txt`: 작업용 자식의 스레드별 CPU 구간 표본.
- `process-snapshots.txt`: PID/PPID, 스레드 상태, 커널 대기 위치.
- `result.txt`: 종료 코드, 전체 실행 시간, 관측 스크립트에 의한 종료 여부.

관찰 시간 종료로 중단한 실행은 자연 종료나 장애 복구 완료로 해석하지 않는다. 제공 예시의 수치와 실제 측정값을 섞지 않는다.

## 주요 결과

| 사례 | 설정 변경 | 실측 결과 |
| --- | --- | --- |
| 메모리 | MEMORY_LIMIT 50 → 100 | MemoryGuard 종료까지 전체 시간 약 6 → 13초. 두 실행 모두 종료하여 임시 조치임을 확인. |
| CPU | CPU_MAX_OCCUPY 100 → 40 | 약 28초 후 Watchdog 종료 → 65초 관찰 동안 작업 지속. 별도 0.1초 표본에서 실제 CPU 순간 최대 40.0% 관측. |
| 교착상태 | MULTI_THREAD_ENABLE true → false | A/B 순환 대기와 로그 정체 → 작업 및 메모리 정리 로그 지속. |

After 실행은 관찰 종료 후 스크립트로 중단했다. 종료 처리까지 포함한 전체 시간은 CPU 약 68초, 교착상태 약 67초다. 프로그램의 Current Load 표시와 top의 실제 CPU 표본은 다른 지표로 취급한다.

## 추가 확인과 제출 범위

`evidence/discovery`는 부모 PID만 관측한 초기 탐색 자료다. 정식 수치 비교에서 제외했다. `high-memory-discovery`는 CPU 경로를 확인한 탐색 실행이며, `cpu-burst`는 짧은 CPU 급상승을 확인한 0.1초 표본이다. `console-confirmation`은 강제 종료 직전 콘솔 문구를 가상 터미널로 추가 수집한 자료다.

필수 보고서 3건과 선택 과제인 스케줄링 추론 1건은 GitHub Issue 구조의 Markdown으로 작성했고, 같은 내용을 GitHub Issues에도 등록했다. 이 레포 링크를 제출 자료로 사용한다.

## 검증

```bash
bash -n scripts/monitor.sh scripts/run-case.sh scripts/verify-console.sh
python3 scripts/summarize.py
python3 scripts/validate-evidence.py
sha256sum -c evidence/SHA256SUMS
```

검증 항목은 원본 해시, 요약값과 원본의 일치, 단일 환경변수 비교, 바이너리 동일성, 필수 증거·보고서 구조, 문서 링크다. 상세 통과 수는 `evidence/validation.json`, 파일 목록과 해시는 `evidence/SHA256SUMS`에 있다. 이 검증은 관측값의 연결성과 기본 조건을 확인하며, 모든 원인 해석을 자동으로 증명하는 검사는 아니다.

일반 검증은 읽기 전용이다. 새 실험이나 문서 수정 후 검토를 마친 경우에만 `python3 scripts/validate-evidence.py --refresh`로 파생 검증 결과와 해시 목록을 갱신한다. 이때도 기존 원본 증거의 해시가 바뀌었으면 갱신을 거부한다.

```bash
python3 -m unittest discover -s tests -v
```

격리된 임시 복사본에서 정상 검증의 읽기 전용 동작, 원본 로그 변조, 원본 누락 탐지를 검사한다.

커밋 전 `python3 scripts/check-privacy.py`로 Git 인덱스의 개인정보 패턴과 작성자 noreply 주소를 점검한다. 이 검사는 알려진 패턴을 대상으로 하므로 수동 검토도 함께 수행한다.
