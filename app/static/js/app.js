const API = '';
let currentView = 'dashboard';
let currentPage = 1;
let selectedIds = new Set();
let langChartInstance = null;
let timelineChartInstance = null;
let currentTopic = '';

// Theming for charts
Chart.defaults.color = '#94A3B8';
Chart.defaults.font.family = "'Inter', sans-serif";

// Navigation
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', e => {
        e.preventDefault();
        const view = item.dataset.view;
        switchView(view);
    });
});

function switchView(view) {
    currentView = view;
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector(`.nav-item[data-view="${view}"]`).classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById(`view-${view}`).classList.add('active');
    selectedIds.clear();

    if (view === 'dashboard') loadDashboard();
    else if (view === 'all') { loadTopics(); loadProjects(); }
    else if (view === 'favorites') loadFavorites();
    else if (view === 'trending') loadTrending();
    else if (view === 'timeline') loadTimeline();
}

// API calls
async function api(path, opts = {}) {
    const resp = await fetch(API + path, opts);
    return resp.json();
}
async function apiPut(path) { return api(path, { method: 'PUT' }); }
async function apiPost(path) { return api(path, { method: 'POST' }); }

// Dashboard
async function loadDashboard() {
    const stats = await api('/api/stats');

    document.getElementById('stat-total').textContent = stats.total_projects;
    document.getElementById('stat-unviewed').textContent = stats.unviewed;
    document.getElementById('stat-favorites').textContent = stats.favorites;
    document.getElementById('stat-trending').textContent = stats.trending;
    document.getElementById('stat-spikes').textContent = stats.spikes;

    if (stats.last_fetch.time) {
        document.getElementById('last-fetch-time').textContent =
            new Date(stats.last_fetch.time).toLocaleString('zh-CN');
    }

    // Language chart (Chart.js)
    const ctxLang = document.getElementById('lang-chart').getContext('2d');
    if (langChartInstance) langChartInstance.destroy();
    
    langChartInstance = new Chart(ctxLang, {
        type: 'doughnut',
        data: {
            labels: stats.top_languages.map(l => l.language),
            datasets: [{
                data: stats.top_languages.map(l => l.count),
                backgroundColor: [
                    '#8B5CF6', '#3B82F6', '#10B981', '#F59E0B', '#EF4444',
                    '#EC4899', '#8B5CF6', '#6366F1', '#14B8A6', '#F97316'
                ],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: '#F8FAFC' } }
            },
            cutout: '70%'
        }
    });

    // Top projects
    const topData = await api('/api/projects?page_size=10&sort_by=stars');
    document.getElementById('top-projects').innerHTML = topData.projects.map(p =>
        renderProjectItem(p)
    ).join('');

    // Velocity Leaderboard
    const velocityData = await api('/api/projects/velocity');
    document.getElementById('velocity-list').innerHTML = velocityData
        .map((p, index) => `
            <div class="spike-item">
                <span style="font-size: 16px; font-weight: 800; color: ${index < 3 ? 'var(--orange)' : 'var(--text-dim)'}; width: 20px;">${index + 1}</span>
                <img src="${p.owner_avatar_url || 'https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png'}" style="width:24px; height:24px; border-radius:50%">
                <span class="name"><a href="${p.url}" target="_blank">${p.name}</a></span>
                <span class="growth"><i class="fas fa-arrow-trend-up"></i> +${p.star_growth_24h}</span>
            </div>
        `).join('');
}

// Topics
async function loadTopics() {
    const topics = await api('/api/topics');
    const container = document.getElementById('topic-cloud');
    container.innerHTML = topics.map(t => 
        `<span class="topic-tag ${currentTopic === t.topic ? 'active' : ''}" onclick="setTopic('${t.topic}')">${t.topic} <small>(${t.count})</small></span>`
    ).join('');
}

function setTopic(topic) {
    if (currentTopic === topic) currentTopic = ''; // toggle off
    else currentTopic = topic;
    loadTopics();
    loadProjects(1);
}

