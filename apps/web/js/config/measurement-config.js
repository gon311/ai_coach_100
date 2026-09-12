(function (root) {
  const namespace = root.FitnessCoach = root.FitnessCoach || {};

  const ADULT_ITEMS = [
    { code: "cross_situp", name: "교차윗몸일으키기", unit: "회", why: "복부·코어 근지구력을 확인해요.", prep: "매트 또는 바닥에 깔 담요", space: "누울 수 있는 1.5m x 1m 공간", method: "무릎을 세우고 누운 뒤, 팔꿈치가 반대쪽 무릎에 닿도록 상체를 교차로 들어올려요.", caution: "목에 힘을 주지 말고 반동을 사용하지 마세요." },
    { code: "sit_and_reach", name: "앉아윗몸앞으로굽히기", unit: "cm", why: "허리·하체 뒤쪽 유연성을 확인해요.", prep: "줄자 또는 유연성 측정자, 벽", space: "다리를 뻗고 앉을 수 있는 공간", method: "다리를 펴고 앉아 상체를 천천히 앞으로 굽혀 손끝이 닿는 위치를 측정해요.", caution: "무릎을 굽히지 말고, 통증이 있으면 즉시 중단하세요.", note: "영점 기준: 발바닥 앞면을 0cm으로 두고, 발끝을 넘으면 +, 못 미치면 −로 기록해요." },
    { code: "standing_long_jump", name: "제자리멀리뛰기", unit: "cm", why: "하체 순발력을 확인해요.", prep: "줄자, 미끄럽지 않은 바닥", space: "착지 거리까지 2m 이상의 평평한 공간", method: "제자리에서 두 발로 최대한 멀리 뛰어 착지 지점까지의 거리를 측정해요.", caution: "착지 시 무릎에 힘을 주고 균형을 잃지 않도록 주의하세요." },
  ];
  const SENIOR_ITEMS = [
    { code: "chair_stand", name: "의자에 앉았다 일어서기", unit: "회", why: "하지 근기능을 확인해요.", prep: "등받이 없는 안정된 의자", space: "의자 앞뒤로 여유 공간", method: "팔짱을 낀 채 정해진 시간 동안 앉았다 일어서기를 반복해요.", caution: "의자가 흔들리지 않는지 먼저 확인하세요.", note: "의자 좌면 높이: 무릎이 90도 정도로 굽혀지는 높이로 통일해야 결과가 일관돼요." },
    { code: "sit_and_reach", name: "앉아윗몸앞으로굽히기", unit: "cm", why: "허리·하체 뒤쪽 유연성을 확인해요.", prep: "줄자 또는 유연성 측정자", space: "다리를 뻗고 앉을 수 있는 공간", method: "다리를 펴고 앉아 상체를 천천히 앞으로 굽혀 손끝이 닿는 위치를 측정해요.", caution: "무릎을 굽히지 말고, 통증이 있으면 즉시 중단하세요.", note: "영점 기준: 발바닥 앞면을 0cm으로 두고, 발끝을 넘으면 +, 못 미치면 −로 기록해요." },
    { code: "two_min_step", name: "2분 제자리걷기", unit: "회", why: "심폐 지구력 관련 기능을 확인해요.", prep: "무릎 높이 표시 테이프", space: "제자리 걷기가 가능한 공간", method: "2분 동안 무릎을 정해진 높이까지 올리며 제자리 걷기를 반복해요.", caution: "어지러움이 느껴지면 즉시 중단하세요." },
    { code: "chair_sit_and_reach_3m", name: "의자에 앉아 3m 표적 돌아오기", unit: "초", why: "민첩성과 균형 관련 기능을 확인해요.", prep: "의자, 표적(콘 등), 줄자", space: "왕복 3m 이상의 통로", method: "의자에서 일어나 3m 앞 표적을 돌아 다시 앉기까지의 시간을 측정해요.", caution: "회전 시 미끄러지지 않도록 주의하세요." },
  ];
  const GRIP_ITEM = { code: "grip_strength", name: "악력", unit: "kg", why: "상지 근력을 확인해요.", prep: "악력계", space: "서서 측정할 수 있는 공간", method: "악력계를 잡고 최대 힘으로 2회 측정해 더 큰 값을 기록해요.", caution: "손목을 비틀지 말고 팔을 몸에서 떨어뜨려 측정하세요." };
  const AGILITY_ITEM = { code: "agility_shuttle", name: "10m 4회 왕복달리기", unit: "초", why: "빠르게 방향을 바꾸는 민첩성을 확인해요.", prep: "초시계, 출발선과 10m 지점 표시물 2개", space: "미끄럽지 않고 장애물이 없는 직선 10m 이상", method: "출발선에서 10m 표시까지 달려 선을 넘고 돌아오는 동작을 2번 반복해 총 40m 완료 시간을 기록해요.", caution: "실내 좁은 공간에서는 실시하지 마세요. 급정지·회전이 불안하거나 관절 통증이 있으면 센터 측정을 이용하세요." };
  const CARDIO_ITEM = { code: "cardio_endurance", name: "심폐지구력(센터 측정)", unit: "회", why: "센터 측정값으로 심폐지구력을 확인해요." };
  const MEASUREMENT_RULES = {
    sit_and_reach: { min: -30 }, cross_situp: { min: 0 }, standing_long_jump: { min: 0 }, agility_shuttle: { min: 0 },
    chair_stand: { min: 0 }, two_min_step: { min: 0 }, chair_sit_and_reach_3m: { min: 0, percentileEligible: false },
    grip_strength: { min: 0 }, cardio_endurance: { min: 0 },
  };
  const HOME_BATTERY_CODES = {
    adult: ['sit_and_reach','cross_situp','standing_long_jump','agility_shuttle'],
    senior: ['chair_stand','sit_and_reach','two_min_step','chair_sit_and_reach_3m'],
  };
  const CENTER_BATTERY_CODES = {
    adult: ['sit_and_reach','cross_situp','standing_long_jump','agility_shuttle','cardio_endurance'],
    senior: ['sit_and_reach','standing_long_jump','chair_stand','chair_sit_and_reach_3m','two_min_step'],
  };

  namespace.measurementConfig = Object.freeze({ ADULT_ITEMS, SENIOR_ITEMS, GRIP_ITEM, AGILITY_ITEM, CARDIO_ITEM, MEASUREMENT_RULES, HOME_BATTERY_CODES, CENTER_BATTERY_CODES });
})(window);
