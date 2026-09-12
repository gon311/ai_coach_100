(function (root) {
  const namespace = root.FitnessCoach = root.FitnessCoach || {};
  const RADAR_CONFIG = {
    adult: [
      {label:"유연성", code:"FLEX_SIT_REACH", valueCode:"sit_and_reach", unit:"cm", min:-30, max:40},
      {label:"순발력", code:"POWER_LONGJUMP", valueCode:"standing_long_jump", unit:"cm", min:0, max:300},
      {label:"근지구력", code:"MUSC_END_SITUP", valueCode:"cross_situp", unit:"회", min:0, max:100},
      {label:"민첩성", code:"AGILITY_10M_SHUTTLE", valueCode:"agility_shuttle", unit:"초", min:0, max:40, lowerBetter:true},
      {label:"악력", code:"GRIP_RELATIVE", valueCode:"grip_strength", unit:"%", min:0, max:100},
      {label:"심폐지구력", code:"CARDIO_ENDURANCE", valueCode:"cardio_endurance", unit:"회", min:0, max:150},
    ],
    senior: [
      {label:"유연성", code:"FLEX_SIT_REACH", valueCode:"sit_and_reach", unit:"cm", min:-30, max:40},
      {label:"순발력", code:"POWER_LONGJUMP", valueCode:"standing_long_jump", unit:"cm", min:0, max:300},
      {label:"근지구력", code:"MUSC_END_CHAIR_STAND", valueCode:"chair_stand", unit:"회", min:0, max:60},
      {label:"민첩성", code:"AGILITY_3M", valueCode:"chair_sit_and_reach_3m", unit:"초", min:0, max:20, lowerBetter:true, percentileEligible:false},
      {label:"악력", code:"GRIP_RELATIVE", valueCode:"grip_strength", unit:"%", min:0, max:100},
      {label:"심폐지구력", code:"CARDIO_2MINSTEP", valueCode:"two_min_step", unit:"회", min:0, max:150},
    ],
  };
  const BACKEND_PERCENTILE_RANGE_WIDTH = { chair_stand: 5 };
  namespace.radarConfig = Object.freeze({ RADAR_CONFIG, BACKEND_PERCENTILE_RANGE_WIDTH });
})(window);
