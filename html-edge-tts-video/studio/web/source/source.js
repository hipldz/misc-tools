const $ = selector => document.querySelector(selector);

const state = {
  project: null,
  projects: [],
  originalScenes: '',
  originalBody: '',
  sourceRevision: '',
  dirty: false,
  activeTab: 'scenes',
  pendingMediaPath: '',
  aspectRatio: '16:9',
  scenes: [],
  selectedSceneId: '',
  selectedNode: null,
};

const els = {
  engineStatus: $('#engineStatus'),
  engineDot: $('#engineDot'),
  sourceProjectName: $('#sourceProjectName'),
  dirtyBadge: $('#dirtyBadge'),
  projectSelect: $('#projectSelect'),
  validateButton: $('#validateButton'),
  saveButton: $('#saveButton'),
  scenesEditor: $('#scenesEditor'),
  bodyEditor: $('#bodyEditor'),
  editorFileName: $('#editorFileName'),
  editorStats: $('#editorStats'),
  saveImpact: $('#saveImpact'),
  reloadPreviewButton: $('#reloadPreviewButton'),
  addTextButton: $('#addTextButton'),
  addShapeButton: $('#addShapeButton'),
  shapeColorInput: $('#shapeColorInput'),
  previousSceneButton: $('#previousSceneButton'),
  nextSceneButton: $('#nextSceneButton'),
  sceneNavigator: $('#sceneNavigator'),
  previewWrap: $('#previewWrap'),
  previewViewport: $('#previewViewport'),
  previewFrame: $('#previewFrame'),
  selectedObjectLabel: $('#selectedObjectLabel'),
  objectX: $('#objectX'),
  objectY: $('#objectY'),
  objectWidth: $('#objectWidth'),
  objectHeight: $('#objectHeight'),
  objectMotion: $('#objectMotion'),
  applyObjectButton: $('#applyObjectButton'),
  deleteObjectButton: $('#deleteObjectButton'),
  uploadButton: $('#uploadButton'),
  mediaInput: $('#mediaInput'),
  dropZone: $('#dropZone'),
  missingCount: $('#missingCount'),
  missingList: $('#missingList'),
  mediaCount: $('#mediaCount'),
  mediaList: $('#mediaList'),
  notification: $('#notification'),
};

let notificationTimer = 0;

function renderIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

function notify(message, tone = '') {
  window.clearTimeout(notificationTimer);
  els.notification.textContent = message;
  els.notification.className = `notification show ${tone}`.trim();
  notificationTimer = window.setTimeout(() => {
    els.notification.className = 'notification';
  }, 3600);
}

function setStatus(message, error = false) {
  els.engineStatus.textContent = error ? '连接失败' : '运行正常';
  els.engineDot.classList.toggle('error', error);
  notify(message, error ? 'error' : '');
}

