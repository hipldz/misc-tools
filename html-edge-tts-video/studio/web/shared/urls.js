(() => {
  const basePath = document.querySelector('meta[name="app-base-path"]')?.content || '';
  window.appPath = path => {
    if (basePath && (path === basePath || path.startsWith(`${basePath}/`))) {
      return path.slice(basePath.length) || '/';
    }
    return path;
  };
  // Call with internal URLs only. API responses already contain the public prefix.
  window.appUrl = path => {
    if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) return path;
    return `${basePath}${path}`;
  };
})();
