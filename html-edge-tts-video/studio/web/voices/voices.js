const $ = selector => document.querySelector(selector);

const els = {
  textInput: $('#textInput'),
  charCount: $('#charCount'),
  clearTextButton: $('#clearTextButton'),
  insertExampleButton: $('#insertExampleButton'),
  providerSelect: $('#providerSelect'),
  providerHint: $('#providerHint'),
  voiceSelect: $('#voiceSelect'),
  rateInput: $('#rateInput'),
  rateValue: $('#rateValue'),
  pitchInput: $('#pitchInput'),
  pitchValue: $('#pitchValue'),
  formatSelect: $('#formatSelect'),
  generateButton: $('#generateButton'),
  previewEmpty: $('#previewEmpty'),
  previewReady: $('#previewReady'),
  currentVoiceName: $('#currentVoiceName'),
  currentVoiceMeta: $('#currentVoiceMeta'),
  largePlayButton: $('#largePlayButton'),
  audioPlayer: $('#audioPlayer'),
  copyCommandButton: $('#copyCommandButton'),
  jobStatus: $('#jobStatus'),
  jobLog: $('#jobLog'),
  clearLogButton: $('#clearLogButton'),
  historyList: $('#historyList'),
  refreshHistoryButton: $('#refreshHistoryButton'),
  engineDot: $('#engineDot'),
  engineStatus: $('#engineStatus'),
  topStatus: $('#topStatus'),
  notification: $('#notification'),
  voiceGuideButton: $('#voiceGuideButton'), voiceGuideDialog: $('#voiceGuideDialog'),
};

const EXAMPLE_TEXT = `欢迎使用 TTS 语音试听工具。

选择语音服务和音色，调整语速和音调，然后生成本地试听。

文本会发送给你选择的语音服务，生成的音频文件保存在本地。

点击“生成试听”即可开始。`;

let appState = { providers: [], voices: [], history: [], manifest: {} };
let currentJobId = '';
let pollTimer = 0;
let seenJobLog = 0;
let logLines = [];
let notificationTimer = 0;

function renderIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function bindGuideDialog() {
  if (!els.voiceGuideButton || !els.voiceGuideDialog) return;
  els.voiceGuideButton.addEventListener('click', startVoiceTour);
  els.voiceGuideDialog.querySelector('[data-close-guide]')?.addEventListener('click', () => els.voiceGuideDialog.close());
  els.voiceGuideDialog.addEventListener('click', event => {
    if (event.target === els.voiceGuideDialog) els.voiceGuideDialog.close();
  });
}

function startVoiceTour() {
  const driverFactory = window.driver?.js?.driver;
  if (!driverFactory) {
    els.voiceGuideDialog.showModal();
    return;
  }
  const steps = [
    { element: '.text-panel', popover: { title: '1. 输入试听文本', description: '在此粘贴旁白。两三句话即可用于对比不同语音。', side: 'right', align: 'start' } },
    { element: '.settings-panel', popover: { title: '2. 选择语音和设置', description: '选择语音服务和音色后，微调语速和音调。', side: 'right', align: 'start' } },
    { element: '#generateButton', popover: { title: '3. 生成试听', description: '通过所选语音服务生成音频；准备就绪后播放器会自动加载。', side: 'right', align: 'center' } },
    { element: '.history-panel', popover: { title: '4. 对比结果', description: '最近的试听会保留在此，方便快速比较语音和设置。', side: 'left', align: 'start' } },
  ];
  driverFactory({
    showProgress: true,
    animate: true,
    allowClose: true,
    overlayOpacity: 0.42,
    nextBtnText: '下一步',
    prevBtnText: '上一步',
    doneBtnText: '完成',
    steps,
  }).drive();
}

function nowLabel() {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date());
}

function appendLog(message, tone = '') {
  logLines.push(`[${nowLabel()}]${tone ? ` ${tone}` : ''} ${message}`);
  logLines = logLines.slice(-200);
  els.jobLog.textContent = logLines.join('\n');
  els.jobLog.scrollTop = els.jobLog.scrollHeight;
}

