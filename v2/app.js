const form = document.getElementById('request-form');
const userIdInput = document.getElementById('user-id');
const actorNameInput = document.getElementById('actor-name');
const yearInput = document.getElementById('year');
const runAnalysisButton = document.getElementById('run-analysis');
const apiHint = document.getElementById('api-hint');
const requestFeedback = document.getElementById('request-feedback');
const statusPill = document.getElementById('status-pill');
const statusMessage = document.getElementById('status-message');
const summary = document.getElementById('summary');
const warnings = document.getElementById('warnings');
const errorPanel = document.getElementById('error-panel');
const eventsBody = document.getElementById('events-body');
const runtimeConfigUrl = './data/runtime-config.json';

const defaultConfig = {
  analyze_api_url: '',
};

let runtimeConfig = { ...defaultConfig };

const summaryFields = {
  userId: document.getElementById('summary-user-id'),
  actorName: document.getElementById('summary-actor-name'),
  year: document.getElementById('summary-year'),
  total: document.getElementById('summary-total'),
  attended: document.getElementById('summary-attended'),
  rate: document.getElementById('summary-rate'),
};

function getRequestPayload() {
  return {
    user_id: userIdInput.value.trim(),
    actor_name: actorNameInput.value.trim(),
    year: yearInput.value.trim(),
  };
}

function getRequestError(payload) {
  if (!payload.user_id) return '请填写 Eventernote 用户 ID。';
  if (!payload.actor_name) return '请填写艺人名称。';
  if (!/^\d{4}$/.test(payload.year)) return '请填写 4 位年份。';
  const year = Number(payload.year);
  if (year < 2000 || year > 2100) return '请填写 2000-2100 之间的年份。';
  return '';
}

function normalizeRuntimeConfig(value) {
  if (!value || typeof value !== 'object') {
    return { ...defaultConfig };
  }

  return {
    analyze_api_url: typeof value.analyze_api_url === 'string' ? value.analyze_api_url.trim() : '',
  };
}

function resolveAnalyzeApiUrl() {
  const configured = runtimeConfig.analyze_api_url;
  if (configured) {
    return toSafeUrl(configured);
  }
  if (window.location.protocol === 'file:') {
    return 'http://127.0.0.1:8000/api/analyze';
  }
  return `${window.location.origin}/api/analyze`;
}

function setFeedback(kind, text) {
  requestFeedback.innerHTML = '';
  requestFeedback.className = 'request-feedback';
  if (kind) requestFeedback.classList.add(kind);
  const paragraph = document.createElement('p');
  paragraph.textContent = text;
  requestFeedback.appendChild(paragraph);
  requestFeedback.classList.remove('hidden');
}

function clearFeedback() {
  requestFeedback.innerHTML = '';
  requestFeedback.className = 'request-feedback hidden';
}

function setStatus(kind, text) {
  statusPill.className = 'pill';
  if (kind) statusPill.classList.add(kind);
  statusPill.textContent = text;
}

function syncRequestState() {
  const payload = getRequestPayload();
  const error = getRequestError(payload);
  runAnalysisButton.disabled = Boolean(error);
  apiHint.textContent = error || `当前分析接口：${resolveAnalyzeApiUrl() || '未配置'}`;
}

