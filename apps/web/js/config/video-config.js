(function (root) {
  const namespace = root.FitnessCoach = root.FitnessCoach || {};
  const MEASUREMENT_VIDEO_GUIDES = {
    sit_and_reach: { title: "앉아 윗몸 앞으로 굽히기", youtubeId: "ydKH9ybDUZ4", sourceUrl: "https://youtu.be/ydKH9ybDUZ4?si=NKT_LEDspm6YgiOI" },
    cross_situp: { title: "교차 윗몸일으키기", youtubeId: "j5sktGOVq1c", sourceUrl: "https://youtu.be/j5sktGOVq1c?si=tUW5C_eqJ8xMZUty" },
    standing_long_jump: { title: "제자리멀리뛰기", youtubeId: "lb3PMPb-ugY", sourceUrl: "https://youtu.be/lb3PMPb-ugY?si=uDEISAFK7Y64w4R2" },
    agility_shuttle: { title: "10m 4회 왕복달리기", youtubeId: "DmXC2eJomjM", sourceUrl: "https://youtu.be/DmXC2eJomjM?si=vhKHwkdKC4CTvUy9" },
    chair_stand: { title: "의자에 앉았다 일어서기", youtubeId: "CZWDbfpoYF4", sourceUrl: "https://youtu.be/CZWDbfpoYF4?si=jM2k6bejcuBRFaoa" },
    two_min_step: { title: "2분 제자리걷기", youtubeId: "aYdPb99PcOw", sourceUrl: "https://youtu.be/aYdPb99PcOw?si=uAtkVlDn54uAkf6d" },
    senior_two_min_step: { title: "어르신 2분 제자리걷기", youtubeId: "lkG5wTv5IEg", sourceUrl: "https://youtu.be/lkG5wTv5IEg" },
    chair_sit_and_reach_3m: { title: "의자에 앉아 3m 표적 돌아오기", youtubeId: "xh_LPFeXJyw", sourceUrl: "https://youtu.be/xh_LPFeXJyw?si=C_4Wq6ehRbnxTU9_" },
  };
  const VIDEO_CATEGORY_BY_LABEL = { 유연성:"flexibility", 순발력:"power", 근지구력:"endurance", 민첩성:"agility", 악력:"grip", 심폐지구력:"cardio" };
  namespace.videoConfig = Object.freeze({ MEASUREMENT_VIDEO_GUIDES, VIDEO_CATEGORY_BY_LABEL });
})(window);
