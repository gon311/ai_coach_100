(function (root) {
  const namespace = root.FitnessCoach = root.FitnessCoach || {};
  const services = namespace.services = namespace.services || {};

  services.loadReportSummary = async function loadReportSummary(payload, fetchImpl = root.fetch.bind(root)) {
    try {
      const response = await fetchImpl('/api/report-summary', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error('report-api-unavailable');
      return await response.json();
    } catch (error) {
      throw new Error('report-api-unavailable');
    }
  };
})(window);
