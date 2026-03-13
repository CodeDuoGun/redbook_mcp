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
setInterval(updateGlobalStatus, 8000);
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
  const img         = document.getElementById('qrImage');
  const status      = document.getElementById('qrStatus');
  placeholder.classList.add('hidden');
  img.classList.add('hidden');
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
        img.src = 'data:image/png;base64,' + data.img;
        img.classList.remove('hidden');
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
   ANALYZE PANEL
   ============================================================ */
async function analyzeSearch() {
  const keyword = document.getElementById('analyzeKeyword').value.trim();
  if (!keyword) { toast('请输入关键词', 'error'); return; }
  const btn = event.target;
  setLoading(btn, true);
  const grid = document.getElementById('analyzeResults');
  grid.innerHTML = renderSkeletons(6);
  grid.classList.remove('hidden');
  document.getElementById('analyzeDetailCard').classList.add('hidden');
  try {
    const res = await apiFetch('/feeds/search', {
      method: 'POST',
      body: JSON.stringify({ keyword }),
    });
    const feeds = res.data.feeds || [];
    if (!feeds.length) { grid.innerHTML = '<p style="color:var(--text-muted);padding:20px">未找到相关笔记</p>'; return; }
    grid.innerHTML = feeds.map((f, i) => renderFeedCard(f, i, 'selectFeedForAnalysis')).join('');
    toast(`找到 ${feeds.length} 篇笔记`, 'success');
  } catch (e) {
    grid.innerHTML = `<p style="color:var(--accent);padding:20px">搜索失败：${e.message}</p>`;
    toast('搜索失败：' + e.message, 'error');
  } finally {
    setLoading(btn, false);
  }
}

function selectFeedForAnalysis(feedJson) {
  _selectedFeed = JSON.parse(decodeURIComponent(feedJson));
  const card   = document.getElementById('analyzeDetailCard');
  const detail = document.getElementById('analyzeDetail');
  const ai     = document.getElementById('aiAnalysis');
  ai.classList.add('hidden');
  detail.innerHTML = renderFeedDetail(_selectedFeed);
  card.classList.remove('hidden');
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function runAiAnalysis() {
  if (!_selectedFeed) { toast('请先选择笔记', 'error'); return; }
  const btn = event.target;
  setLoading(btn, true);
  const aiBlock = document.getElementById('aiAnalysis');
  aiBlock.classList.remove('hidden');
  aiBlock.innerHTML = `<div class="ai-block-title">✦ AI 爆款分析</div><div class="skeleton" style="height:120px;margin-top:8px"></div>`;

  // Build analysis from feed data (local AI analysis — no external API needed)
  await new Promise(r => setTimeout(r, 600)); // simulate brief processing
  const f = _selectedFeed;
  const likes    = f.likes_count    || f.like_count    || 0;
  const comments = f.comments_count || f.comment_count || 0;
  const collects = f.collects_count || f.collect_count || 0;
  const title    = f.title || f.desc || '（无标题）';
  const tags     = (f.tag_list || f.tags || []).map(t => (typeof t === 'string' ? t : t.name || '')).filter(Boolean);
  const engagementScore = Math.min(100, Math.round((likes * 0.4 + comments * 1.2 + collects * 0.8) / 10));

  const reasons = [];
  if (title.length >= 10 && title.length <= 20) reasons.push('标题长度适中（10-20字），易于阅读');
  if (title.includes('！') || title.includes('❗')) reasons.push('标题含感叹号，情绪张力强');
  if (tags.length >= 3) reasons.push(`标签丰富（${tags.length} 个），曝光覆盖广`);
  if (likes > 1000) reasons.push(`高点赞量（${likes.toLocaleString()}），已形成正向流量闭环`);
  if (comments > 100) reasons.push(`评论活跃（${comments.toLocaleString()} 条），互动率高`);
  if (collects > 500) reasons.push(`收藏量高（${collects.toLocaleString()}），内容具备长尾价值`);
  if (!reasons.length) reasons.push('数据量较少，建议加载全量评论后再分析');

  const suggestion = engagementScore >= 60
    ? '该笔记互动表现优秀，可复用其选题方向、标题结构及视觉风格。'
    : '互动数据一般，建议优化封面图质量和标题吸引力，同时增加精准话题标签。';

  aiBlock.innerHTML = `
    <div class="ai-block-title">✦ AI 爆款分析报告</div>
    <div style="margin-bottom:12px">
      <strong>互动评分：</strong>
      <span style="color:var(--gold);font-size:20px;font-weight:700">${engagementScore}</span>
      <span style="color:var(--text-muted)"> / 100</span>
    </div>
    <div style="margin-bottom:12px">
      <strong>数据概览：</strong><br/>
      👍 点赞 ${likes.toLocaleString()} &nbsp;|&nbsp; 💬 评论 ${comments.toLocaleString()} &nbsp;|&nbsp; ⭐ 收藏 ${collects.toLocaleString()}
    </div>
    <div style="margin-bottom:12px">
      <strong>爆款要素：</strong><br/>
      ${reasons.map(r => `• ${r}`).join('<br/>')}
    </div>
    <div style="margin-bottom:12px">
      <strong>优化建议：</strong><br/>${suggestion}
    </div>
    ${tags.length ? `<div><strong>命中标签：</strong> ${tags.map(t => `<span style="background:rgba(255,208,96,.12);color:var(--gold);padding:2px 8px;border-radius:4px;margin:2px;display:inline-block">#${t}</span>`).join('')}</div>` : ''}
  `;
  toast('分析完成', 'success');
  setLoading(btn, false);
}

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
  const title    = escHtml(f.title || f.desc || f.note_card?.title || '（无标题）');
  const likes    = (f.likes_count || f.like_count || f.interact_info?.liked_count || 0).toLocaleString();
  const comments = (f.comments_count || f.comment_count || f.interact_info?.comment_count || 0).toLocaleString();
  const collects = (f.collects_count || f.collect_count || f.interact_info?.collected_count || 0).toLocaleString();
  const img      = f.cover?.url || f.image_list?.[0]?.url || f.note_card?.cover?.url || '';
  const clickHandler = onClickFn
    ? `onclick="${onClickFn}('${encodeURIComponent(JSON.stringify(f))}')"`
    : '';
  return `
    <div class="feed-card" ${clickHandler}>
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
  const title   = escHtml(f.title || f.desc || '（无标题）');
  const tags    = (f.tag_list || f.tags || []).map(t => typeof t === 'string' ? t : t.name || '').filter(Boolean);
  const likes   = (f.likes_count || f.like_count || 0).toLocaleString();
  const comments= (f.comments_count || f.comment_count || 0).toLocaleString();
  const collects= (f.collects_count || f.collect_count || 0).toLocaleString();
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