// Projects
async function loadProjects(page = 1) {
    currentPage = page;
    const search = document.getElementById('search-input').value;
    const language = document.getElementById('filter-language').value;
    const minStars = document.getElementById('filter-stars').value;
    const sortBy = document.getElementById('filter-sort').value;

    const params = new URLSearchParams({
        page, page_size: 20, language, min_stars: minStars,
        sort_by: sortBy, search, topic: currentTopic
    });

    const data = await api(`/api/projects?${params}`);
    const container = document.getElementById('projects-list');

    if (data.projects.length === 0) {
        container.innerHTML = '<div class="loading"><i class="fas fa-ghost"></i> 没有找到项目</div>';
    } else {
        container.innerHTML = data.projects.map(p => renderProjectItem(p, true)).join('');
    }

    renderPagination(data.total, data.page, data.page_size);
}

function renderProjectItem(p, withCheckbox = false) {
    const classes = ['project-item'];
    if (p.is_viewed) classes.push('viewed');
    if (p.spike_detected) classes.push('spike');
    if (p.is_trending) classes.push('trending');

    const avatarUrl = p.owner_avatar_url || 'https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png';
    const topicsHtml = p.topics ? p.topics.split(',').slice(0,3).map(t => `<span class="tag">${t}</span>`).join('') : '';

    return `
        <div class="${classes.join(' ')}" data-id="${p.github_id}">
            ${withCheckbox ? `<input type="checkbox" class="project-checkbox" data-id="${p.github_id}"
                ${selectedIds.has(p.github_id) ? 'checked' : ''}>` : ''}
            
            <img src="${avatarUrl}" alt="${p.name}" class="project-avatar" loading="lazy">
            
            <div class="project-info">
                <div class="project-name">
                    <a href="${p.url}" target="_blank">${p.full_name}</a>
                    ${p.spike_detected ? '<span class="tag spike"><i class="fas fa-bolt"></i> 飙升</span>' : ''}
                    ${p.is_trending ? '<span class="tag trending"><i class="fas fa-fire"></i> 趋势</span>' : ''}
                    ${topicsHtml}
                </div>
                <div class="project-desc" title="${p.description || ''}">${p.description || '暂无描述'}</div>
                <div class="project-meta">
                    <span><i class="fas fa-star" style="color: var(--orange)"></i> ${formatNum(p.stars)}</span>
                    <span><i class="fas fa-code-branch"></i> ${formatNum(p.forks)}</span>
                    ${p.star_growth_24h > 0 ? `<span style="color: var(--green)"><i class="fas fa-arrow-up"></i> +${p.star_growth_24h}</span>` : ''}
                    ${p.language ? `<span class="tag lang"><i class="fas fa-circle" style="font-size: 8px;"></i> ${p.language}</span>` : ''}
                    ${p.license_name ? `<span><i class="fas fa-balance-scale"></i> ${p.license_name}</span>` : ''}
                </div>
            </div>
            <div class="project-actions">
                <button class="btn-icon" onclick="openReadme(${p.github_id}, '${p.full_name}')" title="预览 README">
                    <i class="fab fa-readme"></i>
                </button>
                <button class="btn-icon ${p.is_favorite ? 'active' : ''}" onclick="toggleFavorite(${p.github_id})" title="收藏">
                    <i class="fas fa-star"></i>
                </button>
                <button class="btn-icon" onclick="markViewed(${p.github_id})" title="标记已查看">
                    <i class="fas fa-check"></i>
                </button>
                <button class="btn-icon" onclick="hideProject(${p.github_id})" title="隐藏">
                    <i class="fas fa-eye-slash"></i>
                </button>
            </div>
        </div>
    `;
}

function renderPagination(total, page, pageSize) {
    const pages = Math.ceil(total / pageSize);
    const container = document.getElementById('pagination');
    if (pages <= 1) { container.innerHTML = ''; return; }

    let html = '';
    if (page > 1) html += `<button onclick="loadProjects(${page - 1})"><i class="fas fa-chevron-left"></i></button>`;
    for (let i = 1; i <= Math.min(pages, 10); i++) {
        html += `<button class="${i === page ? 'active' : ''}" onclick="loadProjects(${i})">${i}</button>`;
    }
    if (page < pages) html += `<button onclick="loadProjects(${page + 1})"><i class="fas fa-chevron-right"></i></button>`;
    container.innerHTML = html;
}