async function loadRuntimeConfig() {
  try {
    const response = await fetch(`${runtimeConfigUrl}?ts=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    runtimeConfig = normalizeRuntimeConfig(await response.json());
  } catch (error) {
    runtimeConfig = { ...defaultConfig };
  } finally {
    syncRequestState();
  }
}

function renderWarnings(items) {
  warnings.innerHTML = '';
  if (!items || items.length === 0) {
    warnings.classList.add('hidden');
    return;
  }
  items.forEach((warning) => {
    const item = document.createElement('li');
    item.textContent = warning;
    warnings.appendChild(item);
  });
  warnings.classList.remove('hidden');
}

function renderEvents(items) {
  eventsBody.innerHTML = '';
  if (!items || items.length === 0) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 4;
    cell.className = 'muted';
    cell.textContent = '当前结果没有活动明细。';
    row.appendChild(cell);
    eventsBody.appendChild(row);
    return;
  }

  items.forEach((event) => {
    const row = document.createElement('tr');
    const badgeClass = event.attended ? 'attended' : 'missed';
    const badgeText = event.attended ? '已出席' : '未出席';
    const statusCell = document.createElement('td');
    const statusBadge = document.createElement('span');
    statusBadge.className = `status-badge ${badgeClass}`;
    statusBadge.textContent = badgeText;
    statusCell.appendChild(statusBadge);

    const dateCell = document.createElement('td');
    dateCell.textContent = event.date ?? '-';

    const titleCell = document.createElement('td');
    const safeUrl = toSafeUrl(event.url);
    if (safeUrl) {
      const link = document.createElement('a');
      link.href = safeUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = event.title ?? '-';
      titleCell.appendChild(link);
    } else {
      titleCell.textContent = event.title ?? '-';
    }

    const venueCell = document.createElement('td');
    venueCell.textContent = event.venue ?? '-';

    row.append(statusCell, dateCell, titleCell, venueCell);
    eventsBody.appendChild(row);
  });
}

function renderSummary(result) {
  summaryFields.userId.textContent = result.user_id || '-';
  summaryFields.actorName.textContent = result.actor_name || '-';
  summaryFields.year.textContent = result.year ?? '-';
  summaryFields.total.textContent = result.total_actor_events ?? 0;
  summaryFields.attended.textContent = result.attended_events ?? 0;
  summaryFields.rate.textContent = typeof result.attendance_rate === 'number'
    ? `${(result.attendance_rate * 100).toFixed(2)}%`
    : '-';
  summary.classList.remove('hidden');
}

function renderResult(result) {
  renderWarnings(result.warnings || []);
  renderEvents(result.events || []);

  if (result.status === 'success') {
    setStatus('success', '成功');
    statusMessage.textContent = `分析完成：${result.generated_at || '未知时间'}`;
    errorPanel.classList.add('hidden');
    renderSummary(result);
    return;
  }

  setStatus('error', '失败');
  statusMessage.textContent = '分析执行失败，请检查错误信息。';
  summary.classList.add('hidden');
  errorPanel.textContent = result.error?.message || '未知错误';
  errorPanel.classList.remove('hidden');
}

async function submitAnalysis(payload) {
  const response = await fetch(resolveAnalyzeApiUrl(), {
    method: 'POST',
    headers: {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  const resultText = await response.text();
  let result = {};
  if (resultText) {
    try {
      result = JSON.parse(resultText);
    } catch (error) {
      result = {
        status: 'error',
        error: {
          message: `分析接口返回了非 JSON 响应（HTTP ${response.status}）。`,
        },
        warnings: [],
        events: [],
      };
    }
  }
  if (!response.ok) {
    return result;
  }
  return result;
}

function toSafeUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return '';
  try {
    const url = new URL(value, window.location.origin);
    return ['http:', 'https:'].includes(url.protocol) ? url.toString() : '';
  } catch (error) {
    return '';
  }
}

form.addEventListener('input', syncRequestState);
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  clearFeedback();

  const payload = getRequestPayload();
  const error = getRequestError(payload);
  if (error) {
    setFeedback('error', error);
    syncRequestState();
    return;
  }

  runAnalysisButton.disabled = true;
  runAnalysisButton.textContent = '分析中...';
  setStatus('', '分析中');
  statusMessage.textContent = '正在实时抓取并计算，请稍候。';
  errorPanel.classList.add('hidden');

  try {
    const result = await submitAnalysis(payload);
    renderResult(result);
    setFeedback(result.status === 'success' ? 'success' : 'error', result.status === 'success' ? '分析完成。' : '分析失败。');
  } catch (submitError) {
    setStatus('error', '请求失败');
    statusMessage.textContent = '无法连接分析接口，请检查配置。';
    errorPanel.textContent = submitError instanceof Error ? submitError.message : '未知错误';
    errorPanel.classList.remove('hidden');
    summary.classList.add('hidden');
    renderWarnings([]);
    renderEvents([]);
    setFeedback('error', '请求失败，请检查接口地址和网络连通性。');
  } finally {
    runAnalysisButton.textContent = '开始分析';
    syncRequestState();
  }
});

syncRequestState();
void loadRuntimeConfig();
