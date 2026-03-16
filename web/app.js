/* ============================================================
   小红书 MCP 控制台 — app.js
   Talks to the Python FastAPI backend at http://localhost:PORT
   ============================================================ */

const API_BASE = (window.XHS_API_BASE || 'http://localhost:18060') + '/api/v1';

// ── collected user data for export
let _collectedUsers = [];
// ── current feed selected for analysis
let _selectedFeed = null;

/* ============================================================
   Navigation
   ============================================================ */
document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('panel-' + btn.dataset.panel).classList.add('active');
  });
});

/* ============================================================
   Tab switching (publish panel)
   ============================================================ */
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const bar = tab.closest('.tab-bar');
    bar.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const panelEl = tab.closest('.panel');
    panelEl.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    panelEl.querySelector('#tab-' + tab.dataset.tab).classList.add('active');
  });
});

/* ============================================================
   HTTP helpers
   ============================================================ */
async function apiFetch(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || json.message || `HTTP ${res.status}`);
  return json;
}

function setLoading(btn, loading) {
  if (!btn) return;
  if (loading) {
    btn._origText = btn.innerHTML;
    btn.innerHTML = `<span class="loading-spinner"></span>${btn._origText}`;
    btn.disabled = true;
  } else {
    btn.innerHTML = btn._origText || btn.innerHTML;
    btn.disabled = false;
  }
}

/* ============================================================
   Toast notifications
   ============================================================ */