async function apiJson(path, options = {}) {
  const response = await fetch(window.appUrl(path), {
    ...options,
    signal: options.signal || AbortSignal.timeout(20000),
    headers: {
      ...(options.headers || {}),
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    },
    cache: 'no-store',
  });
  const raw = await response.text();
  const data = raw ? JSON.parse(raw) : {};
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

async function postJson(path, value) {
  return apiJson(path, { method: 'POST', body: JSON.stringify(value) });
}

function activeEditor() {
  return state.activeTab === 'body' ? els.bodyEditor : els.scenesEditor;
}

function setDirty(value = true) {
  state.dirty = Boolean(value);
  els.dirtyBadge.hidden = !state.dirty;
  updateEditorMeta();
}

function timelineSignature(text) {
  try {
    const scenes = JSON.parse(text);
    if (!Array.isArray(scenes)) return null;
    return scenes.map(scene => [scene?.id, scene?.narration]);
  } catch {
    return null;
  }
}

function parsedScenes(text = els.scenesEditor.value) {
  try {
    const value = JSON.parse(text);
    return Array.isArray(value) ? value.filter(scene => scene && typeof scene.id === 'string') : [];
  } catch {
    return [];
  }
}

function serializeBodyDocument(documentValue) {
  return `<!doctype html>\n${documentValue.documentElement.outerHTML}\n`;
}

function bodyDocument() {
  return new DOMParser().parseFromString(els.bodyEditor.value, 'text/html');
}

function sourceNodeById(documentValue, id) {
  return [...documentValue.querySelectorAll('[data-studio-id]')]
    .find(node => node.getAttribute('data-studio-id') === id) || null;
}

function updateEditorMeta() {
  const editor = activeEditor();
  els.editorFileName.textContent = state.activeTab === 'body' ? 'body.html' : 'scenes.json';
  els.editorStats.textContent = `${editor.value.length.toLocaleString()} 字符`;
  const before = JSON.stringify(timelineSignature(state.originalScenes));
  const after = JSON.stringify(timelineSignature(els.scenesEditor.value));
  const timelineChanged = before !== after;
  els.saveImpact.textContent = timelineChanged
    ? '场景 ID、顺序或旁白已变化：保存后将清除旧 TTS、时间轴与字幕。'
    : '仅视觉、分类或媒体变化：保存后会保留现有旁白、时间轴与字幕。';
  els.saveImpact.classList.toggle('warning', timelineChanged);
  const readOnly = state.project?.id === 'starter';
  els.saveButton.disabled = readOnly;
  els.uploadButton.disabled = readOnly;
  els.addTextButton.disabled = readOnly;
  els.addShapeButton.disabled = readOnly;
  els.shapeColorInput.disabled = readOnly;
}

function setEditorTab(tab) {
  state.activeTab = tab === 'body' ? 'body' : 'scenes';
  els.scenesEditor.hidden = state.activeTab !== 'scenes';
  els.bodyEditor.hidden = state.activeTab !== 'body';
  document.querySelectorAll('[data-editor-tab]').forEach(button => {
    button.classList.toggle('active', button.dataset.editorTab === state.activeTab);
  });
  updateEditorMeta();
  activeEditor().focus();
}

function fitPreview() {
  const width = els.previewWrap.clientWidth;
  const height = els.previewWrap.clientHeight;
  if (!width || !height) return;
  const portrait = state.aspectRatio === '9:16';
  const designWidth = portrait ? 720 : 1280;
  const designHeight = portrait ? 1280 : 720;
  const scale = Math.min((width - 14) / designWidth, (height - 14) / designHeight);
  els.previewViewport.style.setProperty('--preview-width', `${designWidth}px`);
  els.previewViewport.style.setProperty('--preview-height', `${designHeight}px`);
  els.previewViewport.style.setProperty('--preview-scale', String(scale));
}

function renderSceneNavigator() {
  els.sceneNavigator.innerHTML = state.scenes.map((scene, index) => `
    <button type="button" data-scene-id="${escapeHtml(scene.id)}" class="${scene.id === state.selectedSceneId ? 'active' : ''}">
      ${String(index + 1).padStart(2, '0')} · ${escapeHtml(scene.category || scene.id)}
    </button>`).join('');
  const index = state.scenes.findIndex(scene => scene.id === state.selectedSceneId);
  els.previousSceneButton.disabled = index <= 0;
  els.nextSceneButton.disabled = index < 0 || index >= state.scenes.length - 1;
}

function clearSelectedObject() {
  state.selectedNode?.classList.remove(
    'studio-editor-selected',
    'studio-editor-resize-hover',
    'studio-editor-resizing',
  );
  state.selectedNode = null;
  els.selectedObjectLabel.textContent = '未选择对象';
  [els.objectX, els.objectY, els.objectWidth, els.objectHeight, els.objectMotion, els.applyObjectButton, els.deleteObjectButton]
    .forEach(element => { element.disabled = true; });
}

function updateObjectInspector(node = state.selectedNode) {
  if (!node) {
    clearSelectedObject();
    return;
  }
  const id = node.getAttribute('data-studio-id') || '未命名';
  const kind = node.getAttribute('data-studio-kind') || node.tagName.toLowerCase();
  if (kind === 'shape') {
    const color = node.style.backgroundColor || node.style.background;
    const match = color.match(
      /^#([0-9a-f]{6})$/i,
    ) || color.match(
      /^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/i,
    );
    if (match) {
      els.shapeColorInput.value = match.length === 2
        ? `#${match[1]}`
        : `#${match.slice(1, 4).map(value => Number(value).toString(16).padStart(2, '0')).join('')}`;
    }
  }
  els.selectedObjectLabel.textContent = `${kind} · ${id}`;
  els.objectX.value = String(Math.round(Number.parseFloat(node.style.left) || node.offsetLeft || 0));
  els.objectY.value = String(Math.round(Number.parseFloat(node.style.top) || node.offsetTop || 0));
  els.objectWidth.value = String(Math.round(Number.parseFloat(node.style.width) || node.offsetWidth || 1));
  els.objectHeight.value = String(Math.round(Number.parseFloat(node.style.height) || node.offsetHeight || 1));
  els.objectMotion.value = node.getAttribute('data-motion') || '';
  const readOnly = state.project?.id === 'starter';
  [els.objectX, els.objectY, els.objectWidth, els.objectHeight, els.objectMotion, els.applyObjectButton, els.deleteObjectButton]
    .forEach(element => { element.disabled = readOnly; });
}

function selectObject(node) {
  if (state.selectedNode === node) return updateObjectInspector(node);
  state.selectedNode?.classList.remove(
    'studio-editor-selected',
    'studio-editor-resize-hover',
    'studio-editor-resizing',
  );
  state.selectedNode = node;
  node?.classList.add('studio-editor-selected');
  updateObjectInspector(node);
}

function isBottomRightResizePoint(node, event) {
  const rect = node.getBoundingClientRect();
  return event.clientX >= rect.right - 22
    && event.clientX <= rect.right + 10
    && event.clientY >= rect.bottom - 22
    && event.clientY <= rect.bottom + 10;
}

function syncPreviewNodeToSource(node, includeContent = false) {
  const id = node?.getAttribute('data-studio-id');
  if (!id) return;
  const documentValue = bodyDocument();
  const sourceNode = sourceNodeById(documentValue, id);
  if (!sourceNode) return;
  const sourceStyle = node.ownerDocument.defaultView?.getSourceStyleForNode?.(node)
    || node.getAttribute('style')
    || '';
  if (!node.hasAttribute('data-motion')) {
    const previewStyle = node.ownerDocument.defaultView?.rebaseSourceCss?.(sourceStyle) || sourceStyle;
    node.setAttribute('style', previewStyle);
  }
  sourceNode.setAttribute('style', sourceStyle);
  ['data-motion', 'data-studio-max-font-size'].forEach(attribute => {
    const value = node.getAttribute(attribute);
    if (value === null) sourceNode.removeAttribute(attribute);
    else sourceNode.setAttribute(attribute, value);
  });
  if (includeContent) sourceNode.innerHTML = node.innerHTML;
  els.bodyEditor.value = serializeBodyDocument(documentValue);
  setDirty(true);
}

function autofitTextNode(node) {
  if (node?.getAttribute('data-studio-kind') !== 'text') return;
  const minimum = state.aspectRatio === '9:16' ? 16 : 14;
  const computed = Number.parseFloat(getComputedStyle(node).fontSize) || minimum;
  const maximum = Math.max(minimum, Number(node.dataset.studioMaxFontSize) || computed);
  node.dataset.studioMaxFontSize = String(maximum);
  const wasSelected = node.classList.contains('studio-editor-selected');
  // The editor's selected-state resize handle sits outside the box and otherwise
  // appears as overflow, forcing every autofit operation down to the minimum size.
  if (wasSelected) node.classList.remove('studio-editor-selected');
  try {
    node.style.fontSize = `${maximum}px`;
    let size = maximum;
    while ((node.scrollHeight > node.clientHeight + 1 || node.scrollWidth > node.clientWidth + 1) && size > minimum) {
      size = Math.max(minimum, size - 1);
      node.style.fontSize = `${size}px`;
    }
  } finally {
    if (wasSelected) node.classList.add('studio-editor-selected');
  }
}

function installPreviewEditing() {
  const previewWindow = els.previewFrame.contentWindow;
  const documentValue = previewWindow?.document;
  const stage = documentValue?.querySelector('#stage');
  if (!stage || !previewWindow.compositionReady) return false;

  let editorStyle = documentValue.querySelector('style[data-source-editor]');
  if (!editorStyle) {
    editorStyle = documentValue.createElement('style');
    editorStyle.dataset.sourceEditor = '';
    editorStyle.textContent = `
      [data-studio-id] { touch-action: none; }
      [data-studio-id].studio-editor-selected {
        outline: 3px solid #3479f6 !important;
        outline-offset: 3px !important;
        cursor: move !important;
      }
      [data-studio-id].studio-editor-selected::after {
        position: absolute; right: -8px; bottom: -8px; width: 14px; height: 14px;
        border: 2px solid #fff; border-radius: 3px; background: #3479f6; content: "";
        cursor: nwse-resize !important;
      }
      [data-studio-id].studio-editor-resize-hover,
      [data-studio-id].studio-editor-resizing {
        cursor: nwse-resize !important;
      }
      [data-studio-kind="text"][contenteditable="true"] {
        cursor: text !important; outline-color: #35b85e !important;
      }
    `;
    documentValue.head.append(editorStyle);
  }

  if (!stage.dataset.sourceEditorBound) {
    stage.dataset.sourceEditorBound = 'true';
    stage.addEventListener('pointermove', event => {
      const node = state.selectedNode;
      if (!node || node.isContentEditable || node.classList.contains('studio-editor-resizing')) return;
      node.classList.toggle('studio-editor-resize-hover', isBottomRightResizePoint(node, event));
    });
    stage.addEventListener('pointerleave', () => {
      if (!state.selectedNode?.classList.contains('studio-editor-resizing')) {
        state.selectedNode?.classList.remove('studio-editor-resize-hover');
      }
    });
    stage.addEventListener('pointerdown', event => {
      const node = event.target.closest?.('[data-studio-id]');
      if (!node || !stage.contains(node)) {
        clearSelectedObject();
        return;
      }
      selectObject(node);
      if (node.isContentEditable) return;
      event.preventDefault();
      const resize = isBottomRightResizePoint(node, event);
      node.classList.toggle('studio-editor-resizing', resize);
      let geometryChanged = false;
      const start = {
        x: event.clientX,
        y: event.clientY,
        left: Number.parseFloat(node.style.left) || node.offsetLeft || 0,
        top: Number.parseFloat(node.style.top) || node.offsetTop || 0,
        width: Number.parseFloat(node.style.width) || node.offsetWidth || 1,
        height: Number.parseFloat(node.style.height) || node.offsetHeight || 1,
      };
      const lockAspect = ['image', 'video'].includes(node.getAttribute('data-studio-kind'));
      const aspect = start.width / Math.max(1, start.height);
      node.setPointerCapture?.(event.pointerId);
      const move = moveEvent => {
        const dx = moveEvent.clientX - start.x;
        const dy = moveEvent.clientY - start.y;
        if (!geometryChanged && Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
        geometryChanged = true;
        node.style.position = 'absolute';
        if (resize) {
          let width = Math.max(24, start.width + dx);
          let height = Math.max(24, start.height + dy);
          if (lockAspect && !moveEvent.shiftKey) {
            if (Math.abs(dx / start.width) >= Math.abs(dy / start.height)) height = width / aspect;
            else width = height * aspect;
          }
          node.style.width = `${width}px`;
          node.style.height = `${height}px`;
          autofitTextNode(node);
        } else {
          node.style.left = `${start.left + dx}px`;
          node.style.top = `${start.top + dy}px`;
        }
        updateObjectInspector(node);
      };
      const finish = () => {
        documentValue.removeEventListener('pointermove', move);
        documentValue.removeEventListener('pointerup', finish);
        documentValue.removeEventListener('pointercancel', finish);
        node.classList.remove('studio-editor-resizing');
        if (!geometryChanged) return;
        if (resize) autofitTextNode(node);
        syncPreviewNodeToSource(node);
      };
      documentValue.addEventListener('pointermove', move);
      documentValue.addEventListener('pointerup', finish, { once: true });
      documentValue.addEventListener('pointercancel', finish, { once: true });
    });

    stage.addEventListener('dblclick', event => {
      const node = event.target.closest?.('[data-studio-id][data-studio-kind="text"]');
      if (!node) return;
      event.preventDefault();
      selectObject(node);
      const originalContent = node.innerHTML;
      node.contentEditable = 'true';
      node.focus();
      const finish = () => {
        node.removeAttribute('contenteditable');
        if (node.innerHTML === originalContent) return;
        autofitTextNode(node);
        syncPreviewNodeToSource(node, true);
      };
      node.addEventListener('blur', finish, { once: true });
    });
  }
  selectScene(state.selectedSceneId || state.scenes[0]?.id, false);
  return true;
}

function waitForPreviewEditing(attempt = 0) {
  if (installPreviewEditing()) return;
  if (attempt < 80) window.setTimeout(() => waitForPreviewEditing(attempt + 1), 50);
}

async function selectScene(sceneId, updateNavigation = true) {
  if (!sceneId) return;
  state.selectedSceneId = sceneId;
  clearSelectedObject();
  if (updateNavigation) renderSceneNavigator();
  const previewWindow = els.previewFrame.contentWindow;
  if (typeof previewWindow?.renderScene === 'function') {
    try {
      if (typeof previewWindow.renderSceneAtCue === 'function') {
        await previewWindow.renderSceneAtCue(sceneId);
      } else {
        await previewWindow.renderScene(sceneId, 1);
      }
    } catch {
      // A draft scene list can be newer than the saved preview until the user saves.
    }
  }
}

function moveScene(direction) {
  const index = state.scenes.findIndex(scene => scene.id === state.selectedSceneId);
  const next = state.scenes[index + direction];
  if (next) selectScene(next.id);
}

function reloadPreview() {
  if (!state.project) return;
  clearSelectedObject();
  const base = encodeURIComponent(`/${state.project.relativePath}`);
  els.previewFrame.src = window.appUrl(`/pipeline/shell/index.html?projectBase=${base}&embed=1&editor=1&transition=0&v=${Date.now()}`);
}

async function loadProjects(preferred = '') {
  const data = await apiJson('/api/projects');
  state.projects = data.projects || [];
  const selected = preferred || state.projects.find(project => project.active)?.id || state.projects[0]?.id || '';
  els.projectSelect.innerHTML = state.projects.map(project => (
    `<option value="${escapeHtml(project.id)}" ${project.id === selected ? 'selected' : ''}>${escapeHtml(project.name || project.id)}</option>`
  )).join('');
  els.projectSelect.disabled = !state.projects.length;
  if (selected) await loadProject(selected);
}

async function loadProject(projectId) {
  const project = encodeURIComponent(projectId);
  // Commit the source and media together, so a failed request cannot mix projects.
  const [data, media] = await Promise.all([
    apiJson(`/api/projects/source?project=${project}`),
    projectId === 'starter' ? Promise.resolve({ files: [], missing: [] })
      : apiJson(`/api/projects/media?project=${project}`),
  ]);
  state.project = data.project;
  state.aspectRatio = data.project?.aspectRatio || '16:9';
  document.body.dataset.aspectRatio = state.aspectRatio;
  state.originalScenes = data.files?.scenesJson || '';
  state.originalBody = data.files?.bodyHtml || '';
  state.sourceRevision = data.sourceRevision || '';
  els.scenesEditor.value = state.originalScenes;
  els.bodyEditor.value = state.originalBody;
  state.scenes = parsedScenes(state.originalScenes);
  state.selectedSceneId = state.scenes.some(scene => scene.id === state.selectedSceneId)
    ? state.selectedSceneId
    : state.scenes[0]?.id || '';
  els.sourceProjectName.textContent = data.project?.name || projectId;
  els.projectSelect.value = data.project?.id || projectId;
  renderSceneNavigator();
  setDirty(false);
  renderMedia(media);
  renderIcons();
  reloadPreview();
  await window.AppUI.waitForPreview(els.previewFrame);
  installPreviewEditing();
  requestAnimationFrame(fitPreview);
}

async function switchProject(projectId) {
  if (window.AppUI.busy) return;
  if (state.dirty && !window.confirm('当前源文件有未保存修改。切换项目会丢弃这些修改，是否继续？')) {
    els.projectSelect.value = state.project?.id || '';
    return;
  }
  try {
    await window.AppUI.runProjectTransition('正在切换项目', async () => {
      clearSelectedObject();
      els.previewFrame.contentWindow?.pause?.();
      await postJson('/api/projects/activate', { project: projectId });
      await loadProject(projectId);
      setStatus('项目已切换');
    });
  } catch (error) {
    els.projectSelect.value = state.project?.id || '';
    setStatus(error.message, true);
  }
}

async function validateSource() {
  try {
    const result = await postJson('/api/source/validate', {
      scenesJson: els.scenesEditor.value,
      bodyHtml: els.bodyEditor.value,
      aspectRatio: state.aspectRatio,
    });
    setStatus(`验证通过：${result.sceneCount} 个场景，${result.narrationChars} 个旁白字符。`);
    return true;
  } catch (error) {
    setStatus(error.message, true);
    return false;
  }
}

async function saveSource() {
  if (window.AppUI.busy) return false;
  return window.AppUI.runProjectTransition('正在保存源文件', saveSourceContents);
}

async function saveSourceContents() {
  if (!state.project || state.project.id === 'starter') {
    setStatus('starter 是只读模板，请先选择可编辑项目。', true);
    return false;
  }
  try {
    const result = await postJson('/api/projects/source/draft', {
      project: state.project.id,
      name: state.project.name,
      scenesJson: els.scenesEditor.value,
      bodyHtml: els.bodyEditor.value,
      language: state.project.language,
      aspectRatio: state.aspectRatio,
      overwrite: true,
      sourceRevision: state.sourceRevision,
    });
    state.project = result.project;
    const savedScenes = result.scenesJson || els.scenesEditor.value;
    els.scenesEditor.value = savedScenes;
    state.originalScenes = savedScenes;
    state.originalBody = els.bodyEditor.value;
    state.sourceRevision = result.sourceRevision || state.sourceRevision;
    state.scenes = parsedScenes(savedScenes);
    renderSceneNavigator();
    setDirty(false);
    await loadMedia();
    reloadPreview();
    await window.AppUI.waitForPreview(els.previewFrame);
    setStatus(result.narrationNormalized
      ? '源码已保存；所有旁白已按标点统一为 segments，旧时间轴已清除。'
      : (result.timelineInvalidated
        ? '源码草稿已保存并刷新；旁白结构变化，旧时间轴与字幕已清除。'
        : '源码草稿已保存并刷新；现有旁白、时间轴与字幕已保留。'));
    return true;
  } catch (error) {
    setStatus(error.message, true);
    return false;
  }
}

async function saveVisualBody() {
  if (window.AppUI.busy) return false;
  return window.AppUI.runProjectTransition('正在保存画面', saveVisualBodyContents);
}

async function saveVisualBodyContents() {
  if (!state.project || state.project.id === 'starter') {
    setStatus('starter 是只读模板，请先选择可编辑项目。', true);
    return false;
  }
  if (els.scenesEditor.value !== state.originalScenes) {
    setStatus('场景结构还有未保存修改；请先使用“保存并刷新”，再继续添加视觉对象。', true);
    return false;
  }
  try {
    const result = await postJson('/api/projects/source/body', {
      project: state.project.id,
      bodyHtml: els.bodyEditor.value,
    });
    state.project = result.project;
    state.originalBody = els.bodyEditor.value;
    setDirty(false);
    await loadMedia();
    reloadPreview();
    await window.AppUI.waitForPreview(els.previewFrame);
    return true;
  } catch (error) {
    setStatus(error.message, true);
    return false;
  }
}

function uniqueStudioId(documentValue, prefix) {
  let index = 1;
  let candidate = `${prefix}-${index}`;
  while (sourceNodeById(documentValue, candidate)) {
    index += 1;
    candidate = `${prefix}-${index}`;
  }
  return candidate;
}

async function insertStudioObject(kind, media = null) {
  if (!state.selectedSceneId) {
    setStatus('请先选择要插入对象的场景。', true);
    return;
  }
  const documentValue = bodyDocument();
  const scene = [...documentValue.querySelectorAll('[data-scene]')]
    .find(section => section.getAttribute('data-scene') === state.selectedSceneId);
  if (!scene) {
    setStatus(`body.html 中找不到场景 ${state.selectedSceneId}。`, true);
    return;
  }
  const canvas = scene.querySelector(':scope > .scene-canvas') || scene;
  const object = documentValue.createElement(
    kind === 'image' ? 'img' : kind === 'video' ? 'video' : 'div',
  );
  const shapeColor = /^#[0-9a-f]{6}$/i.test(els.shapeColorInput.value)
    ? els.shapeColorInput.value
    : '#dff3ee';
  const id = uniqueStudioId(documentValue, `${state.selectedSceneId}-${kind}`);
  object.setAttribute('data-studio-id', id);
  object.setAttribute('data-studio-kind', kind);
  object.style.cssText = kind === 'text'
    ? 'position:absolute;left:80px;top:100px;width:480px;height:90px;z-index:10;margin:0;font-size:42px;font-weight:700;line-height:1.15;color:#173b3d;'
    : kind === 'shape'
      ? `position:absolute;left:80px;top:220px;width:360px;height:180px;z-index:2;border-radius:24px;background:${shapeColor};`
      : 'position:absolute;left:80px;top:120px;width:460px;height:280px;z-index:5;object-fit:cover;border-radius:18px;';

  if (kind === 'text') {
    object.textContent = '双击编辑文字';
    object.setAttribute('data-studio-max-font-size', '42');
  }
  if (kind === 'image') {
    object.setAttribute('src', media.path);
    object.setAttribute('alt', media.name || '场景图片');
  }
  if (kind === 'video') {
    object.setAttribute('src', media.path);
    object.setAttribute('muted', '');
    object.setAttribute('playsinline', '');
    object.setAttribute('loop', '');
    object.setAttribute('preload', 'metadata');
  }
  canvas.append(object);
  els.bodyEditor.value = serializeBodyDocument(documentValue);
  setDirty(true);
  if (await saveVisualBody()) {
    setStatus(`${kind === 'image' ? '图片' : kind === 'video' ? '视频' : kind === 'text' ? '文字' : '色块'}已插入场景 ${state.selectedSceneId}。`);
  }
}

function applyObjectInspector() {
  const node = state.selectedNode;
  if (!node) return;
  const previousWidth = Number.parseFloat(node.style.width) || node.offsetWidth || 1;
  const previousHeight = Number.parseFloat(node.style.height) || node.offsetHeight || 1;
  const nextWidth = Math.max(1, Number(els.objectWidth.value) || 1);
  const nextHeight = Math.max(1, Number(els.objectHeight.value) || 1);
  node.style.position = 'absolute';
  node.style.left = `${Number(els.objectX.value) || 0}px`;
  node.style.top = `${Number(els.objectY.value) || 0}px`;
  node.style.width = `${nextWidth}px`;
  node.style.height = `${nextHeight}px`;
  if (els.objectMotion.value) node.setAttribute('data-motion', els.objectMotion.value);
  else node.removeAttribute('data-motion');
  if (Math.abs(nextWidth - previousWidth) >= 0.5 || Math.abs(nextHeight - previousHeight) >= 0.5) {
    autofitTextNode(node);
  }
  syncPreviewNodeToSource(node);
  const previewWindow = node.ownerDocument.defaultView;
  const playback = previewWindow?.getPlaybackState?.();
  previewWindow?.renderAtTime?.(playback?.current || 0);
  updateObjectInspector(node);
}

function deleteSelectedObject() {
  const node = state.selectedNode;
  const id = node?.getAttribute('data-studio-id');
  if (!node || !id || !window.confirm(`删除对象 ${id}？保存前仍可刷新预览放弃修改。`)) return;
  const documentValue = bodyDocument();
  sourceNodeById(documentValue, id)?.remove();
  els.bodyEditor.value = serializeBodyDocument(documentValue);
  node.remove();
  clearSelectedObject();
  setDirty(true);
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function renderMedia(data) {
  const missing = data.missing || [];
  const files = data.files || [];
  els.missingCount.textContent = String(missing.length);
  els.mediaCount.textContent = String(files.length);
  els.missingList.innerHTML = missing.length
    ? missing.map(path => `
      <div class="missing-item">
        <code title="${escapeHtml(path)}">${escapeHtml(path)}</code>
        <button type="button" data-fill-slot="${escapeHtml(path)}">补齐</button>
      </div>`).join('')
    : '<div class="empty-state">HTML 中没有缺失的本地媒体引用。</div>';
  els.mediaList.innerHTML = files.length
    ? files.map(file => {
      const isVideo = String(file.contentType || '').startsWith('video/');
      const preview = isVideo
        ? `<video class="media-thumb" src="${escapeHtml(file.url)}" muted preload="metadata"></video>`
        : `<img class="media-thumb" src="${escapeHtml(file.url)}" alt="" loading="lazy" />`;
      return `
        <article class="media-card">
          ${preview}
          <div class="media-card-copy">
            <code title="${escapeHtml(file.path)}">${escapeHtml(file.path)}</code>
            <small>${formatBytes(file.size)} · ${file.referenced ? '已引用' : '未引用'}</small>
            <div class="media-card-actions">
              <button type="button" data-insert-media="${escapeHtml(file.path)}" data-media-type="${escapeHtml(file.contentType)}" data-media-name="${escapeHtml(file.name)}">插入场景</button>
              <button type="button" data-copy-media="${escapeHtml(file.path)}">复制路径</button>
              <button type="button" data-delete-media="${escapeHtml(file.path)}">删除</button>
            </div>
          </div>
        </article>`;
    }).join('')
    : '<div class="empty-state">还没有项目媒体。拖入文件即可上传。</div>';
}

async function loadMedia() {
  if (!state.project || state.project.id === 'starter') {
    renderMedia({ files: [], missing: [] });
    return;
  }
  const data = await apiJson(`/api/projects/media?project=${encodeURIComponent(state.project.id)}`);
  renderMedia(data);
  renderIcons();
}

async function uploadFile(file, requestedPath = '') {
  if (!state.project || state.project.id === 'starter') return;
  const path = requestedPath || `media/${file.name}`;
  const response = await fetch(
    window.appUrl(`/api/projects/media?project=${encodeURIComponent(state.project.id)}&path=${encodeURIComponent(path)}`),
    { method: 'POST', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' } },
  );
  const raw = await response.text();
  const data = raw ? JSON.parse(raw) : {};
  if (!response.ok) throw new Error(data.error || response.statusText);
  renderMedia(data.media);
}

async function uploadFiles(files, requestedPath = '') {
  const list = [...files];
  if (!list.length) return;
  try {
    if (requestedPath && list.length > 1) throw new Error('补齐单个插槽时请选择一个文件。');
    if (requestedPath) {
      const expected = requestedPath.split('.').pop().toLowerCase();
      const actual = list[0].name.split('.').pop().toLowerCase();
      if (expected !== actual) {
        throw new Error(`插槽需要 .${expected} 文件；当前选择的是 .${actual}。请先转换格式或修改 HTML 路径。`);
      }
    }
    for (const [index, file] of list.entries()) {
      setStatus(`正在上传 ${index + 1}/${list.length}：${file.name}`);
      await uploadFile(file, requestedPath);
    }
    state.pendingMediaPath = '';
    renderIcons();
    reloadPreview();
    setStatus(`已上传 ${list.length} 个媒体文件。`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    els.mediaInput.value = '';
  }
}

async function deleteMedia(path) {
  if (!window.confirm(`删除 ${path}？HTML 中的引用不会自动移除。`)) return;
  try {
    const data = await postJson('/api/projects/media/delete', {
      project: state.project.id,
      path,
    });
    renderMedia(data.media);
    renderIcons();
    reloadPreview();
    setStatus(`已删除 ${path}`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

function bindEvents() {
  document.querySelectorAll('[data-editor-tab]').forEach(button => {
    button.addEventListener('click', () => setEditorTab(button.dataset.editorTab));
  });
  [els.scenesEditor, els.bodyEditor].forEach(editor => {
    editor.addEventListener('input', () => {
      if (editor === els.scenesEditor) {
        state.scenes = parsedScenes();
        if (!state.scenes.some(scene => scene.id === state.selectedSceneId)) {
          state.selectedSceneId = state.scenes[0]?.id || '';
        }
        renderSceneNavigator();
      }
      setDirty(true);
      updateEditorMeta();
    });
    editor.addEventListener('keydown', event => {
      if (event.key === 'Tab') {
        event.preventDefault();
        const start = editor.selectionStart;
        editor.setRangeText('  ', start, editor.selectionEnd, 'end');
        setDirty(true);
      }
    });
  });
  els.projectSelect.addEventListener('change', () => switchProject(els.projectSelect.value));
  els.validateButton.addEventListener('click', validateSource);
  els.saveButton.addEventListener('click', saveSource);
  els.reloadPreviewButton.addEventListener('click', reloadPreview);
  els.addTextButton.addEventListener('click', () => insertStudioObject('text'));
  els.addShapeButton.addEventListener('click', () => insertStudioObject('shape'));
  els.shapeColorInput.addEventListener('input', () => {
    const node = state.selectedNode;
    if (node?.getAttribute('data-studio-kind') !== 'shape') return;
    node.style.background = els.shapeColorInput.value;
    syncPreviewNodeToSource(node);
  });
  els.previousSceneButton.addEventListener('click', () => moveScene(-1));
  els.nextSceneButton.addEventListener('click', () => moveScene(1));
  els.sceneNavigator.addEventListener('click', event => {
    const button = event.target.closest('[data-scene-id]');
    if (button) selectScene(button.dataset.sceneId);
  });
  els.previewFrame.addEventListener('load', () => waitForPreviewEditing());
  els.applyObjectButton.addEventListener('click', applyObjectInspector);
  els.deleteObjectButton.addEventListener('click', deleteSelectedObject);
  els.uploadButton.addEventListener('click', () => {
    state.pendingMediaPath = '';
    els.mediaInput.multiple = true;
    els.mediaInput.click();
  });
  els.mediaInput.addEventListener('change', () => uploadFiles(els.mediaInput.files, state.pendingMediaPath));
  els.missingList.addEventListener('click', event => {
    const button = event.target.closest('[data-fill-slot]');
    if (!button) return;
    state.pendingMediaPath = button.dataset.fillSlot;
    els.mediaInput.multiple = false;
    els.mediaInput.click();
  });
  els.mediaList.addEventListener('click', async event => {
    const insert = event.target.closest('[data-insert-media]');
    if (insert) {
      await insertStudioObject(
        String(insert.dataset.mediaType || '').startsWith('video/') ? 'video' : 'image',
        {
          path: insert.dataset.insertMedia,
          name: insert.dataset.mediaName,
        },
      );
      return;
    }
    const copy = event.target.closest('[data-copy-media]');
    if (copy) {
      await navigator.clipboard.writeText(copy.dataset.copyMedia);
      setStatus(`已复制 ${copy.dataset.copyMedia}`);
      return;
    }
    const remove = event.target.closest('[data-delete-media]');
    if (remove) deleteMedia(remove.dataset.deleteMedia);
  });
  ['dragenter', 'dragover'].forEach(type => els.dropZone.addEventListener(type, event => {
    event.preventDefault();
    els.dropZone.classList.add('dragging');
  }));
  ['dragleave', 'drop'].forEach(type => els.dropZone.addEventListener(type, event => {
    event.preventDefault();
    els.dropZone.classList.remove('dragging');
  }));
  els.dropZone.addEventListener('drop', event => uploadFiles(event.dataTransfer.files));
  window.addEventListener('paste', event => {
    if (document.activeElement === els.scenesEditor || document.activeElement === els.bodyEditor) return;
    const files = [...(event.clipboardData?.items || [])]
      .filter(item => item.kind === 'file')
      .map(item => item.getAsFile())
      .filter(Boolean);
    if (files.length) uploadFiles(files);
  });
  window.addEventListener('resize', fitPreview);
  window.addEventListener('beforeunload', event => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = '';
  });
  window.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      saveSource();
    }
  });
}

async function init() {
  try {
    bindEvents();
    renderIcons();
    await window.AppUI.runProjectTransition('正在加载项目', () =>
      loadProjects(new URLSearchParams(window.location.search).get('project') || ''));
    setStatus('源文件编辑器已就绪');
  } catch (error) {
    setStatus(error.message, true);
  }
}

init();
