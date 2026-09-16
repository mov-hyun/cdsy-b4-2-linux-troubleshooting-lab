# B4-2 과제 요구사항

과제: 컴퓨터가 갑자기 느려지거나 멈췄을 때 원인 찾아 고치기

## 필수 제출물

GitHub Issue 형태의 기술 보고서 3건을 PDF 또는 GitHub Repository 링크로 제출한다.

| 사례 | 필수 증거 | 변경할 환경변수 |
| --- | --- | --- |
| 메모리 누수 / OOM | 메모리 증가 관측, MemoryGuard 종료 로그, 최소 2회 실행 비교 | MEMORY_LIMIT |
| CPU 과점유 | CPU 급상승 관측, Watchdog 종료 로그, 종료 여부 또는 생존 시간 비교 | CPU_MAX_OCCUPY |
| Deadlock | PID 존재, CPU/메모리 정체, 마지막 WAITING/BLOCKED 로그, 스레드/락 대기 추론, 회피 비교 | MULTI_THREAD_ENABLE |

각 보고서는 Description, Evidence & Logs, Root Cause Analysis, Workaround & Verification을 포함한다.

## 실행 조건

- Linux, 일반 사용자, 포트 15034 사용 가능.
- AGENT_HOME과 upload_files, api_keys, 쓰기 가능한 로그 디렉터리.
- api_keys/secret.key 내용은 과제에서 지정한 테스트 문자열 agent_api_key_test.
- MEMORY_LIMIT: 50~512 MB, CPU_MAX_OCCUPY: 10~100, MULTI_THREAD_ENABLE: true/false.

## 제약 및 해석 기준

- 바이너리 디컴파일 및 리버스 엔지니어링 금지.
- Linux 표준 도구와 실행 로그로 분석한다.
- 제공 예시의 시간·수치·결론을 실측 결과로 사용하지 않는다.
- 애플리케이션 자체 MemoryGuard 종료와 Linux 커널 OOM killer를 구분한다.
- ps의 %CPU는 실행 이후 평균이다. 순간 부하는 top의 연속 표본 또는 별도 구간 측정으로 확인한다.
- 관찰 종료를 위해 실험 스크립트가 중단한 경우 애플리케이션 자체 종료와 구분한다.
- 스케줄링 알고리즘 추론은 선택 과제이며 로그만으로 확정할 수 없는 OS 정책은 단정하지 않는다.

## 제공 자료 확인

제공 폴더에는 agent-leak-app-x86과 agent-leak-app-arm64가 있다. monitor.sh는 없어 관측 스크립트를 별도로 작성한다.