function setJobStatus(label, status = '') {
  els.jobStatus.textContent = label;
  els.jobStatus.className = `job-status ${status}`.trim();
  if (els.topStatus) els.topStatus.textContent = label;
}

function notify(message, tone = '') {
  window.clearTimeout(notificationTimer);
  els.notification.textContent = message;
  els.notification.className = `notification show ${tone}`.trim();
  notificationTimer = window.setTimeout(() => {
    els.notification.className = 'notification';
  }, 3200);
}

async function api(path, options = {}) {
  const response = await fetch(window.appUrl(path), {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    },
  });
  const raw = await response.text();
  let data = {};
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    throw new Error(`API 返回了无效数据（${response.status}）`);
  }
  if (!response.ok) throw new Error(data.error || `API 请求失败（${response.status}）`);
  return data;
}

function signed(value, suffix) {
  const number = Number(value);
  return `${number >= 0 ? '+' : ''}${number}${suffix}`;
}

function updateInputs() {
  els.charCount.textContent = `${els.textInput.value.length} / 3000`;
  els.rateValue.textContent = signed(els.rateInput.value, '%');
  els.pitchValue.textContent = signed(els.pitchInput.value, 'Hz');
}

function providers() {
  return appState.providers.length
    ? appState.providers
    : [{ id: 'edge', label: 'Edge TTS', configured: true }];
}

function currentProvider() {
  return els.providerSelect.value || 'edge';
}

function voicesForProvider(provider) {
  const source = appState.voices;
  if (Array.isArray(source)) {
    const tagged = source.filter(voice => voice.provider === provider);
    return tagged.length || source.some(voice => voice.provider) ? tagged : source;
  }
  return Array.isArray(source?.[provider]) ? source[provider] : [];
}

function voiceInfo(id, provider = '') {
  const voices = provider ? voicesForProvider(provider) : Object.values(
    Array.isArray(appState.voices) ? { all: appState.voices } : appState.voices
  ).flat();
  return voices.find(voice => voice.id === id) || { id, label: id, locale: '', gender: '' };
}

function renderProviders() {
  const selected = els.providerSelect.value
    || appState.manifest?.samples?.[0]?.provider
    || 'edge';
  els.providerSelect.innerHTML = providers().map(provider =>
    `<option value="${escapeHtml(provider.id)}">${escapeHtml(provider.label || provider.id)}${provider.configured === false ? '（未配置）' : ''}</option>`
  ).join('');
  if ([...els.providerSelect.options].some(option => option.value === selected)) {
    els.providerSelect.value = selected;
  }
}

function renderProviderStatus() {
  const provider = providers().find(item => item.id === currentProvider());
  const configured = provider?.configured !== false;
  const label = provider?.label || currentProvider();
  els.engineStatus.textContent = configured ? `${label} 可用` : `${label} 未配置`;
  els.engineDot.classList.toggle('error', !configured);
  els.providerHint.textContent = provider?.message
    || (configured ? `将使用 ${label} 生成试听。` : `${label} 未配置。`);
  els.providerHint.classList.toggle('error', !configured);
  els.generateButton.disabled = !configured;
  els.generateButton.title = configured ? `使用 ${label} 生成试听` : 'Azure Speech 未配置，无法生成试听';
}

function renderVoices() {
  const voices = voicesForProvider(currentProvider());
  const latest = appState.manifest?.samples?.find(sample =>
    !sample.provider || sample.provider === currentProvider()
  );
  const selected = els.voiceSelect.value || latest?.voice || voices[0]?.id || '';
  els.voiceSelect.innerHTML = voices.map(voice => {
    const gender = voice.gender === 'Female' ? 'Female' : voice.gender === 'Male' ? 'Male' : '';
    return `<option value="${escapeHtml(voice.id)}">${escapeHtml(voice.id)} (${escapeHtml(voice.label)}${gender ? ` · ${gender}` : ''}${voice.preview ? ' · 预览' : ''})</option>`;
  }).join('');
  if ([...els.voiceSelect.options].some(option => option.value === selected)) {
    els.voiceSelect.value = selected;
  }
}

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

function formatDate(value) {
  if (!value) return '未知时间';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未知时间';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date);
}

