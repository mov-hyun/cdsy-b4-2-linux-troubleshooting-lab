# [Bug] 멀티스레드의 순환 잠금 대기로 프로세스 무응답

## 1. Description (현상 설명)

2026-09-16 Ubuntu 24.04에서 MEMORY_LIMIT=512, CPU_MAX_OCCUPY=40, MULTI_THREAD_ENABLE=true로 실행했다. 부팅 후 두 작업 스레드가 서로 다른 자원을 획득한 다음 상대 자원을 요청하며 멈췄다. 프로세스는 살아 있었지만 작업 로그가 추가되지 않았다.

제공 바이너리를 준비한 뒤 프로젝트 루트의 Ubuntu 터미널에서 재현한다. 이미 있는 실험 이름은 새 이름으로 바꾼다.

```bash
bash scripts/run-case.sh review-deadlock-before 512 40 true 65
bash scripts/run-case.sh review-deadlock-after 512 40 false 65
```

## 2. Evidence & Logs (증거 자료)

- [실행 로그](../evidence/deadlock-before/application.log)
- [PID와 스레드 대기 상태](../evidence/deadlock-before/process-snapshots.txt)
- [메모리와 평균 CPU](../evidence/deadlock-before/monitor.tsv)
- [스레드별 CPU 구간 표본](../evidence/deadlock-before/top-threads.txt)
- [실험 종료 기록](../evidence/deadlock-before/result.txt)

작업 프로세스 PID는 2323이다. 21:01:57에 스레드 1은 Shared_Memory_A, 스레드 2는 Socket_Pool_B를 획득했다. 마지막 로그는 다음과 같다.

```text
2026-09-16 21:01:59,868 [INFO] [AgentWorker][Worker-Thread-1] WAITING for [Socket_Pool_B]... (Status: BLOCKED)
2026-09-16 21:01:59,869 [INFO] [AgentWorker][Worker-Thread-2] WAITING for [Shared_Memory_A]... (Status: BLOCKED)
```

21:02:25의 `ps -L`에서는 메인 스레드 2323과 작업 스레드 2448, 2449가 모두 `futex_wait_queue`에서 대기하고 있었다. 작업 프로세스 RSS는 17,792 KiB로 유지되었다. 단순히 프로세스가 종료된 상황과 구별된다.

마지막 `ps` 표본인 21:02:55까지 같은 PID와 대기 상태가 남았다. 마지막 작업 로그 이후 약 55초 동안 진행 기록이 없었다. 이는 유한한 관찰 기간의 정체 증거다. 무기한 대기라는 판단은 관찰 시간 자체와 함께, 서로 상대가 가진 잠금의 해제를 기다리는 순환 관계에 근거한다.

## 3. Root Cause Analysis (원인 분석)

로그가 보여 주는 대기 관계는 `스레드 1 → B → 스레드 2 → A → 스레드 1`이다. 두 스레드가 자원을 획득하는 순서가 반대라서 순환 대기가 형성되었다고 판단한다.

| 교착상태 조건 | 이 실험의 근거 |
| --- | --- |
| 상호 배제 | 한 스레드가 획득한 자원을 다른 스레드가 기다린다. |
| 점유 대기 | 각 스레드가 첫 자원을 가진 채 두 번째 자원을 요청한다. |
| 비선점 | 관찰 기간 동안 다른 스레드의 잠금을 강제로 회수하거나 대기를 해제한 기록이 없다. |
| 순환 대기 | 스레드 1은 스레드 2의 B를, 스레드 2는 스레드 1의 A를 기다린다. |

`futex_wait_queue`만으로 특정 잠금 객체나 교착상태를 확정할 수는 없다. 자원 이름과 획득 순서는 애플리케이션 로그에서, 대기 지속은 OS 관측에서 확인했다. 소스 코드 내부 잠금 구현은 조사하지 않았다.

## 4. Workaround & Verification (조치 및 검증)

MEMORY_LIMIT=512와 CPU_MAX_OCCUPY=40을 유지하고 MULTI_THREAD_ENABLE만 false로 바꾸었다.

- Before: 두 작업 스레드가 BLOCKED 상태에 들어가 로그와 자원 사용량 변화가 멈췄다.
- After: [재실행 로그](../evidence/deadlock-after/application.log)에 MemoryWorker와 CpuWorker의 진행 기록이 이어졌다. [프로세스 관측](../evidence/deadlock-after/process-snapshots.txt), [종료 기록](../evidence/deadlock-after/result.txt)에서 관찰 범위와 종료 주체를 확인할 수 있다.

멀티스레드 비활성화는 이번 재현 경로를 회피하는 임시 조치다. 근본 개선안은 모든 작업에서 잠금을 A→B 순서로 획득하도록 통일하고, 대기 시간 제한과 실패 시 잠금 해제 경로를 마련하는 것이다. 개선안은 제공 바이너리에 적용하거나 검증한 변경 사항이 아니다.

| 항목 | Before: true | After: false |
| --- | --- | --- |
| 작업 PID | 2323 | 3490 |
| 관측 RSS | 17,792 KiB 유지 | 17,792 → 최대 529,920 → 마지막 17,944 KiB |
| top 1초 구간 CPU 최댓값 | 0.0% | 9.0% (스레드 합계) |
| 작업 로그 | 21:01:59.869 이후 정체 | 메모리 증가·정리와 CPU 부하 조절 로그 지속 |
| 전체 실행 시간 | 약 67초 | 약 67초 |
| 종료 주체 | 관찰 종료 후 실험 스크립트 | 관찰 종료 후 실험 스크립트 |

최대 관찰 시간은 65초였고 종료 처리 시간까지 포함한 결과가 약 67초다. false에서도 정상 작업용 스레드가 관측되므로, 이 옵션이 프로세스의 모든 스레드를 없앤다고 해석하지 않는다. 이번 실험은 해당 교착 재현 경로의 회피를 확인했다.

잠금이 획득된 상태에서 후속 acquire가 해제까지 대기하는 원리는 [Python Lock 문서](https://docs.python.org/3/library/threading.html#lock-objects)를 참고했다.
