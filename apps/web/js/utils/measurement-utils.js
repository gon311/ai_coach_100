(function (root) {
  const namespace = root.FitnessCoach = root.FitnessCoach || {};
  const config = namespace.measurementConfig;
  if (!config) throw new Error('measurement-config.js must load before measurement-utils.js');

  function isMeasurementValueValid(item, value) {
    if (value === undefined || value === null || value === '') return false;
    const number = Number(value);
    const rule = config.MEASUREMENT_RULES[item.code];
    return Number.isFinite(number) && number >= (rule?.min ?? 0);
  }

  function measurementItemsFor(ageGroup, route, gripOwned) {
    const codes = [...((route === 'CENTER' ? config.CENTER_BATTERY_CODES : config.HOME_BATTERY_CODES)[ageGroup] || [])];
    if (gripOwned === true) codes.push('grip_strength');
    const guides = [...config.ADULT_ITEMS, ...config.SENIOR_ITEMS, config.AGILITY_ITEM, config.CARDIO_ITEM, config.GRIP_ITEM];
    return codes.map(code => guides.find(item => item.code === code)).filter(Boolean);
  }

  function buildPercentileMeasurements(radarConfig, values, weight, gripOwned) {
    const measurements = {};
    radarConfig.forEach(axis => {
      if (axis.percentileEligible === false) return;
      const input = values[axis.valueCode];
      if (input === undefined || input === null || input === '' || !Number.isFinite(Number(input))) return;
      if (axis.code === 'GRIP_RELATIVE') {
        const bodyWeight = Number(weight);
        if (gripOwned === true && bodyWeight > 0) measurements[axis.code] = Number(input) / bodyWeight * 100;
        return;
      }
      measurements[axis.code] = Number(input);
    });
    return measurements;
  }

  namespace.measurementUtils = Object.freeze({ isMeasurementValueValid, measurementItemsFor, buildPercentileMeasurements });
})(window);
