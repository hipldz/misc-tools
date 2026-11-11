const RUNTIME_PARAMS = new URLSearchParams(window.location.search);
const PROJECT_BASE = window.appUrl(RUNTIME_PARAMS.get('projectBase') || '/.local/work/starter');
const SOURCE_BASE = PROJECT_BASE.replace(/\/$/, '');
const ASSET_BASE = `${SOURCE_BASE}/generated`;
const NARRATION_SRC = `${ASSET_BASE}/narration.mp3`;
const DEFAULT_SCENE_TRANSITION_SECONDS = 0.4;
const MAX_SCENE_TRANSITION_SECONDS = 2;

function resolveTransitionSeconds(search) {
  const raw = new URLSearchParams(search).get('transition');
  if (raw === null || raw.trim() === '') return DEFAULT_SCENE_TRANSITION_SECONDS;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return DEFAULT_SCENE_TRANSITION_SECONDS;
  return Math.max(0, Math.min(MAX_SCENE_TRANSITION_SECONDS, parsed));
}

const SCENE_TRANSITION_SECONDS = resolveTransitionSeconds(window.location.search);

const state = {
  scenes: [],
  timeline: null,
  duration: 0,
  current: 0,
  playing: false,
  raf: null,
  startedAt: 0,
  startOffset: 0,
  hasNarrationAudio: false,
  renderMode: RUNTIME_PARAMS.has('render'),
  captureMode: RUNTIME_PARAMS.get('capture') || '',
  embedMode: RUNTIME_PARAMS.has('embed'),
  editorMode: RUNTIME_PARAMS.has('editor'),
  projectMeta: {},
  aspectRatio: '16:9',
  visualModule: null,
};

const stage = document.querySelector('#stage');
const caption = document.querySelector('#caption');
const captionSafe = document.querySelector('.caption-safe');
const audio = document.querySelector('#narration');
const playButton = document.querySelector('#playButton');
const scrubber = document.querySelector('#scrubber');
const timecode = document.querySelector('#timecode');
const durationLabel = document.querySelector('#durationLabel');
const chapterRail = document.querySelector('#chapterRail');
const sceneTransition = document.querySelector('#sceneTransition');
const motionBaseStyles = new WeakMap();
const mediaMetadataPromises = new WeakMap();
const imageLoadPromises = new WeakMap();
const mediaWarnings = new WeakSet();
const runtimeVisibilityStyle = document.createElement('style');
document.head.append(runtimeVisibilityStyle);

document.documentElement.classList.toggle('render-mode', state.renderMode);
document.documentElement.classList.toggle('preview-mode', !state.renderMode);
document.documentElement.classList.toggle('embed-mode', state.embedMode);
document.documentElement.classList.toggle('editor-mode', state.editorMode);

function applyProjectAspectRatio(value) {
  state.aspectRatio = value === '9:16' ? '9:16' : '16:9';
  document.documentElement.dataset.aspectRatio = state.aspectRatio;
  document.body.dataset.aspectRatio = state.aspectRatio;
}

applyProjectAspectRatio('16:9');

const pad = (value, width = 2) => String(value).padStart(width, '0');

function formatTime(seconds, withMs = false) {
  const safe = Math.max(0, seconds || 0);
  const minutes = Math.floor(safe / 60);
  const wholeSeconds = Math.floor(safe % 60);
  const millis = Math.floor((safe % 1) * 1000);
  return `${pad(minutes)}:${pad(wholeSeconds)}${withMs ? `.${pad(millis, 3)}` : ''}`;
}

function fitCaptionText() {
  caption.style.removeProperty('font-size');
  if (!caption.textContent || !captionSafe) return;

  const allowedHeight = Math.max(44, captionSafe.clientHeight * 1.35);
  const minimumSize = Math.max(10, window.innerHeight * 0.014);
  let size = Number.parseFloat(getComputedStyle(caption).fontSize) || 17;
  while (caption.scrollHeight > allowedHeight && size > minimumSize) {
    size = Math.max(minimumSize, size - 1);
    caption.style.fontSize = `${size}px`;
  }
}

function renderCaption(cue) {
  const text = cue?.text || '';
  if (caption.textContent !== text) {
    caption.textContent = text;
    fitCaptionText();
  }
  caption.classList.toggle('show', Boolean(text));
}

function captionTextUnits(text) {
  return [...String(text || '').trim()].reduce((total, char) => {
    if (/\s/u.test(char)) return total + 0.3;
    if (/^[\x00-\x7f]$/u.test(char)) return total + 0.55;
    return total + 1;
  }, 0);
}

