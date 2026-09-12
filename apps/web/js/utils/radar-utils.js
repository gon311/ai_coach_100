(function (root) {
  const namespace = root.FitnessCoach = root.FitnessCoach || {};

  function normalizeRadarValue(value, min, max, lowerBetter = false) {
    const number = Number(value);
    if (!Number.isFinite(number) || !Number.isFinite(min) || !Number.isFinite(max) || max <= min) return null;
    const ratio = lowerBetter ? (max - number) / (max - min) : (number - min) / (max - min);
    return Math.min(100, Math.max(0, ratio * 100));
  }

  function measuredRadarRuns(values) {
    if (!values.length || values.every(value => Number.isFinite(value))) return [];
    const measured = values.map(value => Number.isFinite(value));
    const firstGap = measured.findIndex(value => !value);
    const runs = [];
    let current = [];
    for (let offset = 1; offset <= values.length; offset += 1) {
      const index = (firstGap + offset) % values.length;
      if (measured[index]) current.push(index);
      else {
        if (current.length >= 2) runs.push(current);
        current = [];
      }
    }
    return runs;
  }

  function radarPoints(values, center = 150, radius = 94) {
    const count = values.length;
    return values.map((value,index) => {
      const angle = -Math.PI/2 + index * 2 * Math.PI / count;
      const r = radius * Math.max(0, Math.min(100, Number(value) || 0)) / 100;
      return `${(center + Math.cos(angle) * r).toFixed(1)},${(center + Math.sin(angle) * r).toFixed(1)}`;
    }).join(' ');
  }

  function radarIndexedPoints(values, indices, center = 150, radius = 94) {
    const count = values.length;
    return indices.map(index => {
      const angle = -Math.PI/2 + index * 2 * Math.PI / count;
      const r = radius * Math.max(0, Math.min(100, Number(values[index]) || 0)) / 100;
      return `${(center + Math.cos(angle) * r).toFixed(1)},${(center + Math.sin(angle) * r).toFixed(1)}`;
    }).join(' ');
  }

  function radarDotCoordinates(values, center = 150, radius = 94) {
    const count = values.length;
    return values.map((value,index) => {
      if (!Number.isFinite(value)) return null;
      const angle = -Math.PI/2 + index * 2 * Math.PI / count;
      const r = radius * value / 100;
      return { x: center + Math.cos(angle) * r, y: center + Math.sin(angle) * r, index };
    }).filter(Boolean);
  }

  namespace.radarUtils = Object.freeze({ normalizeRadarValue, measuredRadarRuns, radarPoints, radarIndexedPoints, radarDotCoordinates });
})(window);