// Favorites
async function loadFavorites() {
    const data = await api('/api/projects?favorites_only=true&show_viewed=true&show_hidden=true&page_size=100');
    const container = document.getElementById('favorites-list');
    container.innerHTML = data.projects.length === 0
        ? '<div class="loading">暂无收藏项目</div>'
        : data.projects.map(p => renderProjectItem(p)).join('');
}

// Trending
async function loadTrending() {
    const data = await api('/api/projects?trending_only=true&show_viewed=true&page_size=50');
    const container = document.getElementById('trending-list');
    container.innerHTML = data.projects.length === 0
        ? '<div class="loading">暂无趋势项目</div>'
        : data.projects.map(p => renderProjectItem(p)).join('');
}

// Timeline
async function loadTimeline() {
    const data = await api('/api/timeline?days=14');
    
    const ctxTimeline = document.getElementById('timeline-chart').getContext('2d');
    if (timelineChartInstance) timelineChartInstance.destroy();
    
    // Create gradient
    let gradient = ctxTimeline.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(139, 92, 246, 0.5)');   
    gradient.addColorStop(1, 'rgba(139, 92, 246, 0.0)');

    timelineChartInstance = new Chart(ctxTimeline, {
        type: 'line',
        data: {
            labels: data.map(d => new Date(d.date).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })),
            datasets: [{
                label: '每日新增项目',
                data: data.map(d => d.count),
                borderColor: '#8B5CF6',
                backgroundColor: gradient,
                borderWidth: 2,
                pointBackgroundColor: '#8B5CF6',
                pointBorderColor: '#fff',
                pointRadius: 4,
                pointHoverRadius: 6,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' } },
                x: { grid: { display: false } }
            }
        }
    });
}

// README Drawer
async function openReadme(githubId, fullName) {
    const drawer = document.getElementById('readme-drawer');
    const title = document.getElementById('drawer-title');
    const body = document.getElementById('drawer-body');
    
    title.textContent = fullName;
    body.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> 加载 README...</div>';
    drawer.classList.add('open');
    
    try {
        const data = await api(`/api/projects/${githubId}/readme`);
        if (data.error) {
            body.innerHTML = `<div class="loading"><i class="fas fa-exclamation-triangle"></i> ${data.error}</div>`;
        } else {
            const html = DOMPurify.sanitize(marked.parse(data.readme));
            body.innerHTML = html;
        }
    } catch (e) {
        body.innerHTML = '<div class="loading"><i class="fas fa-exclamation-triangle"></i> 加载失败</div>';
    }
}

document.getElementById('btn-close-drawer').addEventListener('click', () => {
    document.getElementById('readme-drawer').classList.remove('open');
});
document.getElementById('drawer-overlay').addEventListener('click', () => {
    document.getElementById('readme-drawer').classList.remove('open');
});

// Actions
async function markViewed(githubId) {
    await apiPut(`/api/projects/${githubId}/viewed`);
    showToast('已标记为已查看');
    refreshCurrent();
}

async function toggleFavorite(githubId) {
    const result = await apiPut(`/api/projects/${githubId}/favorite`);
    showToast(result.is_favorite ? '已收藏' : '已取消收藏');
    refreshCurrent();
}

async function hideProject(githubId) {
    await apiPut(`/api/projects/${githubId}/hide`);
    showToast('已隐藏');
    refreshCurrent();
}

async function batchMarkViewed() {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) { showToast('请先选择项目'); return; }
    await api('/api/projects/batch-viewed', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(ids),
    });
    showToast(`已批量标记 ${ids.length} 个项目`);
    selectedIds.clear();
    refreshCurrent();
}

async function triggerFetch() {
    const btn = document.getElementById('btn-fetch');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 抓取中...';
    try {
        const result = await apiPost('/api/fetch');
        showToast(`抓取完成: ${result.total} 个项目, ${result.new} 个新增`);
        refreshCurrent();
    } catch (e) {
        showToast('抓取失败，可能由于网络或速率限制');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-sync"></i> 立即抓取';
    }
}

function refreshCurrent() {
    switchView(currentView);
}

