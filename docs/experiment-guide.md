# 실험 진행과 명령어 해설

## 1. Linux 실행 조건 확인

Windows PowerShell에서 `wsl -d Ubuntu-24.04`로 Ubuntu에 들어간다. 프로젝트 폴더에서 다음을 확인한다.

```bash
id
uname -m
free -m
ss -ltn 'sport = :15034'
```

`id`는 일반 사용자 여부, `uname -m`은 CPU 아키텍처, `free -m`은 가용 메모리를 확인한다. `ss` 결과에 수신 소켓이 나타나면 다른 프로세스가 포트를 사용 중이므로 먼저 원인을 확인한다.

## 2. 변수를 하나씩 바꾸어 비교

```bash
bash scripts/run-case.sh my-oom-before 50 100 false 90
bash scripts/run-case.sh my-oom-after 100 100 false 90
bash scripts/run-case.sh my-cpu-before 512 100 false 90
bash scripts/run-case.sh my-cpu-after 512 40 false 65
bash scripts/run-case.sh my-deadlock-before 512 40 true 65
bash scripts/run-case.sh my-deadlock-after 512 40 false 65
```

인자는 실험 이름, 메모리 제한(MB), CPU 설정(%), 멀티스레드 여부, 최대 관찰 시간(초) 순서다. 기존 증거 폴더가 있으면 덮어쓰기를 거부한다. 재실험에는 새 이름을 쓴다.

메모리 실험은 MEMORY_LIMIT만, CPU 실험은 CPU_MAX_OCCUPY만, 교착상태 실험은 MULTI_THREAD_ENABLE만 변경한다. 관찰 시간은 무한 대기를 막는 실험 종료 기준이며 과제의 정상 종료 조건이 아니다.

## 3. 측정 대상 구분

제공 실행 파일은 실행용 부모 프로세스와 작업용 자식 프로세스를 만든다. 부모 PID만 관측하면 메모리가 거의 늘지 않아 잘못된 결론을 내릴 수 있다. `pid.txt`와 `workload-pid.txt`를 구분한다.

- `monitor.sh`: 부모와 자식의 RSS, 상태, 실행 이후 평균 CPU, 스레드 수, 구간 CPU를 1초 간격으로 기록한다. 경보 조건은 [관제 정책](monitoring-policy.md)을 따른다.
- `/proc/<pid>/task/<tid>/syscall`: 스레드가 어떤 시스템 콜에서, 어떤 futex 주소를 기다리는지 기록한다. `ptrace_scope=1`이라 앱을 띄운 `run-case.sh`가 직접 읽는다.
- `ps -L`: 작업 프로세스의 스레드별 상태와 커널 대기 위치(wchan)를 확인한다.
- `top -b -H -d 1`: 스레드별 CPU 표본을 파일로 저장한다. 첫 화면은 이후 1초 구간 표본과 의미가 달라 요약에서 제외한다.
- 짧은 CPU 급상승은 `TOP_INTERVAL_SECONDS=0.1 bash scripts/run-case.sh my-cpu-burst 512 100 false 90`으로 추가 관측할 수 있다. 다른 간격의 최댓값을 동일한 지표처럼 직접 비교하지 않는다.
- `application.log`: 프로그램이 직접 출력한 진단 메시지다. OS 관측값과 다른 경우 둘을 구분한다.
- `result.txt`: 종료 코드와 전체 실행 시간을 기록한다. STOPPED_BY_HARNESS=true이면 실험 스크립트가 관찰 시간을 채운 뒤 종료한 것이다.

RSS는 RAM에 상주하는 메모리를 뜻한다. 프로그램의 Current Heap 수치와 RSS는 측정 범위가 달라 일치하지 않을 수 있다. 또한 1초 표본 사이에 할당 후 종료하면 마지막 할당을 포착하지 못할 수 있다. [Linux 커널 문서](https://docs.kernel.org/filesystems/proc.html)

잠금이 이미 획득된 상태에서 다른 스레드가 같은 잠금을 요청하면 해제될 때까지 기다릴 수 있다. 두 스레드가 서로의 잠금을 기다리는 상황은 로그의 자원 획득 순서와 대기 상태를 함께 확인해야 한다. [Python Lock 문서](https://docs.python.org/3/library/threading.html#lock-objects)

## 4. 분석 결과 재계산

```bash
python3 scripts/summarize.py
```

원본 TSV, top 출력, 실행 로그로부터 `evidence/summary.json`을 만든다. 정상 상태가 관찰 시간 동안 유지되었다고 해서 무기한 정상 동작이 증명되는 것은 아니다.

## 5. 강제 종료 직전 콘솔 문구 확인

파일로 표준 출력을 직접 보낼 때 강제 종료 직전 문구가 버퍼에 남아 유실될 수 있다. 이 경우 `bash scripts/verify-console.sh`로 가상 터미널에서 같은 설정을 추가 실행한다. 실행 조건과 테스트 키는 앞선 실험 준비가 완료되어 있어야 한다. 기존 `evidence/console-confirmation`이 있으면 덮어쓰지 않는다.

이 추가 실험의 로그는 초기 측정과 PID·시각이 다르다. 원래 측정의 시간·RSS와 합치지 않는다. 가상 터미널은 출력 수집 방식이며, 바이너리 내부를 조사하는 도구로 사용하지 않는다.
