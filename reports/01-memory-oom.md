# [Bug] 메모리 누적으로 MemoryGuard가 프로세스를 강제 종료

| 치명도 | 우선순위 | 영향 범위 | 탐지 | 확산 가능성 |
| --- | --- | --- | --- | --- |
| SEV2 Major | P2 | 수 초마다 강제 종료(137), 재시작해도 재발 | 쉬움. 종료 로그, RSS 경보가 종료 2초 전 | 높음. 한도를 올릴수록 호스트 메모리 잠식 |

등급 기준: [장애 치명도·우선순위 기준](../docs/incident-response.md)

## 1. Description (현상 설명)

2026-09-16 Ubuntu 24.04에서 MEMORY_LIMIT=50, CPU_MAX_OCCUPY=100, MULTI_THREAD_ENABLE=false로 실행했다. MemoryWorker의 Current Heap이 25MB에서 50MB로 증가한 직후 MemoryGuard가 종료를 기록했다. 전체 실행 시간은 약 6초, 종료 코드는 137이었다.

프로젝트 루트의 Ubuntu 터미널에서 다음 명령으로 재현한다. 제공 x86 바이너리를 `agent-app-leak/agent-leak-app-x86`에 둔다. 스크립트가 과제용 환경변수·디렉터리·테스트 키를 준비한다. 기존 폴더가 있으면 새 실험 이름을 사용한다.

```bash
bash scripts/run-case.sh review-oom-before 50 100 false 90
bash scripts/run-case.sh review-oom-after 100 100 false 90
```

## 2. Evidence & Logs (증거 자료)

| 증거 | 50MB 실행 | 100MB 실행 |
| --- | --- | --- |
| 프로그램 로그 | [application.log](../evidence/oom-before/application.log) | [application.log](../evidence/oom-after/application.log) |
| monitor.sh 출력 | [monitor.tsv](../evidence/oom-before/monitor.tsv) | [monitor.tsv](../evidence/oom-after/monitor.tsv) |
| 프로세스 상태 | [ps 출력](../evidence/oom-before/process-snapshots.txt) | [ps 출력](../evidence/oom-after/process-snapshots.txt) |
| 설정·바이너리 식별 | [environment.txt](../evidence/oom-before/environment.txt) | [environment.txt](../evidence/oom-after/environment.txt) |
| 종료 결과 | [result.txt](../evidence/oom-before/result.txt) | [result.txt](../evidence/oom-after/result.txt) |

50MB 실행에서 다음 로그를 확인했다.

```text
Memory limit exceeded (50MB >= 50MB) / (Recommend Over 256MB)
Self-terminating process 420 to prevent system instability.
```

작업 PID 420의 RSS는 17,664 KiB에서 43,264 KiB로 증가했다. 100MB 실행의 작업 PID 778은 17,792 → 43,392 → 68,992 → 94,592 KiB로 증가했다. 세부 표본은 원본 TSV를 따른다.

프로그램이 50MB 또는 100MB 할당을 기록하고 곧바로 종료하므로 1초 주기의 RSS 관측에서는 마지막 할당 직전까지만 포착되었다. Current Heap과 RSS는 서로 다른 측정값이며 동일시하지 않았다.

파일 리다이렉션에서 강제 종료 직전 표준 출력이 일부 빠져, 가상 터미널로 같은 설정을 추가 실행했다. [50MB 콘솔 확인](../evidence/console-confirmation/oom-50.log)과 [100MB 콘솔 확인](../evidence/console-confirmation/oom-100.log)에서 `SELF-TERMINATED (Memory Limit Exceeded)`를 확보했다. 추가 실행의 PID와 시각은 본 비교 실행과 다르며, 본 표의 시간·RSS에 합산하지 않았다.

### 조기 경보 검증

같은 50MB 설정에 `ALERT_RSS_KIB=40960`(한도의 80%)을 주고 다시 실행했다([oom-alert](../evidence/oom-alert/alerts.log)). 00:42:59에 `MEM rss_kib=43392` 경보가 났고, 00:43:01에 MemoryGuard가 종료를 기록했다. 종료 2초 전에 알 수 있었지만, 누수 속도가 빨라 선행 시간이 짧다. 개선 방향은 [관제 정책](../docs/monitoring-policy.md)에 정리했다.

## 3. Root Cause Analysis (원인 분석)

주기적인 메모리 증가와 MemoryGuard 로그를 종합하면, 이 실행 경로에서 누적된 메모리가 설정된 한계에 도달해 애플리케이션이 자체 보호 정책에 따라 종료한 것으로 판단한다. 종료 코드 137은 SIGKILL 종료와 일치한다.

시스템 RAM 전체가 고갈되어 Linux 커널의 OOM killer가 개입했다는 증거는 없다. 이 과제의 OOM 사례는 애플리케이션의 메모리 한도 초과 사례로 해석한다. 바이너리를 역분석하지 않았으므로 어떤 변수나 자료구조가 메모리를 보유하는지는 확정할 수 없다.

RSS는 RAM에 상주하는 프로세스 메모리다. 할당량 증가가 지속되면 프로세스의 물리 메모리 사용량이 증가하며 시스템의 여유 메모리가 줄어들 수 있다. [Linux 커널 문서](https://docs.kernel.org/filesystems/proc.html)

프로세스의 가상 주소 공간에는 실행 코드, 전역 데이터, 동적 할당 영역(힙), 스레드별 호출 상태를 보관하는 스택 등이 있다. 이번 로그의 Current Heap은 애플리케이션이 보고한 할당량이며 프로세스 전체 RSS와 측정 범위가 다르다. 불필요해진 객체를 계속 참조해 동적 할당 메모리가 회수되지 않으면 누수가 발생할 수 있다. 이번 관측은 이 경로에서 메모리가 누적되는 사실을 보여 주며, 구체적인 참조 관계는 확인하지 않았다.

시스템 전체의 여유 메모리가 부족해지면 페이지 회수와 스왑으로 작업이 느려질 수 있고, 회수가 충분하지 않으면 커널의 메모리 부족 처리가 개입할 수 있다. 이번 실행은 자체 MemoryGuard가 먼저 종료했으며, 시스템 전체 메모리 고갈이나 스왑 지연을 재현한 실험은 아니다.

## 4. Workaround & Verification (조치 및 검증)

다른 설정은 유지하고 MEMORY_LIMIT만 50에서 100으로 변경했다.

| 항목 | Before | After |
| --- | --- | --- |
| MEMORY_LIMIT | 50MB | 100MB |
| CPU_MAX_OCCUPY / MULTI_THREAD_ENABLE | 100 / false | 100 / false |
| 전체 실행 시간 | 약 6초 | 약 13초 |
| 로그의 마지막 Current Heap | 50MB | 100MB |
| 관측 RSS 최댓값 | 43,264 KiB | 94,592 KiB |
| 종료 | MemoryGuard, 137 | MemoryGuard, 137 |

전체 시간에는 부팅과 관측 루프 확인 지연이 포함된다. 제한을 늘리자 생존 시간이 늘어났지만 다시 종료되었으므로, 이번 변경은 메모리 누적을 해결한 조치가 아니다.

근본 개선안은 불필요한 데이터 참조를 해제하고 캐시 용량과 수명에 상한을 두는 것이다. 실제 소스 수정은 수행하지 않았다. 512MB·CPU 40%·멀티스레드 false의 별도 실행에서는 메모리 정리 로그가 관측되지만, 여러 설정이 달라 이 표의 단일 변수 비교와 구분한다.