// Helpers
function formatNum(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n;
}

function showToast(msg) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'slideInUp 0.4s reverse forwards';
        setTimeout(() => toast.remove(), 400);
    }, 3000);
}

// Event listeners
document.getElementById('btn-fetch').addEventListener('click', triggerFetch);
document.getElementById('btn-batch-view').addEventListener('click', batchMarkViewed);

// Export
document.getElementById('btn-export-all')?.addEventListener('click', () => {
    window.location.href = '/api/export?type=all';
});
document.getElementById('btn-export-favorites')?.addEventListener('click', () => {
    window.location.href = '/api/export?type=favorites';
});

document.getElementById('search-input').addEventListener('input', debounce(() => loadProjects(1), 300));
document.getElementById('filter-language').addEventListener('change', () => loadProjects(1));
document.getElementById('filter-stars').addEventListener('change', () => loadProjects(1));
document.getElementById('filter-sort').addEventListener('change', () => loadProjects(1));

document.addEventListener('change', e => {
    if (e.target.classList.contains('project-checkbox')) {
        const id = parseInt(e.target.dataset.id);
        if (e.target.checked) selectedIds.add(id);
        else selectedIds.delete(id);
    }
});

// Triage Mode (Keyboard Shortcuts)
let focusedIndex = -1;
let currentProjects = [];

// Helper to extract current projects from DOM
function updateCurrentProjects() {
    currentProjects = Array.from(document.querySelectorAll('.view.active .project-item'));
    if (focusedIndex >= currentProjects.length) focusedIndex = currentProjects.length - 1;
    updateFocusUI();
}

function updateFocusUI() {
    document.querySelectorAll('.project-item.focused').forEach(el => el.classList.remove('focused'));
    if (focusedIndex >= 0 && focusedIndex < currentProjects.length) {
        const el = currentProjects[focusedIndex];
        el.classList.add('focused');
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

document.addEventListener('keydown', e => {
    // Disable shortcuts if inside an input or drawer is open
    if (e.target.tagName === 'INPUT' || document.getElementById('readme-drawer').classList.contains('open')) {
        if (e.key === 'Escape') document.getElementById('readme-drawer').classList.remove('open');
        return;
    }
    
    updateCurrentProjects();
    if (currentProjects.length === 0) return;

    if (e.key === 'j' || e.key === 'ArrowDown') {
        focusedIndex = Math.min(focusedIndex + 1, currentProjects.length - 1);
        updateFocusUI();
        e.preventDefault();
    } else if (e.key === 'k' || e.key === 'ArrowUp') {
        focusedIndex = Math.max(focusedIndex - 1, 0);
        updateFocusUI();
        e.preventDefault();
    } else if (e.key === 'v') {
        if (focusedIndex >= 0) {
            const id = currentProjects[focusedIndex].dataset.id;
            markViewed(id);
            // Automatically focus next item if available
            if (focusedIndex >= currentProjects.length - 1) focusedIndex--;
            e.preventDefault();
        }
    } else if (e.key === 'f') {
        if (focusedIndex >= 0) {
            const id = currentProjects[focusedIndex].dataset.id;
            toggleFavorite(id);
            e.preventDefault();
        }
    } else if (e.key === 'r') {
        if (focusedIndex >= 0) {
            const id = currentProjects[focusedIndex].dataset.id;
            const link = currentProjects[focusedIndex].querySelector('.project-name a');
            if (link) openReadme(id, link.textContent.trim());
            e.preventDefault();
        }
    } else if (e.key === 'Enter') {
        if (focusedIndex >= 0) {
            const link = currentProjects[focusedIndex].querySelector('.project-name a');
            if (link) window.open(link.href, '_blank');
            e.preventDefault();
        }
    }
});

function debounce(fn, ms) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}

// Init
async function initLanguages() {
    const langs = await api('/api/languages');
    const select = document.getElementById('filter-language');
    langs.forEach(l => {
        const opt = document.createElement('option');
        opt.value = l.language;
        opt.textContent = `${l.language} (${l.count})`;
        select.appendChild(opt);
    });
}

// Load on start
initLanguages();
loadDashboard();