function renderHistory() {
  if (!appState.history.length) {
    els.historyList.innerHTML = `
      <div class="history-empty">
            <div><i data-lucide="archive"></i><h3>暂无试听记录</h3><p>生成的试听音频将显示在这里。</p></div>
      </div>`;
    renderIcons();
    return;
  }
  els.historyList.innerHTML = appState.history.map((sample, index) => {
    const info = voiceInfo(sample.voice, sample.provider);
    const provider = providers().find(item => item.id === sample.provider);
    return `
      <article class="history-item">
        <div>
          <strong>${escapeHtml(info.label || sample.voice)}</strong>
          <span>${escapeHtml(provider?.label || sample.provider || 'TTS')} · ${escapeHtml(formatDate(sample.createdAt))} · ${escapeHtml(sample.rate || '+0%')} · ${escapeHtml(sample.pitch || '+0Hz')}</span>
        </div>
        <button type="button" data-history-index="${index}" title="播放"><i data-lucide="play"></i></button>
      </article>`;
  }).join('');
  renderIcons();
}

function setCurrentSample(sample, autoplay = false) {
  if (!sample?.audio) return;
  const info = voiceInfo(sample.voice, sample.provider);
  const provider = providers().find(item => item.id === sample.provider);
  els.audioPlayer.src = `${sample.audio}${sample.audio.includes('?') ? '&' : '?'}v=${Date.now()}`;
  els.largePlayButton.disabled = false;
  els.previewEmpty.hidden = true;
  els.previewReady.hidden = false;
  els.currentVoiceName.textContent = `${info.label || sample.voice} 试听已生成`;
  els.currentVoiceMeta.textContent = `${provider?.label || sample.provider || 'TTS'} · ${sample.voice} · ${sample.rate || '+0%'} · ${sample.pitch || '+0Hz'}`;
  if (autoplay) els.audioPlayer.play().catch(() => {});
}

async function loadState({ quiet = false, selectLatest = false } = {}) {
  if (!quiet) appendLog('GET /api/voice-preview');
  try {
    const data = await api('/api/voice-preview');
    appState = data;
    appState.providers = Array.isArray(data.providers) ? data.providers : [];
    appState.voices = Array.isArray(data.voices) || data.voices?.constructor === Object ? data.voices : [];
    appState.history = Array.isArray(data.history) ? data.history : [];
    appState.manifest = data.manifest || {};
    renderProviders();
    renderVoices();
    renderProviderStatus();
    renderHistory();
    if (selectLatest) setCurrentSample(appState.manifest.samples?.[0] || appState.history[0], true);
    else if (!els.audioPlayer.src) setCurrentSample(appState.manifest.samples?.[0] || appState.history[0]);
    const voiceCount = Array.isArray(appState.voices)
      ? appState.voices.length
      : Object.values(appState.voices).flat().length;
    if (!quiet) appendLog(`API complete: ${voiceCount} voices, ${appState.history.length} records`, 'OK');
  } catch (error) {
    els.engineStatus.textContent = '连接失败';
    els.engineDot.classList.add('error');
    appendLog(error.message, 'ERROR');
    notify(error.message, 'error');
  }
}

function setBusy(busy) {
  els.generateButton.disabled = busy;
  els.providerSelect.disabled = busy;
  els.voiceSelect.disabled = busy;
  els.rateInput.disabled = busy;
  els.pitchInput.disabled = busy;
  els.generateButton.querySelector('span').textContent = busy ? '生成中…' : '生成试听';
  if (!busy) renderProviderStatus();
}

function renderJob(job) {
  currentJobId = job.id;
  const labels = { queued: '排队中', running: '生成中', succeeded: '已生成', failed: '失败' };
  setJobStatus(labels[job.status] || job.status, job.status);
  const lines = Array.isArray(job.log) ? job.log : [];
  lines.slice(seenJobLog).forEach(line => appendLog(line));
  seenJobLog = lines.length;
  setBusy(job.status === 'queued' || job.status === 'running');
}

