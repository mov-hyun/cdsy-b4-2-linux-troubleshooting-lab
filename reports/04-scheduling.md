# [Analysis] 로그 패턴 분석을 통한 스케줄링 알고리즘 추론

## 1. 로그 관찰 개요

`agent-leak-app`은 모든 설정이 정상 범위일 때 `[Healthy System Monitoring]` 시나리오를 선택하고, 애플리케이션 내부 `[Scheduler]`가 `Thread-A`, `Thread-B`, `Thread-C` 세 작업을 실행한다. 이 시나리오는 `MEMORY_LIMIT=512MB, CPU_MAX_OCCUPY=40%, MULTI_THREAD_ENABLE=False` 설정의 두 실행에서 기록되었다.

- [cpu-after 실행 로그](../evidence/cpu-after/application.log) (2026-09-16 21:00:45)
- [deadlock-after 실행 로그](../evidence/deadlock-after/application.log) (2026-09-16 21:03:00)

재현: `bash scripts/run-case.sh my-healthy 512 40 false 30` 실행 후 `application.log`에서 `[Scheduler]`와 `[Thread-` 줄을 확인한다.

다른 설정의 실행에서는 장애 시나리오가 선택되어 Scheduler 로그가 나오지 않았다. 분석 대상은 OS 커널 스케줄러가 아니라 로그에 드러난 애플리케이션 작업 스케줄러의 처리 순서다.

## 2. 증거 자료

[ Application Log Snapshot — cpu-after ]

```
2026-09-16 21:00:45,295 [INFO] [Scheduler] Registered Tasks: ['Thread-A', 'Thread-B', 'Thread-C']
2026-09-16 21:00:45,296 [INFO] [Scheduler] Starting task execution...
2026-09-16 21:00:45,296 [INFO] [Thread-A] Task Started. Calculating... (20%)
2026-09-16 21:00:45,347 [INFO] [Thread-A] Calculating... (40%)
2026-09-16 21:00:45,400 [INFO] [Thread-A] Calculating... (60%)
2026-09-16 21:00:45,453 [INFO] [Thread-A] Calculating... (80%)
2026-09-16 21:00:45,505 [INFO] [Thread-A] Task Completed. (100%)
2026-09-16 21:00:45,557 [INFO] [Thread-B] Task Started. Calculating... (20%)   <-- A 완료 후에야 B 시작
2026-09-16 21:00:45,609 [INFO] [Thread-B] Calculating... (40%)
2026-09-16 21:00:45,661 [INFO] [Thread-B] Calculating... (60%)
2026-09-16 21:00:45,713 [INFO] [Thread-B] Calculating... (80%)
2026-09-16 21:00:45,765 [INFO] [Thread-B] Task Completed. (100%)
2026-09-16 21:00:45,830 [INFO] [Thread-C] Task Started. Calculating... (20%)   <-- B 완료 후에야 C 시작
2026-09-16 21:00:45,882 [INFO] [Thread-C] Calculating... (40%)
2026-09-16 21:00:45,933 [INFO] [Thread-C] Calculating... (60%)
2026-09-16 21:00:45,985 [INFO] [Thread-C] Calculating... (80%)
2026-09-16 21:00:46,037 [INFO] [Thread-C] Task Completed. (100%)
2026-09-16 21:00:46,088 [INFO] [Scheduler] All tasks completed.
```

타임스탬프에서 계산한 값 (기준: `Starting task execution` 시각)

| 실행 | 작업 | 시작 | 완료 | 연속 실행 시간 | 대기 시간 | 이전 작업 완료 → 시작 간격 |
| --- | --- | --- | --- | --- | --- | --- |
| cpu-after | Thread-A | 45.296 | 45.505 | 209ms | 0ms | - |
| cpu-after | Thread-B | 45.557 | 45.765 | 208ms | 261ms | 52ms |
| cpu-after | Thread-C | 45.830 | 46.037 | 207ms | 534ms | 65ms |
| deadlock-after | Thread-A | 00.370 | 00.578 | 208ms | 1ms | - |
| deadlock-after | Thread-B | 00.630 | 00.839 | 209ms | 261ms | 52ms |
| deadlock-after | Thread-C | 00.891 | 01.101 | 210ms | 522ms | 52ms |

진행률 로그는 약 52ms 간격으로 20%씩 증가한다. 두 실행 모두 같은 순서, 같은 작업 길이, 같은 교체 지점을 보였다.

## 3. 패턴 분석 및 결론

- **Round-Robin 아님:** Round-Robin이라면 시간 할당량이 끝날 때 다른 작업으로 넘어가 `A 20% → B 20% → C 20% → A 40%`처럼 진행률이 섞여야 한다. 실제로는 각 작업이 20%부터 100%까지 약 208ms 동안 끊김 없이 진행했고, 작업 교체는 `Task Completed` 직후에만 일어났다. 선점이 한 번도 관측되지 않았다.
- **Priority 아님:** 실행 순서가 등록 순서 `['Thread-A', 'Thread-B', 'Thread-C']`와 정확히 일치한다. 로그에 우선순위 값이나 뒤늦게 끼어드는 작업이 없고, 두 실행에서 순서가 바뀌지도 않았다. 다만 세 작업의 우선순위가 우연히 등록 순서와 같을 가능성은 로그만으로 완전히 배제할 수 없다. 우선순위를 판별하려면 등록 순서가 다른 실행이 필요하다.
- **최종 결론:** 먼저 등록된 작업을 끝까지 처리한 뒤 다음 작업으로 넘어가는 **비선점 FCFS(First-Come, First-Served)** 로 추론된다. 대기 시간이 0 → 261ms → 522~534ms로 앞 작업 길이만큼 누적되는 것도 FCFS의 특징과 일치한다.

해석 범위: 이 결론은 애플리케이션이 작업을 내보내는 순서에 대한 것이다. `nice=10` 로그가 보여주듯 프로세스 자체는 Linux CFS 스케줄러 위에서 다른 프로세스와 CPU를 나눠 쓴다. 바이너리 내부는 분석하지 않았으므로 구현 방식은 단정하지 않는다.

## 4. 장단점 및 적합한 아키텍처

| 구분 | 내용 |
| --- | --- |
| 장점 | 구현이 단순하고 문맥 교환 비용이 거의 없다. 실행 순서를 예측할 수 있어 로그 추적과 재현이 쉽다. 작업마다 한 번에 끝까지 실행되므로 캐시 효율과 전체 처리량이 좋다. |
| 단점 | 앞에 긴 작업이 있으면 뒤의 짧은 작업이 모두 기다리는 호위 효과(Convoy Effect)가 생긴다. 이번 로그에서도 C는 자기 실행 시간(약 208ms)보다 대기 시간(522ms 이상)이 길었다. 응답 시간이 작업 순서에 크게 좌우되고, 한 작업이 멈추면 뒤 작업 전체가 멈춘다. |
| 적합 | 처리량이 중요하고 개별 응답 시간이 덜 중요한 **배치 서버**. 예: 야간 정산, 로그 집계, 순서 보장이 필요한 메시지 큐 소비자, 이번처럼 짧고 길이가 비슷한 점검 작업 묶음. |
| 부적합 | 여러 사용자에게 빠른 응답을 줘야 하는 **실시간 웹 서버**나 대화형 서비스. 긴 요청 하나가 다른 요청을 모두 지연시키므로 Round-Robin이나 CFS처럼 시간을 나눠 쓰는 방식, 또는 긴급 작업을 앞세우는 Priority 방식이 적합하다. |
