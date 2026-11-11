(() => {
  let busy = false;
  let overlay;

  function loadingOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('dialog');
    overlay.className = 'app-loading';
    overlay.id = 'projectLoadingOverlay';
    overlay.setAttribute('aria-labelledby', 'projectLoadingTitle');
    overlay.setAttribute('aria-describedby', 'projectLoadingMessage');
    overlay.innerHTML = '<div class="app-loading-card" role="status" aria-live="polite">'
      + '<span class="app-loading-spinner" aria-hidden="true"></span>'
      + '<strong id="projectLoadingTitle"></strong>'
      + '<p id="projectLoadingMessage">正在读取项目与预览，请稍候。</p></div>';
    overlay.addEventListener('cancel', event => event.preventDefault());
    document.body.append(overlay);
    return overlay;
  }

  // A modal dialog also blocks iframe interaction and sits above other dialogs.
  // The synchronous lock closes the gap before the first asynchronous request.
  async function runProjectTransition(title, operation) {
    if (busy) return null;
    busy = true;
    const focused = document.activeElement;
    const roots = [...document.querySelectorAll('body > main')].map(node => ({
      node, inert: node.inert, busy: node.getAttribute('aria-busy'),
    }));
    try {
      const dialog = loadingOverlay();
      dialog.querySelector('strong').textContent = title;
      roots.forEach(({ node }) => {
        node.inert = true;
        node.setAttribute('aria-busy', 'true');
      });
      dialog.showModal();
      return await operation();
    } finally {
      overlay?.close();
      roots.forEach(({ node, inert, busy: previous }) => {
        node.inert = inert;
        if (previous === null) node.removeAttribute('aria-busy');
        else node.setAttribute('aria-busy', previous);
      });
      busy = false;
      if (focused?.isConnected) focused.focus({ preventScroll: true });
    }
  }

  async function waitForPreview(frame, timeout = 15000) {
    const expected = frame.src;
    const deadline = performance.now() + timeout;
    while (performance.now() < deadline) {
      if (frame.src !== expected) throw new Error('预览已切换，请重新选择项目。');
      try {
        const preview = frame.contentWindow;
        // The old document can still be ready after assigning a new iframe src.
        if (preview?.location.href === expected) {
          if (preview.compositionError) throw new Error(String(preview.compositionError));
          if (preview.compositionReady) return;
        }
      } catch (error) {
        if (error.name !== 'SecurityError') throw error;
      }
      await new Promise(resolve => window.setTimeout(resolve, 50));
    }
    throw new Error('项目已读取，但预览加载超时，请刷新预览或重新选择项目。');
  }

  document.addEventListener('keydown', event => {
    if (!busy || event.key === 'Tab') return;
    // Page-level save/playback shortcuts must not act on the previous project.
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);

  window.AppUI = { get busy() { return busy; }, runProjectTransition, waitForPreview };
})();
