# 홈 체력 측정 유저 플로우 (User Flow)

> [!TIP]
> 아래 다이어그램은 **Mermaid** 포맷으로 작성되었습니다. 
> Draw.io (diagrams.net)에서 **[Arrange] -> [Insert] -> [Advanced] -> [Mermaid]** 메뉴를 통해 아래 코드 블록의 텍스트를 그대로 복사하여 붙여넣으면 Draw.io 다이어그램으로 즉시 변환하여 편집하실 수 있습니다.

```mermaid
flowchart TD
    %% 스타일 정의
    classDef startEnd fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef process fill:#e1f5fe,stroke:#039be5,stroke-width:2px;
    classDef decision fill:#fff3e0,stroke:#ff9800,stroke-width:2px;
    classDef test fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px;
    classDef result fill:#e8f5e9,stroke:#43a047,stroke-width:2px;

    %% 노드 정의
    Start([앱 실행]):::startEnd
    Login[로그인 / 소셜 회원가입]:::process
    Home[메인 홈 화면\n대시보드]:::process
    
    RecordChoice{체력 데이터 추가\n방식 선택}:::decision
    
    CenterData[국민체력100 센터\n측정 기록 연동/직접 입력]:::process
    
    QnA[사전 건강 문진표 작성\n안전 체크]:::process
    Profile[신체 정보 입력\n성별, 나이, 키, 몸무게]:::process
    
    subgraph TestPhase [홈 체력 측정 진행 (층간소음 방지 기본 적용)]
        direction TB
        Test1[1. 유연성 측정\n앉아 윗몸 굽히기]:::test
        Test2[2. 근지구력 측정\n플랭크 버티기]:::test
        Test3[3. 하체 근력 측정\n월 시트 (벽 기대기)]:::test
        Test4[4. 심폐지구력 측정\n3분 스텝 테스트]:::test
    end
    
    ResultCalc((데이터 수집 및\n결과 분석)):::process
    Report[측정 결과 리포트\n종합 등급 및 오각형 그래프]:::result
    Recommend[맞춤형 운동 플랜 추천\n약점 보완 루틴]:::result
    
    %% 흐름 연결
    Start --> Login
    Login --> Home
    Home --> RecordChoice
    
    RecordChoice -->|센터 기록 불러오기| CenterData
    RecordChoice -->|집에서 셀프 측정| QnA
    
    CenterData --> ResultCalc
    
    QnA --> Profile
    Profile --> Test1
    
    Test1 -->|기록 입력| Test2
    Test2 -->|기록 입력| Test3
    Test3 -->|기록 입력| Test4
    Test4 -->|기록 입력| ResultCalc
    
    ResultCalc --> Report
    Report --> Recommend
    Recommend -->|확인 완료| Home
```