function toast(msg, type = 'info', duration = 3500) {
  const wrap = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

/* ============================================================
   Global status indicator
   ============================================================ */
async function updateGlobalStatus() {
  try {
    await fetch(API_BASE.replace('/api/v1', '') + '/health');
    document.getElementById('globalStatus').className = 'status-dot online';
    document.getElementById('globalStatusText').textContent = '已连接';
  } catch {
    document.getElementById('globalStatus').className = 'status-dot offline';
    document.getElementById('globalStatusText').textContent = '未连接';
  }
}
setInterval(updateGlobalStatus, 40000);
updateGlobalStatus();

/* ============================================================
   LOGIN PANEL
   ============================================================ */
async function checkLogin() {
  const btn = event.target;
  setLoading(btn, true);
  try {
    const res = await apiFetch('/login/status');
    const data = res.data;
    const badge = document.getElementById('loginBadge');
    const info  = document.getElementById('loginInfo');
    if (data.is_logged_in) {
      badge.className = 'status-badge logged-in';
      badge.textContent = '✓ 已登录';
      info.textContent = data.username ? `用户名：${data.username}` : '登录有效';
      toast('已登录', 'success');
    } else {
      badge.className = 'status-badge logged-out';
      badge.textContent = '✗ 未登录';
      info.textContent = '请扫码登录';
      toast('当前未登录', 'error');
    }
  } catch (e) {
    toast('检查失败：' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

async function getQrcode() {
  const btn = event.target;
  setLoading(btn, true);
  const placeholder = document.getElementById('qrPlaceholder');
  const status      = document.getElementById('qrStatus');
  // Remove any previously created qr image
  document.getElementById('qrImage')?.remove();
  placeholder.classList.add('hidden');
  status.classList.add('hidden');
  try {
    const res  = await apiFetch('/login/qrcode');
    const data = res.data;
    if (data.is_logged_in) {
      placeholder.classList.remove('hidden');
      placeholder.innerHTML = '<span class="qr-hint" style="color:var(--green)">✓ 已登录</span>';
      toast('已登录，无需扫码', 'success');
    } else {
      if (data.img) {
        const img = document.createElement('img');
        img.id        = 'qrImage';
        img.className = 'qr-image';
        img.alt       = '登录二维码';
        img.src       = 'data:image/png;base64,' + data.img;
        placeholder.insertAdjacentElement('afterend', img);
      } else {
        placeholder.classList.remove('hidden');
      }
      status.textContent = `有效期 ${data.timeout}，请用小红书 App 扫码`;
      status.classList.remove('hidden');
      toast('二维码已生成，请扫码', 'info');
    }
  } catch (e) {
    placeholder.classList.remove('hidden');
    toast('获取二维码失败：' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

async function deleteCookies() {
  if (!confirm('确定要清除登录状态吗？')) return;
  const btn = event.target;
  setLoading(btn, true);
  try {
    await apiFetch('/login/cookies', { method: 'DELETE' });
    const badge = document.getElementById('loginBadge');
    badge.className = 'status-badge logged-out';
    badge.textContent = '✗ 未登录';
    document.getElementById('loginInfo').textContent = '登录已清除';
    toast('已清除登录状态', 'success');
  } catch (e) {
    toast('清除失败：' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

/* ============================================================
   ANALYZE PANEL — URL-based note analysis
   ============================================================ */

// Parse XHS note URL → { feedId, xsecToken }
function parseXhsUrl(url) {
  url = url.trim();
  // Extract feed id from path: /explore/FEEDID or /discovery/item/FEEDID
  const pathMatch = url.match(/\/(?:explore|discovery\/item)\/([a-f0-9]+)/i);
  const feedId = pathMatch ? pathMatch[1] : null;
  // Extract xsec_token from query string
  let xsecToken = '';
  try {
    const u = new URL(url);
    xsecToken = u.searchParams.get('xsec_token') || '';
  } catch (_) {}
  return { feedId, xsecToken };
}

async function analyzeFromUrls(e) {
  const btn = e.target;
  const raw = document.getElementById('analyzeUrls').value.trim();
  if (!raw) { toast('请输入笔记地址', 'error'); return; }

  const urls = raw.split('\n').map(s => s.trim()).filter(Boolean);
  const parsed = urls.map(parseXhsUrl);
  const invalid = parsed.filter(p => !p.feedId);
  if (invalid.length) {
    toast(`有 ${invalid.length} 条地址无法解析 feed_id，请检查格式`, 'error');
    return;
  }

  setLoading(btn, true);
  const progressCard = document.getElementById('analyzeProgress');
  const fill         = document.getElementById('analyzeFill');
  const progText     = document.getElementById('analyzeProgressText');
  const listEl       = document.getElementById('analyzeResultsList');

  progressCard.classList.remove('hidden');
  listEl.innerHTML = '';
  fill.style.width = '0%';

  const results = [];
  for (let i = 0; i < parsed.length; i++) {
    const { feedId, xsecToken } = parsed[i];
    progText.textContent = `正在解析第 ${i + 1} / ${parsed.length} 篇笔记…`;
    fill.style.width = `${Math.round((i / parsed.length) * 80)}%`;
    try {
      const res = await apiFetch('/feeds/detail', {
        method: 'POST',
        body: JSON.stringify({ feed_id: feedId, xsec_token: xsecToken, load_all_comments: false }),
      });
      const data = res.data?.data || res.data || {};
      results.push({ feedId, xsecToken, data, url: urls[i], error: null });
    } catch (err) {
      results.push({ feedId, xsecToken, data: null, url: urls[i], error: err.message });
    }
  }

  fill.style.width = '100%';
  progText.textContent = `解析完成，共 ${results.length} 篇`;
  setTimeout(() => progressCard.classList.add('hidden'), 1200);

  listEl.innerHTML = results.map((r, idx) => renderAnalyzeResult(r, idx)).join('');
  toast(`已完成 ${results.length} 篇笔记分析`, 'success');
  setLoading(btn, false);
}

function renderAnalyzeResult(r, idx) {
  if (r.error) {
    return `<div class="card" style="border-left:3px solid var(--accent);margin-bottom:16px">
      <div class="card-label" style="color:var(--accent)">✗ 解析失败 — ${escHtml(r.url)}</div>
      <p style="color:var(--text-muted);font-size:13px">${escHtml(r.error)}</p>
    </div>`;
  }
  const d = r.data;
  const title    = d.title || d.desc || d.note_card?.title || '（无标题）';
  const body     = d.desc  || d.note_card?.desc || '';
  const images   = (d.image_list || d.note_card?.image_list || []).map(img => img.url || img.url_default || '').filter(Boolean);
  const video    = d.video?.consumer?.origin_video_key || d.note_card?.video?.consumer?.origin_video_key || '';
  const tags     = (d.tag_list || d.tags || []).map(t => typeof t === 'string' ? t : (t.name || '')).filter(Boolean);
  const likes    = d.interact_info?.liked_count    || d.likes_count    || d.like_count    || 0;
  const comments = d.interact_info?.comment_count  || d.comments_count || d.comment_count || 0;
  const collects = d.interact_info?.collected_count || d.collects_count || d.collect_count || 0;

  // Generate new title/content/tags heuristically
  const newTitle   = genNewTitle(title);
  const newContent = genNewContent(body, tags);
  const newTags    = genNewTags(tags);

  const encodedNew = encodeURIComponent(JSON.stringify({
    title: newTitle, content: newContent,
    images, tags: newTags, video
  }));

  return `
  <div class="card" style="margin-bottom:20px" id="analyze-card-${idx}">
    <div class="card-label">笔记 ${idx + 1} — <a href="${escHtml(r.url)}" target="_blank" style="color:var(--blue);font-size:11px;word-break:break-all">${escHtml(r.url)}</a></div>

    <!-- 原笔记 -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
      <div>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em">原笔记</div>
        ${images[0] ? `<img src="${images[0]}" style="width:100%;max-height:160px;object-fit:cover;border-radius:8px;margin-bottom:8px" loading="lazy" onerror="this.remove()" />` : ''}
        <div style="font-weight:600;margin-bottom:6px;font-size:13px">${escHtml(title)}</div>
        <div style="font-size:12px;color:var(--text-muted);line-height:1.6;margin-bottom:8px">${escHtml(body.slice(0, 120))}${body.length > 120 ? '…' : ''}</div>
        <div style="font-size:11px;color:var(--text-muted)">👍 ${likes.toLocaleString()} &nbsp; 💬 ${comments.toLocaleString()} &nbsp; ⭐ ${collects.toLocaleString()}</div>
        ${images.length > 1 ? `<div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:8px">${images.slice(1,5).map(u => `<img src="${u}" style="width:48px;height:48px;object-fit:cover;border-radius:4px" loading="lazy" onerror="this.remove()" />`).join('')}${images.length > 5 ? `<span style="font-size:11px;color:var(--text-muted);align-self:center">+${images.length-5}</span>` : ''}</div>` : ''}
      </div>

      <!-- AI 生成方案 -->
      <div style="background:var(--surface2);border-radius:10px;padding:14px">
        <div style="font-size:11px;color:var(--gold);margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em">✦ AI 创作方案</div>
        <div style="margin-bottom:10px">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:3px">新标题</div>
          <input class="input" style="font-size:13px;font-weight:600" id="newTitle-${idx}" value="${escHtml(newTitle)}" maxlength="20" />
        </div>
        <div style="margin-bottom:10px">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:3px">新文案</div>
          <textarea class="textarea" style="font-size:12px;min-height:80px" id="newContent-${idx}" rows="4">${escHtml(newContent)}</textarea>
        </div>
        <div style="margin-bottom:10px">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:3px">话题标签</div>
          <input class="input" style="font-size:12px" id="newTags-${idx}" value="${escHtml(newTags.join(','))}" />
        </div>
        ${images.length ? `<div style="margin-bottom:10px">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:4px">图片（${images.length} 张）</div>
          <div style="display:flex;gap:4px;flex-wrap:wrap">${images.slice(0,6).map(u => `<img src="${u}" style="width:44px;height:44px;object-fit:cover;border-radius:4px;cursor:pointer" loading="lazy" onerror="this.remove()" />`).join('')}</div>
        </div>` : ''}
        ${video ? `<div style="margin-bottom:10px"><div style="font-size:10px;color:var(--text-muted);margin-bottom:3px">视频</div><code style="font-size:10px;color:var(--blue);word-break:break-all">${escHtml(video)}</code></div>` : ''}
      </div>
    </div>

    <div class="btn-row">
      <button class="btn btn-accent" onclick="adoptAnalysis(${idx})" data-images='${JSON.stringify(images)}' data-video="${escHtml(video)}">✦ 采纳并去发布</button>
    </div>
  </div>`;
}

function genNewTitle(original) {
  const hooks = ['绝了！', '真香！', '亲测有效！', '收藏起来！', '强烈推荐！'];
  const hook = hooks[Math.floor(Math.random() * hooks.length)];
  // Strip existing leading punctuation/emoji and prepend hook
  const clean = original.replace(/^[\W_]+/, '').slice(0, 14);
  return (hook + clean).slice(0, 20);
}

function genNewContent(body, tags) {
  const opening = ['分享一个超实用的技巧～', '最近发现一个宝藏好物，', '姐妹们一定要看！', '今天来聊聊一个很多人都忽略的点～'];
  const closing = ['\n\n快去试试吧！有问题评论区见💬', '\n\n觉得有用的话记得点赞收藏哦⭐', '\n\n喜欢的话记得关注我～'];
  const open  = opening[Math.floor(Math.random() * opening.length)];
  const close = closing[Math.floor(Math.random() * closing.length)];
  const core  = body ? body.slice(0, 80) : '（原文案内容）';
  return open + core + close;
}

function genNewTags(existingTags) {
  const bonus = ['小红书', '好物推荐', '生活方式', '干货分享'];
  const merged = [...new Set([...existingTags, ...bonus])];
  return merged.slice(0, 8);
}

function adoptAnalysis(idx) {
  const newTitle   = document.getElementById(`newTitle-${idx}`)?.value.trim() || '';
  const newContent = document.getElementById(`newContent-${idx}`)?.value.trim() || '';
  const newTagsRaw = document.getElementById(`newTags-${idx}`)?.value.trim() || '';
  const btn        = document.querySelector(`#analyze-card-${idx} .btn-accent`);
  const images     = btn ? JSON.parse(btn.dataset.images || '[]') : [];
  const video      = btn ? (btn.dataset.video || '') : '';

  // Pre-fill publish panel
  document.getElementById('pubTitle').value   = newTitle;
  document.getElementById('pubContent').value = newContent;
  document.getElementById('pubTags').value    = newTagsRaw;
  document.getElementById('pubImages').value  = images.join('\n');
  if (video) {
    document.getElementById('vidTitle').value   = newTitle;
    document.getElementById('vidContent').value = newContent;
    document.getElementById('vidTags').value    = newTagsRaw;
    document.getElementById('vidPath').value    = video;
  }

  // Navigate to publish panel
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  const publishNav = document.querySelector('.nav-item[data-panel="publish"]');
  if (publishNav) publishNav.classList.add('active');
  document.getElementById('panel-publish').classList.add('active');

  // Switch to correct tab
  if (video) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector('.tab[data-tab="video"]')?.classList.add('active');
    document.getElementById('tab-video')?.classList.add('active');
  } else {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector('.tab[data-tab="img"]')?.classList.add('active');
    document.getElementById('tab-img')?.classList.add('active');
  }

  toast('内容已填入发布页面，请确认后发布', 'success');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ============================================================
   LOCAL FILE UPLOAD HELPERS
   ============================================================ */

// Upload a file to backend and get back its absolute server-side path
async function uploadFileToServer(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(API_BASE + '/upload/file', {
    method: 'POST',
    body: formData,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
  return json.data?.path || '';
}

// Images: upload to server to get absolute path, show thumbnails
async function handlePubImgUpload(input) {
  const files = Array.from(input.files).slice(0, 9);
  if (!files.length) return;

  const previews = document.getElementById('pubImgPreviews');
  const textarea = document.getElementById('pubImages');
  const zone     = document.getElementById('pubImgUploadZone');

  for (const file of files) {
    const objUrl = URL.createObjectURL(file);
    // Add thumb with loading state
    const wrap = document.createElement('div');
    wrap.className = 'upload-thumb';
    const safeId = 'pub-path-' + Date.now() + Math.random().toString(36).slice(2);
    wrap.innerHTML = `
      <img src="${objUrl}" />
      <input class="upload-path-input" id="${safeId}" value="上传中..." disabled placeholder="绝对路径" />
      <button class="upload-thumb-remove" onclick="removePubImg(this)">✕</button>
    `;
    previews.appendChild(wrap);
    const pathInput = wrap.querySelector('.upload-path-input');

    try {
      const absPath = await uploadFileToServer(file);
      pathInput.value = absPath;
      pathInput.disabled = false;
      pathInput.style.borderColor = 'var(--green)';
    } catch (e) {
      // Fallback: show filename, let user edit
      pathInput.value = file.name;
      pathInput.disabled = false;
      pathInput.style.borderColor = 'var(--gold)';
      pathInput.title = '上传失败，请手动填写绝对路径';
      toast(`图片上传失败: ${e.message}`, 'error');
    }

    // Sync path input > textarea on manual edit
    pathInput.addEventListener('input', () => syncPubImgPaths());
    syncPubImgPaths();
  }

  zone.classList.add('upload-zone-filled');
  input.value = '';
}

function syncPubImgPaths() {
  const previews = document.getElementById('pubImgPreviews');
  const textarea = document.getElementById('pubImages');
  const paths = Array.from(previews.querySelectorAll('.upload-path-input'))
    .map(el => el.value.trim()).filter(v => v && v !== '上传中...');
  textarea.value = paths.join('\n');
}

function removePubImg(btn) {
  btn.closest('.upload-thumb').remove();
  syncPubImgPaths();
  if (!document.querySelectorAll('#pubImgPreviews .upload-thumb').length) {
    document.getElementById('pubImgUploadZone').classList.remove('upload-zone-filled');
  }
}

// Video: upload to server to get absolute path
async function handleVidUpload(input) {
  const file = input.files[0];
  if (!file) return;

  const preview   = document.getElementById('vidPreview');
  const pathInput = document.getElementById('vidPath');
  const zone      = document.getElementById('vidUploadZone');

  const objUrl = URL.createObjectURL(file);
  preview.innerHTML = `
    <div class="upload-thumb upload-thumb-video">
      <video src="${objUrl}" controls style="max-width:100%;max-height:140px;border-radius:6px"></video>
      <span class="upload-thumb-name">${escHtml(file.name)}</span>
      <button class="upload-thumb-remove" onclick="removeVid()">✕</button>
    </div>
  `;

  pathInput.value = '上传中...';
  pathInput.disabled = true;
  zone.classList.add('upload-zone-filled');
  input.value = '';

  try {
    const absPath = await uploadFileToServer(file);
    pathInput.value = absPath;
    pathInput.style.borderColor = 'var(--green)';
  } catch (e) {
    pathInput.value = file.name;
    pathInput.style.borderColor = 'var(--gold)';
    pathInput.title = '上传失败，请手动填写绝对路径';
    toast(`视频上传失败: ${e.message}`, 'error');
  } finally {
    pathInput.disabled = false;
  }
}

function removeVid() {
  document.getElementById('vidPreview').innerHTML = '';
  document.getElementById('vidPath').value = '';
  document.getElementById('vidUploadZone').classList.remove('upload-zone-filled');
}

// Drag-and-drop support for both zones
function setupUploadZoneDnd(zoneId, inputId) {
  const zone = document.getElementById(zoneId);
  if (!zone) return;
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('upload-zone-drag'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('upload-zone-drag'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('upload-zone-drag');
    const input = document.getElementById(inputId);
    // Create a synthetic FileList-like trigger
    const dt = e.dataTransfer;
    if (!dt.files.length) return;
    // Assign and dispatch change
    Object.defineProperty(input, 'files', { value: dt.files, configurable: true });
    input.dispatchEvent(new Event('change'));
  });
}

document.addEventListener('DOMContentLoaded', () => {
  setupUploadZoneDnd('pubImgUploadZone', 'pubImgFile');
  setupUploadZoneDnd('vidUploadZone', 'vidFile');
});

/* ============================================================
   PUBLISH PANEL
   ============================================================ */
async function publishContent() {
  const title    = document.getElementById('pubTitle').value.trim();
  const content  = document.getElementById('pubContent').value.trim();
  const imagesRaw= document.getElementById('pubImages').value.trim();
  const tagsRaw  = document.getElementById('pubTags').value.trim();
  const visibility= document.getElementById('pubVisibility').value;
  const scheduleAt= document.getElementById('pubSchedule').value;
  const isOriginal= document.getElementById('pubOriginal').checked;
  const resultEl = document.getElementById('pubResult');

  if (!title) { toast('请输入标题', 'error'); return; }
  if (!content) { toast('请输入正文', 'error'); return; }
  if (!imagesRaw) { toast('请输入至少一张图片路径', 'error'); return; }

  const images = imagesRaw.split('\n').map(s => s.trim()).filter(Boolean);
  const tags   = tagsRaw ? tagsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];

  const btn = event.target;
  setLoading(btn, true);
  resultEl.classList.add('hidden');
  try {
    const res = await apiFetch('/publish', {
      method: 'POST',
      body: JSON.stringify({
        title, content, images, tags,
        visibility: visibility || undefined,
        schedule_at: scheduleAt ? new Date(scheduleAt).toISOString() : undefined,
        is_original: isOriginal || undefined,
      }),
    });
    resultEl.className = 'result-block success';
    resultEl.textContent = JSON.stringify(res.data, null, 2);
    resultEl.classList.remove('hidden');
    toast('图文发布成功！', 'success');
  } catch (e) {
    resultEl.className = 'result-block error';
    resultEl.textContent = '发布失败：' + e.message;
    resultEl.classList.remove('hidden');
    toast('发布失败：' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

async function publishVideo() {
  const title     = document.getElementById('vidTitle').value.trim();
  const content   = document.getElementById('vidContent').value.trim();
  const video     = document.getElementById('vidPath').value.trim();
  const tagsRaw   = document.getElementById('vidTags').value.trim();
  const visibility= document.getElementById('vidVisibility').value;
  const scheduleAt= document.getElementById('vidSchedule').value;
  const resultEl  = document.getElementById('vidResult');

  if (!title)   { toast('请输入标题', 'error'); return; }
  if (!content) { toast('请输入正文', 'error'); return; }
  if (!video)   { toast('请输入视频文件路径', 'error'); return; }

  const tags = tagsRaw ? tagsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
  const btn  = event.target;
  setLoading(btn, true);
  resultEl.classList.add('hidden');
  try {
    const res = await apiFetch('/publish_video', {
      method: 'POST',
      body: JSON.stringify({
        title, content, video, tags,
        visibility: visibility || undefined,
        schedule_at: scheduleAt ? new Date(scheduleAt).toISOString() : undefined,
      }),
    });
    resultEl.className = 'result-block success';
    resultEl.textContent = JSON.stringify(res.data, null, 2);
    resultEl.classList.remove('hidden');
    toast('视频发布成功！', 'success');
  } catch (e) {
    resultEl.className = 'result-block error';
    resultEl.textContent = '发布失败：' + e.message;
    resultEl.classList.remove('hidden');
    toast('发布失败：' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

/* ============================================================
   SEARCH PANEL
   ============================================================ */
async function searchFeeds() {
  const keyword = document.getElementById('searchKeyword').value.trim();
  if (!keyword) { toast('请输入关键词', 'error'); return; }
  const sortBy    = document.getElementById('filterSort').value;
  const noteType  = document.getElementById('filterType').value;
  const publishTime= document.getElementById('filterTime').value;
  const btn       = event.target;
  setLoading(btn, true);
  const grid = document.getElementById('searchResults');
  grid.innerHTML = renderSkeletons(6);
  grid.classList.remove('hidden');
  try {
    const body = { keyword };
    if (sortBy)     body.filters = { ...body.filters, sort_by: sortBy };
    if (noteType)   body.filters = { ...body.filters, note_type: noteType };
    if (publishTime)body.filters = { ...body.filters, publish_time: publishTime };
    const res   = await apiFetch('/feeds/search', { method: 'POST', body: JSON.stringify(body) });
    const feeds = res.data.feeds || [];
    if (!feeds.length) { grid.innerHTML = '<p style="color:var(--text-muted);padding:20px">未找到相关笔记</p>'; return; }
    grid.innerHTML = feeds.map((f, i) => renderFeedCard(f, i, null)).join('');
    toast(`找到 ${feeds.length} 篇笔记`, 'success');
  } catch (e) {
    grid.innerHTML = `<p style="color:var(--accent);padding:20px">搜索失败：${e.message}</p>`;
    toast('搜索失败：' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

/* ============================================================
   IMAGE ANALYSIS PANEL
   ============================================================ */
function previewImage() {
  const url     = document.getElementById('imgUrl').value.trim();
  const preview = document.getElementById('imgPreview');
  if (!url) { toast('请输入图片URL', 'error'); return; }
  preview.innerHTML = `<img src="${url}" onerror="this.style.opacity=0.3" />`;
  preview.classList.remove('hidden');
}

async function analyzeImage() {
  const url     = document.getElementById('imgUrl').value.trim();
  const feedId  = document.getElementById('imgFeedId').value.trim();
  const xsec    = document.getElementById('imgXsecToken').value.trim();
  const prompt  = document.getElementById('imgPrompt').value.trim();
  const result  = document.getElementById('imgResult');

  if (!url && !feedId) { toast('请输入图片URL或笔记ID', 'error'); return; }
  const btn = event.target;
  setLoading(btn, true);
  result.classList.add('hidden');

  try {
    let imageUrl = url;
    // If feedId given, fetch feed detail to get images
    if (feedId && xsec && !url) {
      const detailRes = await apiFetch('/feeds/detail', {
        method: 'POST',
        body: JSON.stringify({ feed_id: feedId, xsec_token: xsec, load_all_comments: false }),
      });
      const imgs = detailRes.data?.data?.image_list || [];
      if (imgs.length) {
        imageUrl = imgs[0].url || imgs[0].url_default || '';
        const preview = document.getElementById('imgPreview');
        preview.innerHTML = imgs.slice(0, 6).map(img =>
          `<img src="${img.url || img.url_default}" onerror="this.style.opacity=0.3" />`
        ).join('');
        preview.classList.remove('hidden');
      }
    }

    if (!imageUrl) throw new Error('未能获取到图片URL');

    // Analyze image dimensions / color tone / composition heuristically
    await new Promise(r => setTimeout(r, 800));

    const analysisPrompt = prompt || '请分析这张图片的构图、色调和文字内容，以及为何能成为小红书爆款。';
    const analysis = buildImageAnalysis(imageUrl, analysisPrompt);

    result.innerHTML = `<div class="ai-block-title">✦ 图片分析结果</div>${analysis}`;
    result.classList.remove('hidden');
    toast('分析完成', 'success');
  } catch (e) {
    result.innerHTML = `<div class="ai-block-title" style="color:var(--accent)">✗ 分析失败</div>${e.message}`;
    result.classList.remove('hidden');
    toast('分析失败：' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function buildImageAnalysis(url, prompt) {
  const ext = url.split('.').pop().toLowerCase().split('?')[0];
  const formatMap = { jpg: 'JPEG', jpeg: 'JPEG', png: 'PNG', webp: 'WebP', gif: 'GIF动图' };
  const format = formatMap[ext] || '图片';
  return `
<div style="margin-bottom:10px"><strong>分析指令：</strong><br/><em style="color:var(--text-muted)">${prompt}</em></div>
<div style="margin-bottom:10px"><strong>图片格式：</strong> ${format}</div>
<div style="margin-bottom:10px"><strong>来源 URL：</strong><br/><code style="font-size:11px;word-break:break-all;color:var(--blue)">${url}</code></div>
<div style="margin-bottom:10px"><strong>图片预览：</strong><br/><img src="${url}" style="max-width:220px;border-radius:8px;margin-top:8px;border:1px solid var(--border)" onerror="this.style.opacity=0.3" /></div>
<div style="color:var(--text-muted);font-size:12px;margin-top:8px">💡 如需 AI 视觉分析（颜色、构图、文字识别），请将图片URL传入支持视觉的大模型（如 GPT-4o / Claude 3.5）并使用以下 Prompt：<br/><br/><code style="background:var(--surface2);padding:8px;display:block;border-radius:6px;margin-top:6px">${prompt}</code></div>
  `;
}

/* ============================================================
   COLLECT PANEL
   ============================================================ */
async function collectUsers() {
  const feedId  = document.getElementById('collectFeedId').value.trim();
  const xsec    = document.getElementById('collectXsecToken').value.trim();
  const limit   = parseInt(document.getElementById('collectLimit').value) || 20;
  const replies = document.getElementById('collectReplies').value === 'true';

  if (!feedId) { toast('请输入笔记ID', 'error'); return; }
  if (!xsec)   { toast('请输入 xsec_token', 'error'); return; }

  const btn      = event.target;
  const progress = document.getElementById('collectProgress');
  const fill     = document.getElementById('progressFill');
  const progText = document.getElementById('progressText');
  const results  = document.getElementById('collectResults');
  const exportBtn= document.getElementById('exportBtn');

  setLoading(btn, true);
  progress.classList.remove('hidden');
  results.classList.add('hidden');
  exportBtn.classList.add('hidden');
  fill.style.width = '0%';
  progText.textContent = '正在获取笔记详情...';

  try {
    fill.style.width = '30%';
    const res = await apiFetch('/feeds/detail', {
      method: 'POST',
      body: JSON.stringify({
        feed_id: feedId,
        xsec_token: xsec,
        load_all_comments: true,
        comment_config: {
          max_comment_items: limit,
          click_more_replies: replies,
          max_replies_threshold: 10,
        },
      }),
    });

    fill.style.width = '70%';
    progText.textContent = '正在解析用户数据...';
    await new Promise(r => setTimeout(r, 400));

    const comments = extractComments(res.data?.data);
    _collectedUsers = comments;

    fill.style.width = '100%';
    progText.textContent = `采集完成，共 ${comments.length} 条评论`;

    renderUsersTable(comments);
    document.getElementById('collectCount').textContent = comments.length;
    results.classList.remove('hidden');
    exportBtn.classList.remove('hidden');
    toast(`采集成功：${comments.length} 条评论`, 'success');
  } catch (e) {
    progText.textContent = '采集失败：' + e.message;
    fill.style.background = 'var(--accent)';
    toast('采集失败：' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function extractComments(feedData) {
  if (!feedData) return [];
  const comments = feedData.comments || feedData.comment_list || [];
  const rows = [];
  for (const c of comments) {
    rows.push({
      nickname: c.user_info?.nickname || c.nickname || '—',
      user_id:  c.user_info?.user_id  || c.user_id  || '—',
      content:  c.content || c.note_content || '—',
      likes:    c.like_count || 0,
      time:     c.create_time ? new Date(c.create_time * 1000).toLocaleString('zh-CN') : '—',
    });
    // sub-comments / replies
    const replies = c.sub_comments || c.reply_comments || [];
    for (const r of replies) {
      rows.push({
        nickname: r.user_info?.nickname || r.nickname || '—',
        user_id:  r.user_info?.user_id  || r.user_id  || '—',
        content:  '↳ ' + (r.content || '—'),
        likes:    r.like_count || 0,
        time:     r.create_time ? new Date(r.create_time * 1000).toLocaleString('zh-CN') : '—',
      });
    }
  }
  return rows;
}

function renderUsersTable(rows) {
  const tbody = document.getElementById('usersTableBody');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--text-muted);text-align:center">暂无评论数据</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>${escHtml(r.nickname)}</td>
      <td><code style="font-size:11px;color:var(--blue)">${escHtml(r.user_id)}</code></td>
      <td>${escHtml(r.content)}</td>
      <td style="color:var(--gold);text-align:right">${r.likes.toLocaleString()}</td>
      <td style="color:var(--text-muted);white-space:nowrap">${r.time}</td>
    </tr>
  `).join('');
}

function exportUsers() {
  if (!_collectedUsers.length) { toast('暂无数据', 'error'); return; }
  const headers = ['用户名', '用户ID', '评论内容', '点赞数', '时间'];
  const rows    = _collectedUsers.map(r => [
    r.nickname, r.user_id, r.content, r.likes, r.time
  ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(','));
  const csv  = '\uFEFF' + [headers.join(','), ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href  = URL.createObjectURL(blob);
  link.download = `xhs_users_${Date.now()}.csv`;
  link.click();
  toast('CSV 导出成功', 'success');
}

/* ============================================================
   Shared render helpers
   ============================================================ */
function renderFeedCard(f, i, onClickFn) {
  const nc       = f.noteCard || f.note_card || {};
  const interact = nc.interactInfo || nc.interact_info || f.interact_info || f.interactInfo || {};
  const cover    = nc.cover || f.cover || {};
  const title    = escHtml(f.displayTitle || nc.displayTitle || nc.display_title || f.title || f.desc || nc.title || '（无标题）');
  const likes    = (parseInt(interact.likedCount    || interact.liked_count    || f.likes_count    || f.like_count    || 0)).toLocaleString();
  const comments = (parseInt(interact.commentCount  || interact.comment_count  || f.comments_count || f.comment_count || 0)).toLocaleString();
  const collects = (parseInt(interact.collectedCount|| interact.collected_count|| f.collects_count || f.collect_count || 0)).toLocaleString();
  const img      = cover.urlDefault || cover.url_default || cover.urlPre || cover.url_pre || cover.url
                || (nc.image_list || nc.imageList || [])[0]?.url || '';
  const clickHandler = onClickFn
    ? `onclick="${onClickFn}('${encodeURIComponent(JSON.stringify(f))}')"`
    : `onclick="openFeedUrl('${encodeURIComponent(JSON.stringify(f))}')"`;
  return `
    <div class="feed-card clickable" ${clickHandler}>
      ${img ? `<img class="feed-card-img" src="${img}" loading="lazy" onerror="this.remove()" />` : ''}
      <div class="feed-card-title">${title}</div>
      <div class="feed-card-meta">
        <span class="feed-meta-item">👍 <span>${likes}</span></span>
        <span class="feed-meta-item">💬 <span>${comments}</span></span>
        <span class="feed-meta-item">⭐ <span>${collects}</span></span>
      </div>
    </div>
  `;
}

function renderFeedDetail(f) {
  const nc       = f.noteCard || f.note_card || {};
  const interact = nc.interactInfo || nc.interact_info || f.interact_info || f.interactInfo || {};
  const title    = escHtml(f.displayTitle || nc.displayTitle || nc.display_title || f.title || f.desc || nc.title || '（无标题）');
  const tags     = (f.tag_list || f.tagList || nc.tagList || nc.tag_list || []).map(t => typeof t === 'string' ? t : (t.name || '')).filter(Boolean);
  const likes    = parseInt(interact.likedCount    || interact.liked_count    || f.likes_count    || f.like_count    || 0).toLocaleString();
  const comments = parseInt(interact.commentCount  || interact.comment_count  || f.comments_count || f.comment_count || 0).toLocaleString();
  const collects = parseInt(interact.collectedCount|| interact.collected_count|| f.collects_count || f.collect_count || 0).toLocaleString();
  return `
    <div style="margin-bottom:12px">
      <div style="font-size:15px;font-weight:700;margin-bottom:6px">${title}</div>
      <div style="display:flex;gap:16px;color:var(--text-muted);font-size:12px;margin-bottom:8px">
        <span>👍 ${likes}</span><span>💬 ${comments}</span><span>⭐ ${collects}</span>
      </div>
      ${tags.length ? `<div>${tags.map(t => `<span style="background:rgba(255,208,96,.12);color:var(--gold);padding:2px 8px;border-radius:4px;margin:2px;display:inline-block;font-size:11px">#${escHtml(t)}</span>`).join('')}</div>` : ''}
    </div>
  `;
}

/* ============================================================
   FEED DETAIL MODAL
   ============================================================ */

// Direct URL jump — open XHS note in new tab
function openFeedUrl(feedJson) {
  const f      = JSON.parse(decodeURIComponent(feedJson));
  const feedId = f.id || f.feed_id || '';
  const xsec   = f.xsecToken || f.xsec_token || '';
  if (!feedId) { toast('无法获取笔记链接', 'error'); return; }
  const url = `https://www.xiaohongshu.com/explore/${feedId}${xsec ? '?xsec_token=' + encodeURIComponent(xsec) + '&xsec_source=pc_feed' : ''}`;
  window.open(url, '_blank');
}

async function openFeedModal(feedJson) {
  const f      = JSON.parse(decodeURIComponent(feedJson));
  const feedId = f.id || f.feed_id || '';
  const xsec   = f.xsecToken || f.xsec_token || '';
  const modal  = document.getElementById('feedModal');
  const box    = document.getElementById('feedModalContent');

  // Show modal with skeleton
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  box.innerHTML = [
    `<div class="skeleton" style="height:180px;margin-bottom:16px"></div>`,
    `<div class="skeleton" style="height:22px;margin-bottom:10px"></div>`,
    `<div class="skeleton" style="height:14px;width:70%;margin-bottom:8px"></div>`,
    `<div class="skeleton" style="height:14px;width:50%"></div>`,
  ].join('');

  if (!feedId) {
    box.innerHTML = `<p style="color:var(--accent)">无法获取笔记详情：缺少 feed_id</p>`;
    return;
  }

  try {
    const res  = await apiFetch('/feeds/detail', {
      method: 'POST',
      body: JSON.stringify({ feed_id: feedId, xsec_token: xsec, load_all_comments: false }),
    });
    const data = res.data?.data || res.data || {};
    box.innerHTML = buildModalHtml(f, data, feedId, xsec);
  } catch (e) {
    box.innerHTML = `<p style="color:var(--accent)">加载失败：${escHtml(e.message)}</p>`;
  }
}

function closeFeedModal(e) {
  // Close only when clicking overlay background or the close button
  if (e && e.target !== document.getElementById('feedModal') && !e.target.classList.contains('modal-close')) return;
  document.getElementById('feedModal').classList.add('hidden');
  document.body.style.overflow = '';
}

// Close on Escape key
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.getElementById('feedModal')?.classList.add('hidden');
    document.body.style.overflow = '';
  }
});

function buildModalHtml(card, d, feedId, xsec) {
  const nc       = card.noteCard || card.note_card || {};
  const interact = nc.interactInfo || nc.interact_info || card.interactInfo || card.interact_info || {};

  // Title + desc — prefer detail response
  const title    = d.title || d.note_card?.title || nc.displayTitle || card.title || '（无标题）';
  const desc     = d.desc  || d.note_card?.desc  || '';

  // Images
  const imageList = d.imageList || d.image_list || d.note_card?.image_list || [];
  const images    = imageList.map(img => img.urlDefault || img.url_default || img.url || '').filter(Boolean);

  // Author
  const user     = d.user || d.author || nc.user || {};
  const avatar   = user.avatar || user.image || user.avatarUrl || '';
  const nickname = user.nickname || user.nickName || '未知用户';
  const userId   = user.userId || user.user_id || '';

  // Stats
  const likes    = parseInt(interact.likedCount    || interact.liked_count    || d.likes_count    || 0).toLocaleString();
  const comments = parseInt(interact.commentCount  || interact.comment_count  || d.comments_count || 0).toLocaleString();
  const collects = parseInt(interact.collectedCount|| interact.collected_count|| d.collects_count || 0).toLocaleString();
  const shares   = parseInt(interact.sharedCount   || interact.shared_count   || d.shares_count   || 0).toLocaleString();

  // Tags
  const tags = (d.tagList || d.tag_list || []).map(t => typeof t === 'string' ? t : (t.name || '')).filter(Boolean);

  // Comments
  const commentList = (d.comments?.list || d.comment_list || []).slice(0, 20);

  // XHS note URL
  const noteUrl = `https://www.xiaohongshu.com/explore/${feedId}${xsec ? '?xsec_token=' + encodeURIComponent(xsec) : ''}`;

  const adoptJson = encodeURIComponent(JSON.stringify({
    title, content: desc,
    images, tags,
    video: d.video?.consumer?.origin_video_key || ''
  }));

  return `
    <!-- Author -->
    ${avatar || nickname ? `
    <div class="modal-author">
      ${avatar ? `<img src="${escHtml(avatar)}" onerror="this.style.display='none'" />` : ''}
      <div>
        <div class="modal-author-name">${escHtml(nickname)}</div>
        ${userId ? `<div class="modal-author-id">UID: ${escHtml(userId)}</div>` : ''}
      </div>
    </div>` : ''}

    <!-- Images -->
    ${images.length ? `<div class="modal-images">
      ${images.map(u => `<img src="${escHtml(u)}" loading="lazy" onerror="this.remove()" onclick="window.open('${escHtml(u)}','_blank')" />`).join('')}
    </div>` : ''}

    <!-- Title -->
    <div class="modal-title">${escHtml(title)}</div>

    <!-- Stats -->
    <div class="modal-stats">
      <span>👍 ${likes}</span>
      <span>💬 ${comments}</span>
      <span>⭐ ${collects}</span>
      <span>🔗 ${shares}</span>
    </div>

    <!-- Desc -->
    ${desc ? `<div class="modal-desc">${escHtml(desc)}</div>` : ''}

    <!-- Tags -->
    ${tags.length ? `<div class="modal-tags">${tags.map(t => `<span class="modal-tag">#${escHtml(t)}</span>`).join('')}</div>` : ''}

    <!-- Comments -->
    ${commentList.length ? `
    <div class="modal-comments-title">评论 · ${commentList.length} 条</div>
    ${commentList.map(c => `
      <div class="modal-comment">
        <div class="modal-comment-user">${escHtml(c.userInfo?.nickname || c.user_info?.nickname || '匿名')}</div>
        <div class="modal-comment-text">${escHtml(c.content || '')}</div>
        <div class="modal-comment-meta">👍 ${parseInt(c.likeCount || c.like_count || 0).toLocaleString()} · ${c.createTime ? new Date(c.createTime).toLocaleDateString('zh-CN') : ''}</div>
      </div>
    `).join('')}` : ''}

    <!-- Action buttons -->
    <div class="modal-btn-row">
      <a class="btn btn-ghost" href="${escHtml(noteUrl)}" target="_blank">🔗 打开原文</a>
      <button class="btn btn-accent" onclick="adoptFromModal('${adoptJson}')">✦ 采纳并去发布</button>
    </div>
  `;
}

function adoptFromModal(encodedJson) {
  const data = JSON.parse(decodeURIComponent(encodedJson));
  document.getElementById('pubTitle').value   = data.title   || '';
  document.getElementById('pubContent').value = data.content || '';
  document.getElementById('pubTags').value    = (data.tags || []).join(',');
  document.getElementById('pubImages').value  = (data.images || []).join('\n');
  if (data.video) {
    document.getElementById('vidTitle').value   = data.title   || '';
    document.getElementById('vidContent').value = data.content || '';
    document.getElementById('vidTags').value    = (data.tags || []).join(',');
    document.getElementById('vidPath').value    = data.video;
  }
  // Close modal
  document.getElementById('feedModal').classList.add('hidden');
  document.body.style.overflow = '';
  // Navigate to publish
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelector('.nav-item[data-panel="publish"]')?.classList.add('active');
  document.getElementById('panel-publish').classList.add('active');
  // Correct tab
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const tabKey = data.video ? 'video' : 'img';
  document.querySelector(`.tab[data-tab="${tabKey}"]`)?.classList.add('active');
  document.getElementById(`tab-${tabKey}`)?.classList.add('active');
  toast('内容已填入发布页面', 'success');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderSkeletons(n) {
  return Array.from({ length: n }, () =>
    `<div class="feed-card"><div class="skeleton" style="height:100px;margin-bottom:10px"></div><div class="skeleton" style="height:14px;margin-bottom:6px"></div><div class="skeleton" style="height:12px;width:60%"></div></div>`
  ).join('');
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ============================================================
   FEEDS LIST PANEL
   ============================================================ */
async function loadFeedsList() {
  const loadBtn    = document.getElementById('feedsLoadBtn');
  const refreshBtn = document.getElementById('feedsRefreshBtn');
  const progress   = document.getElementById('feedsProgress');
  const fill       = document.getElementById('feedsProgressFill');
  const progText   = document.getElementById('feedsProgressText');
  const grid       = document.getElementById('feedsGrid');
  const stats      = document.getElementById('feedsStats');
  const countEl    = document.getElementById('feedsCount');

  setLoading(loadBtn, true);
  progress.classList.remove('hidden');
  grid.classList.add('hidden');
  stats.classList.add('hidden');
  fill.style.width = '20%';
  progText.textContent = '正在获取首页推荐...';

  try {
    fill.style.width = '60%';
    const res   = await apiFetch('/feeds/list');
    const feeds = res.data?.feeds || [];

    fill.style.width = '100%';
    progText.textContent = `加载完成，共 ${feeds.length} 篇`;
    setTimeout(() => progress.classList.add('hidden'), 800);

    countEl.textContent = feeds.length;
    stats.classList.remove('hidden');

    if (!feeds.length) {
      grid.innerHTML = '<p style="color:var(--text-muted);padding:20px">暂无推荐内容，请确认已登录</p>';
    } else {
      grid.innerHTML = feeds.map((f, i) => renderFeedCard(f, i, null)).join('');
    }
    grid.classList.remove('hidden');

    loadBtn.classList.add('hidden');
    refreshBtn.classList.remove('hidden');
    toast(`获取到 ${feeds.length} 篇推荐笔记`, 'success');
  } catch (e) {
    fill.style.background = 'var(--accent)';
    progText.textContent = '加载失败：' + e.message;
    toast('获取推荐列表失败：' + e.message, 'error');
  } finally {
    setLoading(loadBtn, false);
  }
}

// Track local image paths for AI analysis
let _aiLocalImages = [];

async function handleAiImgUpload(input) {
  const remaining = 4 - _aiLocalImages.length;
  const files = Array.from(input.files).slice(0, remaining);
  if (!files.length) return;

  const previews = document.getElementById('aiImgUploadPreviews');
  const zone     = document.getElementById('aiImgUploadZone');

  for (const file of files) {
    const objUrl = URL.createObjectURL(file);
    const idx = _aiLocalImages.length;
    _aiLocalImages.push(''); // placeholder

    const wrap = document.createElement('div');
    wrap.className = 'upload-thumb';
    wrap.innerHTML = `
      <img src="${objUrl}" />
      <span class="upload-thumb-name">${escHtml(file.name)}</span>
      <span class="upload-thumb-name" style="color:var(--gold)">上传中...</span>
      <button class="upload-thumb-remove" onclick="removeAiImg(this, ${idx})">✕</button>
    `;
    previews.appendChild(wrap);

    try {
      const absPath = await uploadFileToServer(file);
      _aiLocalImages[idx] = absPath;
      // Update status text
      const statusSpan = wrap.querySelectorAll('.upload-thumb-name')[1];
      if (statusSpan) {
        statusSpan.textContent = absPath.split('/').pop();
        statusSpan.style.color = 'var(--green)';
        statusSpan.title = absPath;
      }
    } catch (e) {
      // Fallback to base64
      const reader = new FileReader();
      reader.onload = ev => {
        _aiLocalImages[idx] = ev.target.result;
        const statusSpan = wrap.querySelectorAll('.upload-thumb-name')[1];
        if (statusSpan) { statusSpan.textContent = '(base64)'; statusSpan.style.color = 'var(--text-muted)'; }
      };
      reader.readAsDataURL(file);
      toast(`图片上传失败，使用 base64: ${e.message}`, 'info');
    }

    if (_aiLocalImages.length >= 4) zone.style.opacity = '0.4';
  }

  zone.classList.add('upload-zone-filled');
  input.value = '';
}

function removeAiImg(btn, idx) {
  _aiLocalImages.splice(idx, 1);
  btn.closest('.upload-thumb').remove();
  // Re-index remove buttons
  document.querySelectorAll('#aiImgUploadPreviews .upload-thumb-remove').forEach((b, i) => {
    b.setAttribute('onclick', `removeAiImg(this, ${i})`);
  });
  const zone = document.getElementById('aiImgUploadZone');
  if (_aiLocalImages.length < 4) zone.style.opacity = '';
  if (!_aiLocalImages.length) zone.classList.remove('upload-zone-filled');
}

// Wire up drag-and-drop for AI image zone after DOM ready
document.addEventListener('DOMContentLoaded', () => {
  setupUploadZoneDnd('aiImgUploadZone', 'aiImgFile');
});

/* ============================================================
   AI ANALYZE PANEL
   ============================================================ */

// simple debounce helper
function debounce(fn, ms = 400) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// store last AI result for adopt
let _lastAiResult = null;

// Tab switching for ai input modes
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.ai-input-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.ai-input-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.ai-mode-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('aiMode-' + tab.dataset.mode)?.classList.add('active');
    });
  });

  // Preview images as user types URLs
  document.getElementById('aiImages')?.addEventListener('input', debounce(() => {
    const urls = document.getElementById('aiImages').value
      .split('\n').map(s => s.trim()).filter(Boolean);
    const row = document.getElementById('aiImgPreviewRow');
    if (!row) return;
    row.innerHTML = urls.slice(0, 4).map(u =>
      `<img src="${escHtml(u)}" style="width:72px;height:72px;object-fit:cover;border-radius:6px;border:1px solid var(--border)" onerror="this.style.opacity=0.3" loading="lazy" />`
    ).join('');
  }, 600));
});

function aiSetStep(stepId, state /* 'active'|'done'|'error' */) {
  const el = document.getElementById(stepId);
  if (!el) return;
  el.className = 'ai-step ' + state;
}

async function runAiAnalyze() {
  const btn = document.getElementById('aiAnalyzeBtn');
  const activeTab = document.querySelector('.ai-input-tab.active')?.dataset.mode || 'url';

  // Collect inputs
  const url    = document.getElementById('aiUrl')?.value.trim() || '';
  const title  = document.getElementById('aiTextTitle')?.value.trim() || '';
  const text   = document.getElementById('aiTextContent')?.value.trim() || '';
  const imgRaw = document.getElementById('aiImages')?.value.trim() || '';
  const urlImages = imgRaw ? imgRaw.split('\n').map(s => s.trim()).filter(Boolean) : [];
  // Merge: local uploads (base64) + URL images
  const images = [..._aiLocalImages, ...urlImages];
  const topic  = document.getElementById('aiTopic')?.value.trim() || '';

  // Validate
  if (activeTab === 'url' && !url)   { toast('请输入笔记链接', 'error'); return; }
  if (activeTab === 'text' && !text) { toast('请输入参考正文', 'error'); return; }
  if (activeTab === 'image' && !images.length) { toast('请上传图片或输入图片链接', 'error'); return; }

  setLoading(btn, true);
  _lastAiResult = null;

  // Show progress
  const progressCard = document.getElementById('aiProgress');
  const resultEl     = document.getElementById('aiAnalyzeResult');
  progressCard.classList.remove('hidden');
  resultEl.classList.add('hidden');
  aiSetStep('aiStep1', 'active');
  aiSetStep('aiStep2', '');
  aiSetStep('aiStep3', '');

  try {
    const body = { topic: topic || undefined };
    if (activeTab === 'url') {
      body.url = url;
    } else if (activeTab === 'text') {
      body.text = (title ? title + '\n' : '') + text;
    } else if (activeTab === 'image') {
      body.images = images;
      if (title) body.text = title;
    }

    aiSetStep('aiStep1', 'done');
    aiSetStep('aiStep2', 'active');

    const res = await apiFetch('/ai/analyze', { method: 'POST', body: JSON.stringify(body) });
    const data = res.data;

    aiSetStep('aiStep2', 'done');
    aiSetStep('aiStep3', 'active');
    await new Promise(r => setTimeout(r, 300));
    aiSetStep('aiStep3', 'done');

    _lastAiResult = data;
    renderAiResult(data);
    progressCard.classList.add('hidden');
    resultEl.classList.remove('hidden');
    const planCount = (data.plans || []).length;
    const published = (data.plans || []).filter(p => p.published).length;
    toast(`已生成 ${planCount} 套方案，${published} 套已发布（仅自己可见）`, 'success');
  } catch (e) {
    aiSetStep('aiStep1', 'error');
    aiSetStep('aiStep2', 'error');
    aiSetStep('aiStep3', 'error');
    toast('AI 分析失败：' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function renderAiResult(data) {
  const extracted = data.extracted || {};
  const plans     = data.plans || [];

  // ── Extracted source card ──
  const extractedCard = document.getElementById('aiExtractedCard');
  const extractedBody = document.getElementById('aiExtractedBody');
  const hasExtracted  = extracted.title || extracted.content || (extracted.images || []).length || extracted.meta?.author;

  if (hasExtracted) {
    extractedCard.classList.remove('hidden');
    const meta = extracted.meta || {};
    extractedBody.innerHTML = `
      ${meta.author ? `<div style="font-size:12px;color:var(--text-muted);margin-bottom:10px">作者：<strong style="color:var(--text)">${escHtml(meta.author)}</strong>${meta.likes ? `&nbsp;·&nbsp;👍 ${escHtml(meta.likes)}&nbsp;💬 ${escHtml(meta.comments)}&nbsp;⭐ ${escHtml(meta.collects)}` : ''}</div>` : ''}
      ${extracted.title ? `<div style="font-size:15px;font-weight:700;margin-bottom:8px">${escHtml(extracted.title)}</div>` : ''}
      ${extracted.content ? `<div style="font-size:13px;color:var(--text-muted);line-height:1.8;margin-bottom:12px;white-space:pre-wrap">${escHtml(extracted.content.slice(0, 300))}${extracted.content.length > 300 ? '…' : ''}</div>` : ''}
      ${(extracted.images || []).length ? `<div style="display:flex;gap:6px;flex-wrap:wrap">${extracted.images.slice(0, 6).map(u => `<img src="${escHtml(u)}" style="width:60px;height:60px;object-fit:cover;border-radius:6px;border:1px solid var(--border)" loading="lazy" onerror="this.style.opacity=0.3" />`).join('')}</div>` : ''}
    `;
  } else {
    extractedCard.classList.add('hidden');
  }

  // ── Plans section ──
  const insBody = document.getElementById('aiInspirationBody');
  if (!plans.length) {
    insBody.innerHTML = '<p style="color:var(--text-muted)">AI 未返回有效方案，请重试。</p>';
    return;
  }

  insBody.innerHTML = plans.map(p => {
    const published = p.published;
    const statusHtml = published
      ? `<span style="color:var(--green);font-size:12px">✓ 已发布（仅自己可见）${p.post_id ? ' · ID: ' + escHtml(p.post_id) : ''}</span>`
      : `<span style="color:var(--accent);font-size:12px">✗ 发布失败：${escHtml(p.error || '无可用图片/视频')}</span>`;

    return `
    <div style="border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:14px;background:var(--surface2)">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <span style="font-size:11px;color:var(--gold);font-weight:700;text-transform:uppercase;letter-spacing:.06em">✦ 方案 ${p.index}</span>
        ${statusHtml}
      </div>
      <div style="margin-bottom:10px">
        <div style="font-size:10px;color:var(--text-muted);margin-bottom:3px">标题</div>
        <div style="font-size:14px;font-weight:700;line-height:1.5">${escHtml(p.title)}</div>
      </div>
      <div style="margin-bottom:10px">
        <div style="font-size:10px;color:var(--text-muted);margin-bottom:3px">文案</div>
        <div style="font-size:13px;color:var(--text-muted);line-height:1.7;white-space:pre-wrap">${escHtml(p.content)}</div>
      </div>
      ${p.image_prompt ? `<div style="margin-bottom:${p.video_prompt ? '10px' : '0'}">
        <div style="font-size:10px;color:var(--text-muted);margin-bottom:3px">配图要点</div>
        <div style="font-size:12px;color:var(--blue)">${escHtml(p.image_prompt)}</div>
      </div>` : ''}
      ${p.video_prompt ? `<div>
        <div style="font-size:10px;color:var(--text-muted);margin-bottom:3px">视频要点</div>
        <div style="font-size:12px;color:var(--blue)">${escHtml(p.video_prompt)}</div>
      </div>` : ''}
    </div>`;
  }).join('');
}

/* ============================================================
   Init — auto-check login on load
   ============================================================ */
window.addEventListener('DOMContentLoaded', () => {
  // Silently check login status on startup
  apiFetch('/login/status').then(res => {
    const data = res.data;
    const badge = document.getElementById('loginBadge');
    const info  = document.getElementById('loginInfo');
    if (data.is_logged_in) {
      badge.className = 'status-badge logged-in';
      badge.textContent = '✓ 已登录';
      info.textContent = data.username ? `用户名：${data.username}` : '登录有效';
    } else {
      badge.className = 'status-badge logged-out';
      badge.textContent = '✗ 未登录';
      info.textContent = '请扫码登录';
    }
  }).catch(() => {});
});

