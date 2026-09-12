(function (root) {
  const namespace = root.FitnessCoach = root.FitnessCoach || {};
  const services = namespace.services = namespace.services || {};

  services.loadPercentiles = async function loadPercentiles(payload, fetchImpl = root.fetch.bind(root)) {
    try {
      const response = await fetchImpl('/api/center-percentiles', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error('percentile-api-unavailable');
      return await response.json();
    } catch (error) {
      throw new Error('percentile-api-unavailable');
    }
  };
})(window);
