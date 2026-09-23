# monitor.sh 탐지·알림·샘플링 정책

`monitor.sh`는 관제 수치를 TSV로 남기는 데서 그치지 않고, 세 장애 유형의 조기 신호를 알림으로 분리해 출력한다. 구현은 [scripts/monitor.sh](../scripts/monitor.sh), 동작 검사는 [tests/test_monitor.py](../tests/test_monitor.py)(Linux 전용)다.

## 1. 출력 규칙

| 출력 | 내용 | 저장 위치 (`run-case.sh`) |
| --- | --- | --- |
| stdout (TSV) | `timestamp, pid, state, cpu_lifetime_pct, mem_pct, rss_kib, vsz_kib, threads, elapsed_seconds, cpu_interval_pct` | `monitor.tsv` |
| stderr (알림) | `ALERT<TAB>시각<TAB>유형 pid=… 값 threshold=…` 조건이 시작될 때 1회, `RESOLVED` 조건이 풀릴 때 1회 | `alerts.log` |

- `cpu_lifetime_pct`는 `ps %CPU`로, 프로세스 시작 이후의 평균이다. 급상승 판단에 쓰지 않는다.
- `cpu_interval_pct`는 `/proc/PID/stat`의 utime+stime 증가량을 직전 표본과의 시간 차로 나눈 구간 CPU다. 알림은 이 값으로 판단한다.
- 같은 조건이 계속되는 동안 매 표본마다 알림을 반복하지 않는다. 알림 폭주를 막고, 로그에서 시작·해소 시각을 바로 읽기 위해서다.

## 2. 탐지 조건과 알림 임계값

| 장애 | 탐지 지표 | 알림 조건 (환경변수) | 권장 임계값 | 근거 |
| --- | --- | --- | --- | --- |
| 메모리 누수 | 작업 프로세스 RSS | `ALERT_RSS_KIB` 이상 | `MEMORY_LIMIT × 1024 × 0.8` KiB | MemoryGuard 종료 전에 20% 여유를 두고 알린다. |
| CPU 과점유 | `cpu_interval_pct` | `ALERT_CPU_PCT` 이상 | `CPU_MAX_OCCUPY × 0.8` % | 앱 한도 도달 전 경고. 단, 아래 실측 한계를 참고한다. |
| 교착·무응답 | 로그 파일 마지막 수정 이후 경과 시간 | `ALERT_LOG_FILE`이 `ALERT_STALL_SECONDS` 동안 변하지 않음 (PID는 살아 있음) | 15초 | 정상 실행에서 MemoryWorker·CpuWorker 로그가 약 3초 주기로 남으므로 5주기 연속 누락이다. |

`run-case.sh`는 `ALERT_LOG_FILE`을 해당 실행의 `application.log`로, `ALERT_STALL_SECONDS`를 15로 기본 설정한다. 메모리·CPU 임계값은 실행할 때 지정하며, 적용한 값은 `environment.txt`에 기록된다.

STALL 알림이 오면 `monitor.tsv`의 구간 CPU로 원인을 가른다. 0%면 잠금 대기(교착)이고, 높으면 무한 루프처럼 CPU를 쓰면서 로그만 멈춘 상태다.

## 3. 실측 검증

| 실행 | 설정 | 알림 | 결과 |
| --- | --- | --- | --- |
| [oom-alert](../evidence/oom-alert/alerts.log) | MEMORY_LIMIT=50, `ALERT_RSS_KIB=40960` | 00:42:59 `MEM rss_kib=43392` | 00:43:01 MemoryGuard 종료. **2초 먼저 경보** |
| [deadlock-stack](../evidence/deadlock-stack/alerts.log) | MULTI_THREAD_ENABLE=true, STALL 15초 | 00:40:59 `STALL log_idle_seconds=15` | 마지막 로그 00:40:44. PID 유지, 구간 CPU 0% |
| [cpu-alert](../evidence/cpu-alert/alerts.log) | CPU_MAX_OCCUPY=100, `ALERT_CPU_PCT=80` | 없음 | OS 구간 CPU 최대 4%. 앱은 `Current Load: 52.96%`에서 Watchdog 종료 |

CPU 결과는 **OS 지표로는 이 앱의 Watchdog 종료를 예측할 수 없다**는 뜻이다. 앱이 판단에 쓰는 `Current Load`는 OS가 집계하는 프로세스 CPU와 다른 지표다. 운영에서 CPU 경보가 의미를 가지려면 앱이 내보내는 부하 지표를 함께 수집해야 한다(4절).

## 4. 샘플링 정책

| 도구 | 주기 | 선택 이유 | 한계 |
| --- | --- | --- | --- |
| `monitor.sh` | 1초 (두 번째 인자) | RSS 추세와 생존 여부를 보기에 충분하고, `ps`와 `/proc` 읽기라 오버헤드가 작다. | 1초보다 짧은 CPU 급상승은 평균에 묻힌다. |
| `top -b -H` | 기본 1초, 짧은 급상승 추적 시 0.1초 (`TOP_INTERVAL_SECONDS`) | 스레드별 구간 CPU를 본다. | 0.1초는 파일이 커지고(cpu-burst 약 150KB), 첫 화면은 누적값이라 분석에서 뺀다. |
| `thread-waits.txt` (`run-case.sh`) | 2초 | 스레드별 대기 시스템 콜·futex 주소·문맥 교환 수의 변화 여부를 본다. | Yama `ptrace_scope=1`에서는 조상 프로세스만 `/proc/TID/syscall`을 읽을 수 있다. |

## 5. 운영 개선안 (미구현)

- **앱 지표 기반 CPU 경보:** `Current Load` 로그를 파싱해 `CPU_MAX_OCCUPY`의 80%를 넘으면 알린다. 3절에서 OS 지표만으로는 부족함을 확인했다.
- **RSS 증가율 경보:** 50MB 한도에서는 누수가 약 6초 만에 한도에 닿아, 절대값 경보의 선행 시간이 2초뿐이었다. KiB/s 기울기로 "한도 도달 예상 시각"을 알리면 선행 시간을 늘릴 수 있다.
- **알림 전달:** 지금은 파일로만 남는다. 운영에서는 `ALERT` 줄을 메신저나 페이저로 보내고, 치명도에 따라 수신자를 나눈다([장애 대응 기준](incident-response.md)).

## 6. 사용 예

```bash
ALERT_RSS_KIB=40960 bash scripts/run-case.sh my-oom-alert 50 100 false 60
ALERT_CPU_PCT=80 bash scripts/run-case.sh my-cpu-alert 512 100 false 60
bash scripts/run-case.sh my-deadlock-stack 512 40 true 60
ALERT_LOG_FILE=app.log ALERT_STALL_SECONDS=15 bash scripts/monitor.sh 12345 1 > monitor.tsv 2> alerts.log
```
