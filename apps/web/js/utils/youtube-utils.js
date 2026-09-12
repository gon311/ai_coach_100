(function (root) {
  const namespace = root.FitnessCoach = root.FitnessCoach || {};

  function extractYouTubeId(value) {
    if (typeof value !== 'string' || !value.trim()) return null;
    const trimmed = value.trim();
    if (/^[A-Za-z0-9_-]{11}$/.test(trimmed)) return trimmed;
    try {
      const url = new URL(trimmed);
      const host = url.hostname.toLowerCase().replace(/^www\./,'');
      let candidate = null;
      if (host === 'youtu.be') candidate = url.pathname.split('/').filter(Boolean)[0];
      else if (host === 'youtube.com' || host === 'm.youtube.com' || host === 'youtube-nocookie.com') {
        if (url.pathname === '/watch') candidate = url.searchParams.get('v');
        else {
          const parts = url.pathname.split('/').filter(Boolean);
          if (['shorts','embed'].includes(parts[0])) candidate = parts[1];
        }
      }
      return /^[A-Za-z0-9_-]{11}$/.test(candidate || '') ? candidate : null;
    } catch (error) {
      return null;
    }
  }

  namespace.youtubeUtils = Object.freeze({ extractYouTubeId });
})(window);
