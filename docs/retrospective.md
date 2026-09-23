# 회고: 실험 재현·증거 보존·자동화

## 1. 잘된 점 (Keep)

- **한 번에 한 변수만 바꿨다.** 모든 Before/After 쌍이 같은 바이너리 해시에서 한 환경변수만 다르다. 검증기가 이를 자동으로 검사한다.
- **증거와 결론을 분리했다.** 원본 로그·관측 파일을 먼저 남기고, 수치는 `summarize.py`가 원본에서 다시 계산한다. 리포트의 숫자를 사람이 옮겨 적다 틀릴 여지를 줄였다.
- **해석 범위를 명시했다.** 앱의 `Current Load`와 OS CPU, `futex_wait_queue`와 교착 확정처럼 증거가 말하지 않는 부분은 단정하지 않았다.

## 2. 문제와 원인 (Problem)

| 문제 | 원인 | 조치 |
| --- | --- | --- |
| 초기 관측에서 메모리 증가를 놓쳤다. | PyInstaller 런처(부모) PID만 봤다. 실제 할당은 자식 프로세스가 한다. | `monitor.sh`가 부모와 자식을 함께 기록한다. `discovery`는 비교에서 제외했다. |
| 강제 종료 직전 표준 출력 일부가 파일에 남지 않았다. | 파일 리다이렉션 버퍼가 비워지기 전에 종료됐다. | 가상 터미널로 추가 실행해 `SELF-TERMINATED` 문구를 확보했다(`console-confirmation`). |
| CPU 급상승이 작게 보였다. | `ps %CPU`는 실행 이후 평균이다. | `top -H` 0.1초 표본을 추가했고, 이번에 `monitor.sh`에 구간 CPU(`cpu_interval_pct`)를 넣었다. |
| 공개 로그에 로컬 계정·호스트·경로가 들어갈 뻔했다. | 원본을 그대로 `evidence/`에 기록했다. | 원본은 Git 제외 경로에 두고 마스킹 사본만 내보낸다([마스킹 범위](evidence-privacy.md)). 커밋 전 `check-privacy.py`로 검사한다. |
| 데드락의 스레드별 콜스택을 뜨지 못했다. | gdb 미설치, root 권한 없음, Yama `ptrace_scope=1`, PyInstaller가 `PYTHONFAULTHANDLER`를 무시한다. | 실행 스크립트(조상 프로세스)가 `/proc/TID/syscall`로 스레드별 대기 futex 주소와 문맥 교환 수를 기록하게 했다(`deadlock-stack`). |
| `monitor.sh`가 기록만 하고 알리지 않았다. | 사후 분석용으로만 설계했다. | 메모리·CPU·로그 정지 경보를 추가했다([정책](monitoring-policy.md)). CPU 경보가 OS 지표로는 앱 Watchdog을 예측하지 못한다는 점도 실측으로 확인했다. |

## 3. 개선 체크리스트 (실행 계획)

| 상태 | 항목 | 실행 방법 | 완료 기준 |
| --- | --- | --- | --- |
| 완료 | 원본 → 마스킹 사본 자동 내보내기 | `run-case.sh`가 끝날 때 `redact-evidence.py` 실행 | 공개 증거에 `labuser`, `lab-host`만 남음 |
| 완료 | 증거 무결성 기준선 | `evidence/SHA256SUMS`, 새 증거는 `validate-evidence.py --refresh`로 명시 등록 | 파일 변조·누락 시 검증 실패 |
| 완료 | 관제 경보와 스레드 대기 수집 | `monitor.sh` 경보 3종, `run-case.sh`의 `thread-waits.txt` | `tests/test_monitor.py` 통과, 실측 3건 기록 |
| 완료 | 커밋마다 자동 검사 | [GitHub Actions](../.github/workflows/checks.yml)에서 문법 검사, 단위 테스트(Linux 전용 포함), 증거 검증 실행 | push·PR마다 통과 표시 |
| 예정 | 커밋 전 개인정보 검사 자동화 | `check-privacy.py`를 Git pre-commit 훅으로 등록 | 로컬 경로·실제 이메일이 포함된 커밋이 만들어지지 않음 |
| 예정 | 앱 지표 기반 CPU 경보 | `Current Load` 로그를 파싱하는 경보를 `monitor.sh`에 추가 | cpu-alert 재실행에서 Watchdog 종료 전 경보 |
| 예정 | RSS 증가율 경보 | 직전 표본 대비 KiB/s로 한도 도달 예상 시각 계산 | oom-alert 재실행에서 선행 시간 2초 초과 |
| 예정 | 콘솔 유실 없는 단일 실행 | `run-case.sh`가 `pty-exec.py`로 앱을 실행 | `console-confirmation` 별도 실행 불필요 |
| 예정 | 반복 측정 | 조건마다 3회 실행하고 생존 시간의 최소·최대를 기록 | 리포트 Before/After 표에 범위 표기 |

## 4. 다음 실습에 가져갈 원칙

1. 재시작 전에 증거부터 남긴다. `ps`, 로그 꼬리, 스레드 상태를 1분 안에 수집하는 스크립트를 먼저 준비한다.
2. 관측 대상 PID가 실제 일을 하는 프로세스인지 먼저 확인한다.
3. "평균"과 "구간" 지표를 구분하고, 알림은 구간 지표로 건다.
4. 공개할 증거는 처음부터 마스킹 경로로 내보낸다.