async function pollJob() {
  if (!currentJobId) return;
  try {
    const data = await api(`/api/jobs?id=${encodeURIComponent(currentJobId)}`);
    renderJob(data.job);
    if (['queued', 'running'].includes(data.job.status)) {
      pollTimer = window.setTimeout(pollJob, 700);
      return;
    }
    setBusy(false);
    if (data.job.status === 'succeeded') {
      appendLog('Preview generation API completed', 'OK');
      notify('试听已生成并加载到播放器', 'success');
      await loadState({ quiet: true, selectLatest: true });
    } else {
      appendLog('Preview generation failed; check the task output above', 'ERROR');
      notify('试听生成失败，请查看 API 日志', 'error');
    }
  } catch (error) {
    setBusy(false);
    setJobStatus('连接失败', 'failed');
    appendLog(error.message, 'ERROR');
    notify(error.message, 'error');
  }
}

async function generatePreview() {
  const text = els.textInput.value.trim();
  if (!text) {
    notify('请先输入要转换的文本', 'error');
    els.textInput.focus();
    return;
  }
  const provider = providers().find(item => item.id === currentProvider());
  if (provider?.configured === false) {
    notify(provider.message || 'Azure Speech 未配置，请导出凭据或改用 Edge TTS', 'error');
    renderProviderStatus();
    return;
  }
  window.clearTimeout(pollTimer);
  currentJobId = '';
  seenJobLog = 0;
  setBusy(true);
  setJobStatus('Submitting', 'running');
  const payload = {
    task: 'voice-preview',
    provider: currentProvider(),
    text,
    voice: els.voiceSelect.value,
    rate: signed(els.rateInput.value, '%'),
    pitch: signed(els.pitchInput.value, 'Hz'),
    format: els.formatSelect.value,
  };
  appendLog(`POST /api/jobs voice-preview · ${payload.provider} · ${payload.voice} · ${payload.rate} · ${payload.pitch}`);
  try {
    const data = await api('/api/jobs', { method: 'POST', body: JSON.stringify(payload) });
    renderJob(data.job);
    appendLog(`Task created: ${data.job.id}`, 'OK');
    pollTimer = window.setTimeout(pollJob, 400);
  } catch (error) {
    setBusy(false);
    setJobStatus('提交失败', 'failed');
    appendLog(error.message, 'ERROR');
    notify(error.message, 'error');
  }
}

function bindEvents() {
  els.textInput.addEventListener('input', updateInputs);
  els.rateInput.addEventListener('input', updateInputs);
  els.pitchInput.addEventListener('input', updateInputs);
  els.providerSelect.addEventListener('change', () => {
    renderVoices();
    renderProviderStatus();
  });
  els.clearTextButton.addEventListener('click', () => {
    els.textInput.value = '';
    updateInputs();
    els.textInput.focus();
  });
  els.insertExampleButton.addEventListener('click', () => {
    els.textInput.value = EXAMPLE_TEXT;
    updateInputs();
  });
  els.generateButton.addEventListener('click', generatePreview);
  els.refreshHistoryButton.addEventListener('click', () => loadState());
  els.clearLogButton.addEventListener('click', () => {
    logLines = [];
    els.jobLog.textContent = '等待 API 调用。';
  });
  els.copyCommandButton.addEventListener('click', async () => {
    await navigator.clipboard.writeText('python main.py voice-preview');
    notify('命令已复制', 'success');
  });
  els.largePlayButton.addEventListener('click', () => {
    if (els.audioPlayer.paused) els.audioPlayer.play().catch(() => {});
    else els.audioPlayer.pause();
  });
  els.historyList.addEventListener('click', event => {
    const button = event.target.closest('[data-history-index]');
    if (!button) return;
    setCurrentSample(appState.history[Number(button.dataset.historyIndex)], true);
  });
  els.audioPlayer.addEventListener('play', () => {
    els.largePlayButton.innerHTML = '<i data-lucide="pause"></i>';
    renderIcons();
  });
  els.audioPlayer.addEventListener('pause', () => {
    els.largePlayButton.innerHTML = '<i data-lucide="play"></i>';
    renderIcons();
  });
}

bindEvents();
bindGuideDialog();
updateInputs();
renderIcons();
setJobStatus('就绪');
loadState();
