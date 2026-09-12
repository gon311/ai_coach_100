(function (root) {
  const namespace = root.FitnessCoach = root.FitnessCoach || {};
  const MOCK_WORKOUT_RECOMMENDATIONS = {
    base: [
      { badge: "워밍업", title: "가벼운 유산소 걷기 10분", tone: "primary", phase: "워밍업", durationMinutes: 10 },
      { badge: "기본 운동", title: "코어 안정화 플랭크 3세트", tone: "primary", phase: "기본 운동", durationMinutes: 6 },
    ],
    weakness: { badge: "보완 운동", titleSuffix: "보완 스트레칭", tone: "warn", phase: "보완 운동", durationMinutes: 7, opensVideo: true },
  };
  namespace.mockData = Object.freeze({ MOCK_WORKOUT_RECOMMENDATIONS });
})(window);
