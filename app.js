const form = document.getElementById('request-form');
const userIdInput = document.getElementById('user-id');
const actorNameInput = document.getElementById('actor-name');
const yearInput = document.getElementById('year');
const openRequestButton = document.getElementById('open-request');
const requestHint = document.getElementById('request-hint');
const statusPill = document.getElementById('status-pill');
const statusMessage = document.getElementById('status-message');
const summary = document.getElementById('summary');
const warnings = document.getElementById('warnings');
const errorPanel = document.getElementById('error-panel');
const eventsBody = document.getElementById('events-body');
const issueBaseUrl = 'https://github.com/wangdeze/eventernote-attendance/issues/new';

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
  return '';
}

function buildIssueUrl(payload) {
  const title = `[analysis-request] ${payload.user_id} / ${payload.actor_name} / ${payload.year}`;
  const body = [
    '<!-- eventernote-attendance-request -->',
    `user_id: ${payload.user_id}`,
    `actor_name: ${payload.actor_name}`,
    `year: ${payload.year}`,
    '',
    '> 请不要修改以上三行参数；提交 issue 后会自动触发分析 workflow。',
  ].join('\n');
  const url = new URL(issueBaseUrl);
  url.searchParams.set('title', title);
  url.searchParams.set('body', body);
  return url.toString();
}

function syncRequestState() {
  const payload = getRequestPayload();
  const error = getRequestError(payload);
  openRequestButton.disabled = Boolean(error);
  requestHint.textContent = error || '将打开 GitHub issue 页面；提交 issue 后会自动运行分析。';
  if (error) {
    openRequestButton.removeAttribute('data-href');
    return;
  }
  openRequestButton.dataset.href = buildIssueUrl(payload);
}

function setStatus(kind, text) {
  statusPill.className = 'pill';
  if (kind) {
    statusPill.classList.add(kind);
  }
  statusPill.textContent = text;
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
      link.rel = 'noreferrer';
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

function toSafeUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return '';
  try {
    const url = new URL(value, window.location.origin);
    return ['http:', 'https:'].includes(url.protocol) ? url.toString() : '';
  } catch (error) {
    return '';
  }
}

function renderSummary(result) {
  summaryFields.userId.textContent = result.user_id || '-';
  summaryFields.actorName.textContent = result.actor_name || '-';
  summaryFields.year.textContent = result.year ?? '-';
  summaryFields.total.textContent = result.total_actor_events ?? 0;
  summaryFields.attended.textContent = result.attended_events ?? 0;
  const rate = typeof result.attendance_rate === 'number'
    ? `${(result.attendance_rate * 100).toFixed(2)}%`
    : '-';
  summaryFields.rate.textContent = rate;
  summary.classList.remove('hidden');
}

async function loadLatestResult() {
  try {
    const response = await fetch(`./data/latest-result.json?ts=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    renderWarnings(result.warnings || []);
    renderEvents(result.events || []);

    if (result.status === 'success') {
      setStatus('success', '成功');
      statusMessage.textContent = `最后更新时间：${result.generated_at || '未知'}`;
      errorPanel.classList.add('hidden');
      renderSummary(result);
      return;
    }

    if (result.status === 'error') {
      setStatus('error', '失败');
      statusMessage.textContent = '最近一次分析失败，请检查错误信息并重新提交分析请求。';
      summary.classList.add('hidden');
      errorPanel.textContent = result.error?.message || '未知错误';
      errorPanel.classList.remove('hidden');
      return;
    }

    setStatus('', '未运行');
    statusMessage.textContent = result.message || '还没有可展示的结果。';
    summary.classList.add('hidden');
    errorPanel.classList.add('hidden');
  } catch (error) {
    setStatus('error', '读取失败');
    statusMessage.textContent = '无法读取最新结果 JSON，请确认 GitHub Pages 已发布并且 data/latest-result.json 存在。';
    summary.classList.add('hidden');
    errorPanel.textContent = error instanceof Error ? error.message : '未知错误';
    errorPanel.classList.remove('hidden');
  }
}

form.addEventListener('input', syncRequestState);
form.addEventListener('submit', (event) => {
  event.preventDefault();
  const url = openRequestButton.dataset.href;
  if (!url) {
    syncRequestState();
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
});
syncRequestState();
void loadLatestResult();