function splitNarration(text) {
  const source = String(text || '');
  const tokens = source.match(/[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*|\s+|./gu) || [source];
  const chunks = [];
  let current = '';

  tokens.forEach(token => {
    if (current && captionTextUnits(current + token) > 26) {
      chunks.push(current.trim());
      current = '';
    }
    current += token;
    const hardBreak = /[\u3002\uff01\uff1f\uff1b.!?;][\u201d\u2019"'\uff09\u3011\u300b]*\s*$/u.test(current);
    const softBreak = /[\uff0c\u3001\uff1a,:][\u201d\u2019"'\uff09\u3011\u300b]*\s*$/u.test(current)
      && captionTextUnits(current) >= 8;
    if (hardBreak || softBreak) {
      chunks.push(current.trim());
      current = '';
    }
  });
  if (current.trim()) chunks.push(current.trim());

  if (chunks.length > 1) {
    const tail = chunks[chunks.length - 1];
    const previous = chunks[chunks.length - 2];
    const previousEndsSentence = /[\u3002\uff01\uff1f\uff1b.!?;][\u201d\u2019"'\uff09\u3011\u300b]*$/u.test(previous);
    if (!previousEndsSentence && captionTextUnits(tail) <= 7 && captionTextUnits(previous + tail) <= 36) {
      chunks.splice(-2, 2, `${previous}${tail}`);
    }
  }
  return chunks.length ? chunks : [source];
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

async function fetchText(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.text();
}

function sourceUrl(value) {
  if (!value || /^(?:[a-z]+:|\/\/|#|\/)/i.test(value)) return value;
  if (value.startsWith(`${SOURCE_BASE}/`)) return value;
  return `${SOURCE_BASE}/${value.replace(/^\.\//, '')}`;
}

function clearEmbeddedAssets() {
  document.querySelectorAll('[data-source-embedded]').forEach(element => element.remove());
}

function rebaseEmbeddedCss(source) {
  return String(source || '').replace(/url\(\s*(['"]?)([^'"\)]+)\1\s*\)/gi, (match, quote, value) => {
    const trimmed = value.trim();
    if (isExternalUrl(trimmed) || trimmed.startsWith('data:')) return match;
    return `url("${sourceUrl(trimmed)}")`;
  });
}

function restoreSourceCssUrls(source) {
  const bases = [`${SOURCE_BASE}/`, new URL(`${SOURCE_BASE}/`, document.baseURI).href];
  return String(source || '').replace(/url\(\s*(['"]?)([^'"\)]+)\1\s*\)/gi, (match, quote, value) => {
    const trimmed = value.trim();
    const base = bases.find(prefix => trimmed.startsWith(prefix));
    return base ? `url("${trimmed.slice(base.length)}")` : match;
  });
}

async function importInlineModule(source) {
  const blob = new Blob([source], { type: 'text/javascript' });
  const url = URL.createObjectURL(blob);
  try {
    return await import(url);
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function executeEmbeddedScripts(scripts) {
  if (!scripts.length) return null;
  if (scripts.length > 1) throw new Error('body.html may include at most one deterministic module script');
  const script = scripts[0];
  if ((script.getAttribute('type') || '').trim().toLowerCase() !== 'module' || script.hasAttribute('src')) {
    throw new Error('body.html scripts must be one inline type="module" visual module');
  }
  const module = await importInlineModule(script.textContent || '');
  if (typeof module.mount !== 'function' || typeof module.renderAtTime !== 'function') {
    throw new Error('body.html visual code must export mount() and renderAtTime()');
  }
  return module;
}

async function loadBodyDocument(source) {
  clearEmbeddedAssets();
  const parsed = new DOMParser().parseFromString(source, 'text/html');
  const styles = [...parsed.querySelectorAll('style, link[rel~="stylesheet"]')];
  const scripts = [...parsed.querySelectorAll('script')];
  styles.forEach(original => {
    const element = document.importNode(original, true);
    element.dataset.sourceEmbedded = '';
    if (element.tagName === 'LINK') element.href = sourceUrl(element.getAttribute('href'));
    else element.textContent = rebaseEmbeddedCss(element.textContent);
    document.head.append(element);
    original.remove();
  });
  scripts.forEach(script => script.remove());
  stage.innerHTML = parsed.body.innerHTML;
  rebaseMediaUrls(stage);
  return scripts;
}

async function fetchOptionalJson(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

function estimatedTimeline(scenes) {
  let cursor = 0;
  const timelineScenes = [];
  const cues = [];

  scenes.forEach((scene, index) => {
    const segments = Array.isArray(scene?.narration?.segments)
      ? scene.narration.segments.filter(segment => segment && String(segment.text || '').trim())
      : null;
    if (!segments?.length) {
      throw new Error(`Scene ${scene?.id || index + 1} narration must use a non-empty segments array`);
    }
    const narration = segments.map(segment => String(segment.text).trim()).join(' ');
    const chunks = segments;
    const duration = Math.min(90, Math.max(8, narration.length / 5.5, chunks.length * 1.2));
    const cueDuration = duration / Math.max(1, chunks.length);

    chunks.forEach((chunk, cueIndex) => {
      const holdGap = Math.min(0.08, cueDuration * 0.15);
      cues.push({
        id: chunk.id,
        start: Number((cursor + cueIndex * cueDuration).toFixed(3)),
        end: Number((cursor + (cueIndex + 1) * cueDuration - holdGap).toFixed(3)),
        text: String(chunk.text).trim(),
        scene_id: scene.id,
      });
    });

    timelineScenes.push({
      ...scene,
      start: Number(cursor.toFixed(3)),
      duration: Number(duration.toFixed(3)),
    });

    cursor += duration + (index === scenes.length - 1 ? 0 : 0.28);
  });

  return {
    duration: Number(cursor.toFixed(3)),
    estimated: true,
    scenes: timelineScenes,
    cues,
  };
}

function isExternalUrl(value) {
  return /^(?:[a-z]+:|\/\/|#|\/)/i.test(value || '');
}

function rebaseSrcset(source) {
  // Scan URL tokens separately from descriptors. A data URL may contain commas;
  // only trailing commas or commas after descriptors delimit a candidate.
  let cursor = 0;
  let copied = 0;
  let rebased = '';
  while (cursor < source.length) {
    while (cursor < source.length && /[\s,]/.test(source[cursor])) cursor += 1;
    const start = cursor;
    while (cursor < source.length && !/\s/.test(source[cursor])) cursor += 1;
    let end = cursor;
    while (end > start && source[end - 1] === ',') end -= 1;
    if (end === start) continue;
    rebased += source.slice(copied, start) + sourceUrl(source.slice(start, end));
    copied = end;
    if (end < cursor) continue;
    let parentheses = 0;
    while (cursor < source.length) {
      const char = source[cursor++];
      if (char === '(') parentheses += 1;
      else if (char === ')') parentheses = Math.max(0, parentheses - 1);
      else if (char === ',' && !parentheses) break;
    }
  }
  return rebased + source.slice(copied);
}

function rebaseMediaUrls(root) {
  const attributes = [
    ['src', 'img,video,audio,source,track,iframe'],
    ['href', 'a,link,image'],
    ['xlink:href', 'image'],
    ['poster', 'video'],
  ];

  for (const [attribute, selector] of attributes) {
    root.querySelectorAll(selector).forEach(element => {
      const value = element.getAttribute(attribute);
      if (!value || isExternalUrl(value)) return;
      if (attribute === 'xlink:href') {
        element.setAttributeNS('http://www.w3.org/1999/xlink', attribute, sourceUrl(value));
      } else element.setAttribute(attribute, sourceUrl(value));
    });
  }
  root.querySelectorAll('img[srcset],source[srcset]').forEach(element => {
    element.setAttribute('srcset', rebaseSrcset(element.getAttribute('srcset') || ''));
  });
  root.querySelectorAll('[style]').forEach(element => {
    const original = element.getAttribute('style') || '';
    const rebased = rebaseEmbeddedCss(original);
    if (rebased !== original) element.setAttribute('style', rebased);
  });
}

function sceneIndexAt(seconds) {
  const scenes = state.timeline?.scenes || [];
  if (!scenes.length) return 0;
  let index = 0;
  for (let candidate = 1; candidate < scenes.length; candidate += 1) {
    const previous = scenes[candidate - 1];
    const previousEnd = Number(previous.start || 0) + Number(previous.duration || 0);
    const nextStart = Number(scenes[candidate].start || previousEnd);
    const cut = (previousEnd + nextStart) / 2;
    if (seconds < cut) break;
    index = candidate;
  }
  return index;
}

function transitionOpacityAt(seconds) {
  const scenes = state.timeline?.scenes || [];
  if (scenes.length < 2 || SCENE_TRANSITION_SECONDS <= 0) return 0;

  for (let index = 0; index < scenes.length - 1; index += 1) {
    const current = scenes[index];
    const next = scenes[index + 1];
    const currentEnd = Number(current.start || 0) + Number(current.duration || 0);
    const nextStart = Number(next.start || currentEnd);
    const midpoint = (currentEnd + nextStart) / 2;
    const halfDuration = SCENE_TRANSITION_SECONDS / 2;
    const transitionStart = midpoint - halfDuration;
    const transitionEnd = midpoint + halfDuration;

    if (seconds >= transitionStart && seconds < midpoint) {
      return Math.max(0, Math.min(1, (seconds - transitionStart) / halfDuration));
    }
    if (seconds >= midpoint && seconds < transitionEnd) {
      return Math.max(0, Math.min(1, 1 - (seconds - midpoint) / halfDuration));
    }
  }
  return 0;
}

function progressAt(scene, seconds) {
  if (!scene?.duration) return 0;
  return Math.max(0, Math.min(1, (seconds - scene.start) / scene.duration));
}

const clamp01 = value => Math.max(0, Math.min(1, Number(value) || 0));
const smoothstep = value => {
  const progress = clamp01(value);
  return progress * progress * (3 - 2 * progress);
};

function motionWindow(progress, start, duration) {
  return smoothstep((progress - start) / Math.max(0.001, duration));
}

function applyMotionPresets(activeScene, sceneProgress) {
  if (!activeScene) return;
  activeScene.querySelectorAll('[data-motion]').forEach(element => {
    if (!motionBaseStyles.has(element)) {
      motionBaseStyles.set(element, {
        opacity: element.style.opacity,
        transform: element.style.transform,
        clipPath: element.style.clipPath,
        filter: element.style.filter,
      });
    }
    const base = motionBaseStyles.get(element);
    const preset = String(element.dataset.motion || '').trim();
    const start = clamp01(element.dataset.motionDelay || 0.03);
    const duration = clamp01(element.dataset.motionDuration || 0.18) || 0.18;
    const enter = motionWindow(sceneProgress, start, duration);
    const baseTransform = base.transform && base.transform !== 'none' ? `${base.transform} ` : '';
    element.style.opacity = base.opacity;
    element.style.transform = base.transform;
    element.style.clipPath = base.clipPath;
    element.style.filter = base.filter;

    // Source editing needs the authored geometry, not an entrance or camera pose.
    if (state.editorMode) return;

    if (preset === 'fade') {
      element.style.opacity = String(enter);
    } else if (preset === 'rise') {
      element.style.opacity = String(enter);
      element.style.transform = `${baseTransform}translateY(${((1 - enter) * 28).toFixed(2)}px)`;
    } else if (preset === 'slide-left') {
      element.style.opacity = String(enter);
      element.style.transform = `${baseTransform}translateX(${((1 - enter) * 42).toFixed(2)}px)`;
    } else if (preset === 'wipe-left') {
      element.style.clipPath = `inset(0 ${((1 - enter) * 100).toFixed(2)}% 0 0)`;
    } else if (preset === 'zoom-in') {
      element.style.opacity = String(enter);
      element.style.transform = `${baseTransform}scale(${(0.92 + enter * 0.08).toFixed(4)})`;
    } else if (preset === 'ken-burns-in') {
      element.style.transform = `${baseTransform}scale(${(1 + clamp01(sceneProgress) * 0.06).toFixed(4)})`;
    } else if (preset === 'pan-left') {
      element.style.transform = `${baseTransform}translateX(${(12 - clamp01(sceneProgress) * 24).toFixed(2)}px)`;
    } else if (preset === 'pan-right') {
      element.style.transform = `${baseTransform}translateX(${(-12 + clamp01(sceneProgress) * 24).toFixed(2)}px)`;
    } else if (preset === 'pulse-once') {
      const phase = clamp01((sceneProgress - 0.35) / 0.3);
      const pulse = Math.sin(phase * Math.PI) * 0.045;
      element.style.transform = `${baseTransform}scale(${(1 + pulse).toFixed(4)})`;
    }
  });
}

function sourceStyleForNode(element) {
  const clone = document.createElement('div');
  clone.setAttribute('style', element?.getAttribute('style') || '');
  const base = motionBaseStyles.get(element);
  if (base) {
    clone.style.opacity = base.opacity;
    clone.style.transform = base.transform;
    clone.style.clipPath = base.clipPath;
    clone.style.filter = base.filter;
  }
  return restoreSourceCssUrls(clone.getAttribute('style') || '');
}

function syncCssAnimations(activeScene, sceneTime) {
  if (!activeScene?.getAnimations) return;
  activeScene.getAnimations({ subtree: true }).forEach(animation => {
    animation.pause();
    try {
      animation.currentTime = Math.max(0, sceneTime) * 1000;
    } catch {
      // Some browser-owned animations do not expose a writable currentTime.
    }
  });
}

function activeCueAt(seconds) {
  return state.timeline?.cues?.find(cue => seconds >= cue.start && seconds < cue.end);
}

function timelineMatchesSource(timeline, scenes) {
  const timelineScenes = timeline?.scenes || [];
  if (timelineScenes.length !== scenes.length) return false;
  return scenes.every((scene, index) => (
    timelineScenes[index]?.id === scene.id
    && JSON.stringify(timelineScenes[index]?.narration ?? null) === JSON.stringify(scene.narration ?? null)
  ));
}

function timelineAudioKey(timeline) {
  const raw = [
    timeline?.duration,
    timeline?.voice,
    timeline?.rate,
    timeline?.pitch,
    ...(timeline?.scenes || []).map(scene => `${scene.id}:${JSON.stringify(scene.narration ?? null)}`),
  ].join('|');
  let hash = 0;
  for (let index = 0; index < raw.length; index += 1) {
    hash = ((hash << 5) - hash + raw.charCodeAt(index)) | 0;
  }
  return Math.abs(hash).toString(36);
}

function setNarrationAudio(enabled, timeline = null) {
  state.hasNarrationAudio = Boolean(enabled && audio);
  if (!audio) return;
  if (state.hasNarrationAudio) {
    audio.src = `${NARRATION_SRC}?v=${timelineAudioKey(timeline)}`;
    audio.load();
    return;
  }
  if (!audio.paused) audio.pause();
  audio.removeAttribute('src');
  audio.load();
}

function normalizeCaptionCue(cue, index) {
  return {
    id: String(cue?.id || `cue-${String(index + 1).padStart(4, '0')}`),
    scene_id: String(cue?.scene_id || ''),
    start: Number(cue?.start || 0),
    end: Number(cue?.end || 0),
    text: String(cue?.text || ''),
  };
}

function cueIdentityMatches(current, generated) {
  return current.id === generated.id && current.scene_id === generated.scene_id;
}

function cueTimingIsValid(cue, duration) {
  return Number.isFinite(cue.start)
    && Number.isFinite(cue.end)
    && cue.start >= 0
    && cue.end > cue.start
    && cue.end <= duration + 0.05;
}

function signatureMatchesTimeline(signature, timeline) {
  const timelineCues = timeline?.cues || [];
  if (!Array.isArray(signature) || signature.length !== timelineCues.length) return false;

  return signature.every((cue, index) => {
    const saved = normalizeCaptionCue(cue, index);
    const generated = normalizeCaptionCue(timelineCues[index], index);
    return cueIdentityMatches(saved, generated)
      && saved.text === generated.text
      && Math.abs(saved.start - generated.start) <= 0.002
      && Math.abs(saved.end - generated.end) <= 0.002;
  });
}

function captionsMatchTimeline(captions, timeline) {
  const cues = Array.isArray(captions) ? captions : captions?.cues;
  const timelineCues = timeline?.cues || [];
  if (!Array.isArray(cues) || cues.length !== timelineCues.length) return false;

  const hasSignature = !Array.isArray(captions) && Array.isArray(captions?.timeline_signature);
  if (hasSignature && !signatureMatchesTimeline(captions.timeline_signature, timeline)) return false;

  return cues.every((cue, index) => {
    const current = normalizeCaptionCue(cue, index);
    const generated = normalizeCaptionCue(timelineCues[index], index);
    if (!cueIdentityMatches(current, generated)) return false;
    if (!cueTimingIsValid(current, Number(timeline?.duration) || 0)) return false;

    if (!hasSignature) {
      return Math.abs(current.start - generated.start) <= 0.05
        && Math.abs(current.end - generated.end) <= 0.05;
    }
    return true;
  });
}

async function applyCaptionOverrides(timeline) {
  const captions = await fetchOptionalJson(`${SOURCE_BASE}/captions.json`);
  if (!captions || !captionsMatchTimeline(captions, timeline)) return timeline;

  const cues = (Array.isArray(captions) ? captions : captions.cues)
    .map((cue, index) => {
      const timing = normalizeCaptionCue(cue, index);
      const generated = normalizeCaptionCue(timeline.cues[index], index);
      return { ...generated, start: timing.start, end: timing.end };
    });
  return { ...timeline, cues };
}

function chapterLabel(scene) {
  const value = scene?.category || scene?.chapter || scene?.title || scene?.id || 'Scene';
  return String(value).trim();
}

function chapterTimelineGeometry(scenes) {
  const duration = Math.max(0.001, Number(state.duration) || 0.001);
  return scenes.map((scene, index) => {
    const sceneStart = Math.max(0, Number(scene.start) || 0);
    const sceneEnd = sceneStart + Math.max(0, Number(scene.duration) || 0);
    const previous = scenes[index - 1];
    const next = scenes[index + 1];
    const previousEnd = previous
      ? Math.max(0, Number(previous.start) || 0) + Math.max(0, Number(previous.duration) || 0)
      : 0;
    const nextStart = next ? Math.max(sceneEnd, Number(next.start) || sceneEnd) : duration;
    const leftTime = index === 0 ? 0 : (previousEnd + sceneStart) / 2;
    const rightTime = index === scenes.length - 1 ? duration : (sceneEnd + nextStart) / 2;
    return {
      left: clamp01(leftTime / duration),
      right: clamp01(rightTime / duration),
      anchor: clamp01((leftTime + rightTime) / 2 / duration),
    };
  });
}

function fitChapterLabelWidths(preferred, minimum, available) {
  const preferredTotal = preferred.reduce((sum, width) => sum + width, 0);
  if (preferredTotal <= available) return preferred;
  const minimumTotal = minimum.reduce((sum, width) => sum + width, 0);
  if (minimumTotal >= available) {
    const ratio = available / Math.max(1, minimumTotal);
    return minimum.map(width => width * ratio);
  }
  const reduction = preferredTotal - available;
  const flexibility = preferred.reduce(
    (sum, width, index) => sum + Math.max(0, width - minimum[index]),
    0,
  );
  return preferred.map((width, index) => (
    width - reduction * (Math.max(0, width - minimum[index]) / Math.max(1, flexibility))
  ));
}

function layoutChapterLabels() {
  if (!chapterRail) return;
  const items = [...chapterRail.querySelectorAll('.chapter-label-item')];
  const railWidth = chapterRail.clientWidth;
  if (!items.length || !railWidth) return;

  const portrait = state.aspectRatio === '9:16';
  const preferredGap = Math.max(3, Math.min(6, railWidth * 0.004));
  const nominalWidth = (railWidth - preferredGap * Math.max(0, items.length - 1)) / items.length;
  const minimumLimit = portrait ? 30 : 38;
  const comfortableMinimum = portrait ? 44 : 54;
  const maximum = portrait ? 82 : 118;
  const canvas = layoutChapterLabels.canvas || document.createElement('canvas');
  layoutChapterLabels.canvas = canvas;
  const context = canvas.getContext('2d');

  const preferred = items.map(item => {
    const label = item.querySelector('.chapter-label');
    const style = getComputedStyle(label);
    if (context) context.font = style.font || `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const measured = context ? context.measureText(label.textContent || '').width : label.textContent.length * 8;
    return Math.max(minimumLimit, Math.min(maximum, Math.ceil(measured + 14)));
  });
  const minimum = preferred.map(width => Math.min(
    width,
    Math.max(minimumLimit, Math.min(comfortableMinimum, nominalWidth * 0.78)),
  ));
  const available = Math.max(1, railWidth - preferredGap * Math.max(0, items.length - 1));
  const fittedWidths = fitChapterLabelWidths(preferred, minimum, available);
  const anchors = items.map(item => clamp01(item.dataset.anchorRatio) * railWidth);
  const bounds = items.map(item => ({
    left: clamp01(item.dataset.leftRatio) * railWidth,
    right: clamp01(item.dataset.rightRatio) * railWidth,
  }));
  const widths = fittedWidths.map((width, index) => Math.max(
    1,
    Math.min(width, bounds[index].right - bounds[index].left - preferredGap),
  ));
  const left = widths.map((width, index) => anchors[index] - width / 2);

  items.forEach((item, index) => {
    const width = widths[index];
    item.style.left = `${left[index].toFixed(2)}px`;
    item.style.width = `${width.toFixed(2)}px`;
  });
  const preferredTotal = preferred.reduce((sum, width) => sum + width, 0)
    + preferredGap * Math.max(0, items.length - 1);
  const intervalConstrained = widths.some((width, index) => width + 0.5 < fittedWidths[index]);
  chapterRail.dataset.labelDensity = preferredTotal <= railWidth && !intervalConstrained
    ? 'relaxed'
    : 'compact';
}

function setupChapterRail() {
  if (!chapterRail) return;
  chapterRail.replaceChildren();

  const fill = document.createElement('i');
  fill.className = 'chapter-rail-fill';
  chapterRail.append(fill);

  const scenes = state.timeline?.scenes?.length
    ? state.timeline.scenes.map((timelineScene, index) => {
      const sourceScene = state.scenes.find(item => item.id === timelineScene.id) || state.scenes[index] || {};
      return { ...timelineScene, ...sourceScene, duration: timelineScene.duration };
    })
    : state.scenes;
  const geometry = chapterTimelineGeometry(scenes);
  const segmentLayer = document.createElement('div');
  segmentLayer.className = 'chapter-segment-layer';
  const labelLayer = document.createElement('div');
  labelLayer.className = 'chapter-label-layer';

  scenes.forEach((scene, index) => {
    const segment = document.createElement('i');
    segment.className = 'chapter-segment';
    segment.dataset.sceneId = scene.id || `scene-${index + 1}`;
    segment.dataset.chapterIndex = String(index);
    segment.style.left = `${(geometry[index].left * 100).toFixed(5)}%`;
    segment.style.width = `${((geometry[index].right - geometry[index].left) * 100).toFixed(5)}%`;

    const item = document.createElement('div');
    item.className = 'chapter-label-item';
    item.dataset.sceneId = segment.dataset.sceneId;
    item.dataset.chapterIndex = String(index);
    item.dataset.anchorRatio = geometry[index].anchor.toFixed(6);
    item.dataset.leftRatio = geometry[index].left.toFixed(6);
    item.dataset.rightRatio = geometry[index].right.toFixed(6);
    const label = document.createElement('span');
    label.className = 'chapter-label';
    const labelText = chapterLabel(scene);
    label.textContent = labelText;
    item.title = labelText;
    item.setAttribute('aria-label', labelText);

    item.append(label);
    segmentLayer.append(segment);
    labelLayer.append(item);
  });
  const endMarker = document.createElement('i');
  endMarker.className = 'chapter-end-marker';
  endMarker.setAttribute('aria-hidden', 'true');
  segmentLayer.append(endMarker);
  chapterRail.append(segmentLayer, labelLayer);
  layoutChapterLabels();
  window.requestAnimationFrame(layoutChapterLabels);
}

function updateChapterRail(activeIndex) {
  if (!chapterRail) return;
  const overallProgress = state.duration ? state.current / state.duration : 0;
  const clampedOverall = Math.max(0, Math.min(1, overallProgress));
  chapterRail.style.setProperty('--rail-progress', clampedOverall.toFixed(4));

  [...chapterRail.querySelectorAll('[data-chapter-index]')].forEach(item => {
    const index = Number(item.dataset.chapterIndex);
    item.classList.toggle('is-active', index === activeIndex);
    item.classList.toggle('is-done', index < activeIndex);
  });
}

function activateScene(scene, progress) {
  document.documentElement.style.setProperty('--progress', progress.toFixed(4));
  document.body.dataset.activeScene = scene?.id || '';

  const sections = [...stage.querySelectorAll('[data-scene]')];
  if (!sections.length) return null;

  let active = sections.find(section => section.dataset.scene === scene.id);
  if (!active) active = sections[0];

  sections.forEach(section => {
    const isActive = section === active;
    section.hidden = !isActive;
    section.classList.toggle('is-active', isActive);
    section.classList.toggle('active', isActive);
  });

  const steps = [...active.querySelectorAll('[data-step]')];
  const activeStep = steps.length ? Math.min(steps.length - 1, Math.floor(progress * steps.length)) : -1;
  steps.forEach((step, index) => step.classList.toggle('active', index <= activeStep));
  return active;
}

function runtimeSelector(element) {
  const path = [];
  for (let node = element; node && node !== stage; node = node.parentElement) {
    const index = [...node.parentElement.children].indexOf(node) + 1;
    path.unshift(`:nth-child(${index})`);
  }
  return `#stage > ${path.join(' > ')}`;
}

function applyShotVisibility(activeScene, sceneTime) {
  const hidden = [];
  const cues = (state.timeline?.cues || []).filter(cue => cue.scene_id === activeScene?.dataset.scene);
  activeScene?.querySelectorAll('[data-shot-cues],video[data-media-start]').forEach(element => {
    const cueIds = element.hasAttribute('data-shot-cues')
      ? String(element.dataset.shotCues || '').trim().split(/\s+/)
      : null;
    const windows = [];
    let previousSelected = false;
    if (cueIds) cues.forEach((cue, index) => {
      const selected = cueIds.includes(cue.id);
      if (selected) {
        const start = index === 0 ? -Infinity : Number(cue.start);
        const end = index + 1 < cues.length ? Number(cues[index + 1].start) : Infinity;
        if (previousSelected) windows[windows.length - 1].end = end;
        else windows.push({ start, end });
      }
      previousSelected = selected;
    });
    // Hold a shot through subtitle gaps and the scene edges; cut at the next cue.
    const inCue = !cueIds || windows.some(window => state.current >= window.start && state.current < window.end);
    const beforeStart = element.tagName === 'VIDEO' && sceneTime < Number(element.dataset.mediaStart || 0);
    if (!inCue || beforeStart) {
      const selector = runtimeSelector(element);
      hidden.push(`${selector},${selector} *{visibility:hidden!important;pointer-events:none!important}`);
    }
  });
  // Keep derived visibility outside source nodes, including in Studio editor mode.
  // Studio can save authored geometry without persisting a hidden shot or video.
  const css = hidden.join('\n');
  if (runtimeVisibilityStyle.textContent !== css) runtimeVisibilityStyle.textContent = css;
}

function mediaIsVisible(element, activeScene) {
  if (!activeScene?.contains(element)) return false;
  for (let node = element; node && node !== stage; node = node.parentElement) {
    const style = getComputedStyle(node);
    if (node.hidden || style.display === 'none' || style.visibility === 'hidden'
      || style.visibility === 'collapse' || Number(style.opacity) === 0) return false;
  }
  return true;
}

function mediaError(element, detail) {
  const source = element.currentSrc || element.getAttribute('src')
    || element.querySelector?.('source[src]')?.getAttribute('src') || '(no source)';
  return new Error(`Visual media failed: ${source}: ${detail}`);
}

function waitForMediaEvent(element, eventName, timeout = 5000, ready = null) {
  return new Promise((resolve, reject) => {
    let timer = 0;
    const cleanup = () => {
      window.clearTimeout(timer);
      element.removeEventListener(eventName, finish);
      element.removeEventListener('error', failed);
    };
    const finish = () => { cleanup(); resolve(); };
    const failed = () => { cleanup(); reject(mediaError(element, `could not load/decode ${eventName}`)); };
    element.addEventListener(eventName, finish, { once: true });
    element.addEventListener('error', failed, { once: true });
    timer = window.setTimeout(() => {
      cleanup();
      reject(mediaError(element, `timed out waiting for ${eventName}`));
    }, timeout);
    if (element.error) failed();
    else if (ready?.()) finish();
  });
}

async function videoMetadata(video) {
  if (video.error) throw mediaError(video, `media error ${video.error.code}`);
  if (video.readyState >= 1) return;
  if (!video.getAttribute('src') && !video.querySelector('source[src]')) {
    throw mediaError(video, 'video has no source');
  }
  if (!mediaMetadataPromises.has(video)) {
    const pending = waitForMediaEvent(video, 'loadedmetadata', 5000, () => video.readyState >= 1);
    mediaMetadataPromises.set(video, pending);
    // A previous failed source must not prevent Studio from replacing it.
    pending.catch(() => mediaMetadataPromises.delete(video));
    if (video.preload === 'none') video.load();
  }
  await mediaMetadataPromises.get(video);
}

function videoClipAt(video, sceneTime) {
  const duration = Number(video.duration);
  if (!Number.isFinite(duration) || duration <= 0) throw mediaError(video, 'source has no finite playable duration');
  const start = Number(video.dataset.mediaStart || 0);
  const mediaIn = Number(video.dataset.mediaIn || 0);
  const mediaOut = video.hasAttribute('data-media-out') ? Number(video.dataset.mediaOut) : duration;
  const rate = Number(video.dataset.mediaRate || 1);
  if (![start, mediaIn, mediaOut, rate].every(Number.isFinite)
    || start < 0 || mediaIn < 0 || mediaOut <= mediaIn || rate <= 0 || mediaIn >= duration) {
    throw mediaError(video, 'invalid data-media-in/out/start/rate values');
  }
  const end = Math.min(mediaOut, duration);
  const span = end - mediaIn;
  const elapsed = Math.max(0, sceneTime - start) * rate;
  const finished = !video.loop && elapsed >= span;
  const offset = video.loop ? elapsed % span : Math.min(elapsed, Math.max(0, span - 0.001));
  return { target: mediaIn + offset, mediaIn, end, span, rate, finished, beforeStart: sceneTime < start };
}

async function seekVideoFrame(video, target) {
  if (Math.abs((Number(video.currentTime) || 0) - target) > 0.002) {
    const seeked = waitForMediaEvent(video, 'seeked');
    video.currentTime = target;
    await seeked;
  } else if (video.seeking) {
    await waitForMediaEvent(video, 'seeked', 5000, () => !video.seeking);
  }
  if (video.readyState < 2) {
    await waitForMediaEvent(video, 'loadeddata', 5000, () => video.readyState >= 2);
  }
  if (video.error) throw mediaError(video, `media error ${video.error.code}`);
}

function reportMediaFailure(element, error) {
  if (state.renderMode) {
    window.compositionError = error instanceof Error ? error.message : String(error);
    throw error;
  }
  if (!mediaWarnings.has(element)) {
    mediaWarnings.add(element);
    console.warn(error);
  }
}

async function syncSceneImages(activeScene) {
  if (!activeScene || !state.renderMode) return;
  await Promise.all([...activeScene.querySelectorAll('img')].map(async image => {
    if (!mediaIsVisible(image, activeScene)) return;
    try {
      if (!image.complete) {
        const source = `${image.getAttribute('src') || ''}\n${image.getAttribute('srcset') || ''}`;
        if (imageLoadPromises.get(image)?.source !== source) {
          imageLoadPromises.set(image, {
            source,
            promise: waitForMediaEvent(image, 'load', 5000, () => image.complete),
          });
        }
        await imageLoadPromises.get(image).promise;
      }
      if (!image.naturalWidth) throw mediaError(image, 'image has no decoded pixels');
    } catch (error) {
      reportMediaFailure(image, error);
    }
  }));
}

async function syncSceneVideos(activeScene, sceneTime) {
  const videos = [...stage.querySelectorAll('video')];
  const frameCapture = state.renderMode && state.captureMode === 'frames';
  const renderedTime = state.current;
  const pending = [];

  videos.forEach(video => {
    video.muted = true;
    video.playsInline = true;
    const active = mediaIsVisible(video, activeScene);
    if (!active) {
      video.pause();
      return;
    }

    pending.push((async () => {
      try {
        await videoMetadata(video);
        // A seek, scene cut, or cue change can happen while metadata is loading.
        if (state.current !== renderedTime || !mediaIsVisible(video, activeScene)) return;
        const clip = videoClipAt(video, sceneTime);
        video.playbackRate = clip.rate;
        if (frameCapture || !state.playing || clip.finished || clip.beforeStart) {
          video.pause();
          await seekVideoFrame(video, clip.target);
          return;
        }
        const current = Number(video.currentTime) || 0;
        if (current < clip.mediaIn || current >= clip.end
          || Math.abs(current - clip.target) > Math.min(0.25, clip.span / 4)) video.currentTime = clip.target;
        if (video.paused) video.play().catch(error => {
          if (error.name !== 'AbortError') reportMediaFailure(video, error);
        });
      } catch (error) {
        video.pause();
        reportMediaFailure(video, error);
      }
    })());
  });

  await Promise.all(pending);
}

async function renderAtTime(seconds) {
  state.current = Math.max(0, Math.min(state.duration, Number(seconds) || 0));
  const index = sceneIndexAt(state.current);
  const timelineScene = state.timeline.scenes[index] || state.timeline.scenes[0] || {};
  const sourceScene = state.scenes.find(item => item.id === timelineScene.id) || state.scenes[index] || {};
  const scene = { ...sourceScene, ...timelineScene };
  const progress = progressAt(scene, state.current);
  const cue = activeCueAt(state.current);

  const activeScene = activateScene(scene, progress);
  document.documentElement.dataset.sceneFrame = activeScene?.dataset.frame === 'media' ? 'media' : '';
  applyMotionPresets(activeScene, progress);
  renderCaption(cue);
  updateChapterRail(index);
  if (sceneTransition) sceneTransition.style.opacity = transitionOpacityAt(state.current).toFixed(4);

  if (state.visualModule?.renderAtTime) {
    state.visualModule.renderAtTime(state.current, {
      root: stage,
      scenes: state.scenes,
      scene,
      sceneIndex: index,
      sceneTime: Math.max(0, state.current - (Number(scene.start) || 0)),
      sceneProgress: progress,
      duration: state.duration,
      mediaBase: `${SOURCE_BASE}/media`,
      renderMode: state.renderMode,
      editorMode: state.editorMode,
    });
  }

  syncCssAnimations(activeScene, Math.max(0, state.current - (Number(scene.start) || 0)));
  applyShotVisibility(activeScene, Math.max(0, state.current - (Number(scene.start) || 0)));

  if (timecode) timecode.textContent = formatTime(state.current, true);
  if (scrubber) scrubber.value = state.current;
  await Promise.all([
    syncSceneVideos(activeScene, Math.max(0, state.current - (Number(scene.start) || 0))),
    syncSceneImages(activeScene),
  ]);
}

window.addEventListener('resize', () => {
  fitCaptionText();
  layoutChapterLabels();
});

function playbackState() {
  return {
    playing: state.playing,
    current: state.current,
    duration: state.duration,
  };
}

function publishPlaybackState() {
  window.dispatchEvent(new CustomEvent('shell-playback-state', { detail: playbackState() }));
}

function pause() {
  state.playing = false;
  if (playButton) playButton.textContent = 'Play';
  if (audio && !audio.paused) audio.pause();
  stage.querySelectorAll('video').forEach(video => video.pause());
  cancelAnimationFrame(state.raf);
  publishPlaybackState();
}

function tick(now) {
  if (!state.playing) return;

  if (!state.renderMode && state.hasNarrationAudio && audio && !audio.paused && Number.isFinite(audio.currentTime)) {
    state.current = audio.currentTime;
  } else {
    state.current = state.startOffset + (now - state.startedAt) / 1000;
  }

  if (state.current >= state.duration) {
    state.current = state.duration;
    renderAtTime(state.current);
    pause();
    return;
  }

  renderAtTime(state.current);
  state.raf = requestAnimationFrame(tick);
}

async function startPlayback() {
  if (state.current >= state.duration) {
    state.current = 0;
    await renderAtTime(0);
  }
  state.playing = true;
  if (playButton) playButton.textContent = 'Pause';
  state.startedAt = performance.now();
  state.startOffset = state.current;

  if (!state.renderMode && state.hasNarrationAudio && audio) {
    try {
      audio.currentTime = state.current;
      await audio.play();
    } catch {
      // Browser autoplay rules may block audio; the deterministic clock still works.
    }
  }

  cancelAnimationFrame(state.raf);
  state.raf = requestAnimationFrame(tick);
  publishPlaybackState();
}

function togglePlayback() {
  if (state.playing) {
    pause();
    return Promise.resolve(playbackState());
  }
  return startPlayback().then(playbackState);
}

if (playButton) {
  playButton.addEventListener('click', togglePlayback);
}

if (scrubber) {
  scrubber.addEventListener('input', () => {
    const wasPlaying = state.playing;
    pause();
    state.current = Number(scrubber.value);
    if (state.hasNarrationAudio && audio && Number.isFinite(audio.duration)) audio.currentTime = state.current;
    renderAtTime(state.current);
    if (wasPlaying) startPlayback();
  });
}

async function init() {
  state.projectMeta = await fetchOptionalJson(`${SOURCE_BASE}/manifest.json`) || {};
  applyProjectAspectRatio(state.projectMeta.aspectRatio);
  state.scenes = await fetchJson(`${SOURCE_BASE}/scenes.json`);
  const embeddedScripts = await loadBodyDocument(await fetchText(`${SOURCE_BASE}/body.html`));

  try {
    const timeline = await fetchJson(`${ASSET_BASE}/timeline.json`);
    if (timelineMatchesSource(timeline, state.scenes)) {
      state.timeline = await applyCaptionOverrides(timeline);
      setNarrationAudio(true, timeline);
    } else {
      state.timeline = estimatedTimeline(state.scenes);
      setNarrationAudio(false);
    }
  } catch {
    state.timeline = estimatedTimeline(state.scenes);
    setNarrationAudio(false);
  }

  state.duration = Number(state.timeline.duration) || 0;
  if (scrubber) scrubber.max = state.duration;
  if (durationLabel) durationLabel.textContent = formatTime(state.duration);
  setupChapterRail();

  state.visualModule = await executeEmbeddedScripts(embeddedScripts);
  if (state.visualModule) {
    if (typeof state.visualModule.mount !== 'function' || typeof state.visualModule.renderAtTime !== 'function') {
      throw new Error('body.html visual code must export mount() and renderAtTime()');
    }
    await state.visualModule.mount({
      root: stage,
      scenes: state.scenes,
      timeline: state.timeline,
      duration: state.duration,
      mediaBase: `${SOURCE_BASE}/media`,
      renderMode: state.renderMode,
      editorMode: state.editorMode,
    });
  }

  await renderAtTime(0);
  publishPlaybackState();

  window.compositionReady = true;
  window.demoReady = true;
}

window.getCompositionDuration = () => state.duration;
window.getDemoDuration = window.getCompositionDuration;
window.getCompositionScenes = () => (state.timeline?.scenes || []).map(scene => ({
  id: scene.id,
  category: chapterLabel(scene),
  start: Number(scene.start) || 0,
  duration: Number(scene.duration) || 0,
}));
window.renderScene = (sceneId, progress = 0) => {
  const scenes = state.timeline?.scenes || [];
  const scene = scenes.find(item => item.id === sceneId);
  if (!scene) return Promise.reject(new Error(`Unknown scene: ${sceneId}`));
  const clamped = Math.max(0, Math.min(1, Number(progress) || 0));
  return renderAtTime((Number(scene.start) || 0) + (Number(scene.duration) || 0) * clamped);
};
window.renderSceneAtCue = (sceneId, cueId = null) => {
  const cue = (state.timeline?.cues || []).find(item => (
    item.scene_id === sceneId && (!cueId || item.id === cueId)
    && Number.isFinite(Number(item.start)) && Number(item.end) > Number(item.start)
  ));
  return cue ? renderAtTime((Number(cue.start) + Number(cue.end)) / 2) : window.renderScene(sceneId, 0.5);
};
window.renderAtTime = renderAtTime;
window.getPlaybackState = playbackState;
window.togglePlayback = togglePlayback;
window.getSourceStyleForNode = sourceStyleForNode;
window.rebaseSourceCss = rebaseEmbeddedCss;
window.compositionError = null;
window.startCompositionPlayback = async () => {
  state.current = 0;
  await renderAtTime(0);
  return startPlayback();
};
window.startDeterministicPlayback = window.startCompositionPlayback;
window.addEventListener('beforeunload', () => state.visualModule?.destroy?.());

init().catch(error => {
  const message = error instanceof Error ? error.message : String(error);
  window.compositionError = message;
  stage.innerHTML = `<pre class="load-error"></pre>`;
  stage.querySelector('.load-error').textContent = message;
  throw error;
});
