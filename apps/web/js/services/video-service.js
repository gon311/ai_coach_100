(function (root) {
  const namespace = root.FitnessCoach = root.FitnessCoach || {};
  const services = namespace.services = namespace.services || {};

  services.loadWorkoutVideos = async function loadWorkoutVideos(category, fetchImpl = root.fetch.bind(root)) {
    try {
      const response = await fetchImpl(`/api/top-videos/${category}`);
      if (!response.ok) throw new Error('video-api-unavailable');
      return await response.json();
    } catch (error) {
      throw new Error('video-api-unavailable');
    }
  };
})(window);
