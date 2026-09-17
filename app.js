const form = document.getElementById('request-form');
const userIdInput = document.getElementById('user-id');
const actorNameInput = document.getElementById('actor-name');
const yearInput = document.getElementById('year');
const preview = document.getElementById('workflow-input-preview');
const copyButton = document.getElementById('copy-inputs');
const statusPill = document.getElementById('status-pill');
const statusMessage = document.getElementById('status-message');
const summary = document.getElementById('summary');
const warnings = document.getElementById('warnings');
const errorPanel = document.getElementById('error-panel');
const eventsBody = document.getElementById('events-body');

const summaryFields = {
  userId: document.getElementById('summary-user-id'),
  actorName: document.getElementById('summary-actor-name'),
  year: document.getElementById('summary-year'),
  total: document.getElementById('summary-total'),
  attended: document.getElementById('summary-attended'),
  rate: document.getElementById('summary-rate'),
};

function updatePreview() {
  const payload = {
    user_id: userIdInput.value.trim(),
    actor_name: actorNameInput.value.trim(),
    year: yearInput.value.trim(),
  };
  preview.textContent = JSON.stringify(payload, null, 2);
}

async function copyPreview() {
  try {
    await navigator.clipboard.writeText(preview.textContent || '');
    copyButton.textContent = '已复制';
    window.setTimeout(() => {
      copyButton.textContent = '复制 workflow 输入';
    }, 1500);
  } catch (error) {
    copyButton.textContent = '复制失败';
    window.setTimeout(() => {
      copyButton.textContent = '复制 workflow 输入';
    }, 1500);
  }
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

function hydrateForm(result) {
  if (!userIdInput.value && result.user_id) userIdInput.value = result.user_id;
  if (!actorNameInput.value && result.requested_actor_name) actorNameInput.value = result.requested_actor_name;
  if (!yearInput.value && result.year) yearInput.value = String(result.year);
  updatePreview();
}

async function loadLatestResult() {
  try {
    const response = await fetch(`./data/latest-result.json?ts=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    hydrateForm(result);
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
      statusMessage.textContent = '最近一次分析失败，请检查错误信息并重新运行工作流。';
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

form.addEventListener('input', updatePreview);
copyButton.addEventListener('click', copyPreview);
updatePreview();
void loadLatestResult();
