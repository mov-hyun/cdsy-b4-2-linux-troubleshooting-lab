# [Bug] CPU 부하 시나리오에서 Watchdog가 SIGTERM으로 종료

## 1. Description (현상 설명)

2026-09-16 Ubuntu 24.04에서 MEMORY_LIMIT=512, CPU_MAX_OCCUPY=100, MULTI_THREAD_ENABLE=false로 실행했다. CpuWorker의 Current Load 로그가 5.00%에서 50.69%까지 증가한 뒤 CPU Threshold Violated를 기록하며 종료했다. 전체 실행 시간은 약 28초, 종료 코드는 143이었다.

제공 바이너리를 준비한 뒤 프로젝트 루트의 Ubuntu 터미널에서 재현한다. 이미 있는 실험 이름은 새 이름으로 바꾼다.

```bash
bash scripts/run-case.sh review-cpu-before 512 100 false 90
bash scripts/run-case.sh review-cpu-after 512 40 false 65
```

## 2. Evidence & Logs (증거 자료)

| 증거 | CPU_MAX_OCCUPY=100 | CPU_MAX_OCCUPY=40 |
| --- | --- | --- |
| 실행 로그 | [application.log](../evidence/cpu-before/application.log) | [application.log](../evidence/cpu-after/application.log) |
| monitor.sh | [monitor.tsv](../evidence/cpu-before/monitor.tsv) | [monitor.tsv](../evidence/cpu-after/monitor.tsv) |
| top 스레드 표본 | [top-threads.txt](../evidence/cpu-before/top-threads.txt) | [top-threads.txt](../evidence/cpu-after/top-threads.txt) |
| ps 관측 | [process-snapshots.txt](../evidence/cpu-before/process-snapshots.txt) | [process-snapshots.txt](../evidence/cpu-after/process-snapshots.txt) |
| 실행 결과 | [result.txt](../evidence/cpu-before/result.txt) | [result.txt](../evidence/cpu-after/result.txt) |

```text
2026-09-16 21:00:41,507 [INFO] [CpuWorker] Current Load: 50.69%
2026-09-16 21:00:41,610 [CRITICAL] [CpuWorker] CPU Threshold Violated! (50.69%).
```

종료 직전 표준 출력이 파일 리다이렉션에서 일부 누락되어 가상 터미널로 같은 설정을 추가 실행했다. [콘솔 확인 로그](../evidence/console-confirmation/cpu-100.log)에서 다음 문구와 [종료 코드 143](../evidence/console-confirmation/cpu-100-result.txt)을 확인했다.

```text
>>> [SYSTEM] WATCHDOG: INITIATING EMERGENCY ABORT (SIGTERM) <<<
```

콘솔 추가 실행에서는 Current Load 53.59% 부근에서 종료했다. 반복 실행의 부하 로그와 종료 시점이 달라질 수 있어 각 실행을 별도 증거로 보관한다.

### 짧은 CPU 급상승 추가 관측

1초 평균이 짧은 부하를 희석할 가능성을 확인하기 위해 동일한 512/100/false 설정을 유지하고 `top -b -H -d 0.1`로 추가 측정했다.

```bash
TOP_INTERVAL_SECONDS=0.1 bash scripts/run-case.sh cpu-burst 512 100 false 90
```

[0.1초 간격 top 원본](../evidence/cpu-burst/top-threads.txt)에서 작업 PID 412의 CPU가 0.0%인 표본 사이에 최대 40.0%인 표본이 관측되었다. 21:08:20과 21:08:23에 40.0% 표본이 있으며 시스템 전체 idle은 각각 97.6%, 96.9%였다. 특정 프로세스의 짧은 부하 상승을 시스템 전체 포화와 구분할 수 있다.

[해당 실행 로그](../evidence/cpu-burst/application.log)는 Current Load 54.35%에서 보호 종료를 기록했다. 이는 OS의 CPU 표본과 같은 지표라는 뜻은 아니다. 추가 실행 시간은 약 30초였다. 0.1초 표본의 최댓값은 1초 간격 Before/After 표와 직접 비교하지 않는다.

## 3. Root Cause Analysis (원인 분석)

애플리케이션의 부하 증가 시나리오에서 내부 보호 조건에 도달해 Watchdog가 SIGTERM 종료를 요청한 것으로 판단한다. 로그의 보호 조치 문구와 143(128+SIGTERM의 신호 번호 15) 종료 코드가 일치한다. 종료 코드만으로 발신 주체를 알 수는 없으므로 보호 정책 로그와 실험 스크립트의 종료 여부를 함께 근거로 삼았다.

CPU_MAX_OCCUPY=100이라고 해서 실제 CPU 사용률이 100%를 넘어서 종료한 것은 아니다. 로그의 Current Load 약 50%에서 종료되었고, 1초 간격 top 표본의 실제 사용률 최댓값은 5.0%였다. 따라서 환경변수 값, 애플리케이션 내부 부하 표시, OS의 실제 CPU 사용률을 각각 구분한다. 내부 임계치 계산식은 바이너리 역분석 없이 확인할 수 없다.

일반적으로 실행 가능한 작업이 특정 CPU를 오래 점유하면 다른 작업이 CPU를 배정받기까지 기다려 응답 지연이 생길 수 있다. 이번 실험에서 사용자 요청의 실제 응답 시간이나 시스템 전체 지연을 측정하지 않았으므로 그 지연을 실증한 것으로 주장하지 않는다.

## 4. Workaround & Verification (조치 및 검증)

MEMORY_LIMIT=512와 MULTI_THREAD_ENABLE=false를 유지하고 CPU_MAX_OCCUPY만 100에서 40으로 낮췄다.

| 항목 | Before | After |
| --- | --- | --- |
| CPU_MAX_OCCUPY | 100 | 40 |
| 작업 PID | 421 | 1158 |
| 로그의 최대 Current Load | 50.69% | 40.00% |
| top 1초 구간 CPU 최댓값 | 5.0% | 9.9% (스레드 합계) |
| 전체 실행 시간 | 약 28초 | 약 68초 |
| 종료 주체 | Watchdog | 65초 관찰 후 실험 스크립트 |
| 동작 | 임계 위반 후 종료 | 부하 감소·재증가, 메모리 정리 로그 지속 |

After는 다음 로그를 남겼고, 관찰 기간 동안 Watchdog 종료가 없었다.

```text
Peak reached (40.00%). Starting cooldown...
Cooldown complete (5.00%). Resuming load increase...
Memory Cache Flushed. Process Stabilized.
```

After의 종료 코드도 143이지만 STOPPED_BY_HARNESS=true다. 이는 관찰 종료를 위한 SIGTERM이며 장애 종료와 구분한다. After에서는 MemoryWorker 등 여러 작업 스레드가 동작하므로 실제 top 사용률이 Before보다 낮아졌다고 주장하지 않는다. 확인한 개선은 관찰 기간 동안 Watchdog 종료를 회피하고 작업이 계속된 것이다.
