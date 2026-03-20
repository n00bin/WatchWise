/* ─── Rating Labels ──────────────────────────────────────────────── */
const RATING_LABELS = ['', 'Regret Watching', 'It Was Okay', 'Enjoyed It', 'Really Liked It', 'Would Watch Again'];

/* ─── Utilities ──────────────────────────────────────────────────── */

async function api(url, options = {}) {
    const token = localStorage.getItem('access_token');
    const defaults = {
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
    };
    const opts = { ...defaults, ...options };
    if (opts.body && typeof opts.body === 'object') {
        opts.body = JSON.stringify(opts.body);
    }
    const resp = await fetch(url, opts);
    if (resp.status === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        window.location.href = '/login';
        return;
    }
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || 'Request failed');
    }
    return resp.json();
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function renderStars(rating, interactive = false, onRate = null) {
    let html = '<div class="' + (interactive ? 'star-rating' : 'card-stars') + '">';
    for (let i = 1; i <= 5; i++) {
        if (interactive) {
            html += `<button class="star-btn ${i <= rating ? 'active' : ''}" data-value="${i}" onclick="${onRate}(${i})">&#9733;</button>`;
        } else {
            html += `<span class="star ${i <= rating ? 'filled' : ''}">&#9733;</span>`;
        }
    }
    html += '</div>';
    return html;
}

/* ─── Search Modal ───────────────────────────────────────────────── */

let searchType = 'movie';
let searchTimeout = null;
let searchAddCallback = null;

function openSearchModal(type = 'movie', title = 'Search', addCallback = null) {
    searchType = type;
    searchAddCallback = addCallback;
    document.getElementById('searchModalTitle').textContent = title;
    document.getElementById('searchModal').classList.add('open');
    document.getElementById('searchInput').value = '';
    document.getElementById('searchResults').innerHTML = '<p class="search-hint">Start typing to search...</p>';

    // Set toggle button state
    document.querySelectorAll('#searchTypeToggle .toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.type === type);
    });

    setTimeout(() => document.getElementById('searchInput').focus(), 100);
}

function closeSearchModal() {
    document.getElementById('searchModal').classList.remove('open');
}

function setSearchType(type) {
    searchType = type;
    document.querySelectorAll('#searchTypeToggle .toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.type === type);
    });
    const query = document.getElementById('searchInput').value.trim();
    if (query.length >= 2) performSearch(query);
}

async function performSearch(query) {
    const container = document.getElementById('searchResults');
    container.innerHTML = '<div class="loading-center"><div class="spinner"></div></div>';

    try {
        const results = await api(`/api/search?q=${encodeURIComponent(query)}&media_type=${searchType}`);

        if (results.length === 0) {
            container.innerHTML = '<p class="search-hint">No results found</p>';
            return;
        }

        if (searchType === 'anime') {
            container.innerHTML = results.map(item => `
                <div class="search-result-item">
                    <div class="search-result-poster">
                        ${item.poster_path ? `<img src="${item.poster_path}" alt="">` : '<div class="no-poster">No Image</div>'}
                    </div>
                    <div class="search-result-info">
                        <div class="search-result-title">${escapeHtml(item.title_english || item.title)}</div>
                        ${item.title_english && item.title_english !== item.title ? `<div class="search-result-year" style="font-style:italic">${escapeHtml(item.title)}</div>` : ''}
                        <div class="search-result-year">${item.release_date || 'N/A'} &bull; ${item.anime_type || ''} &bull; ${item.episodes || '?'} eps ${item.tmdb_rating ? '&bull; MAL ' + item.tmdb_rating.toFixed(1) : ''}</div>
                        <div class="search-result-overview">${escapeHtml(item.overview)}</div>
                    </div>
                    <div class="search-result-actions">
                        <button class="btn btn-primary btn-xs" onclick="addAnimeFromSearch(${item.mal_id}, 'plan_to_watch')">+ Plan</button>
                        <button class="btn btn-success btn-xs" onclick="addAnimeFromSearch(${item.mal_id}, 'completed')">+ Done</button>
                    </div>
                </div>
            `).join('');
        } else {
            container.innerHTML = results.map(item => `
                <div class="search-result-item">
                    <div class="search-result-poster">
                        ${item.poster_path ? `<img src="${item.poster_path}" alt="">` : '<div class="no-poster">No Image</div>'}
                    </div>
                    <div class="search-result-info">
                        <div class="search-result-title">${escapeHtml(item.title)}</div>
                        <div class="search-result-year">${item.release_date ? item.release_date.substring(0, 4) : 'N/A'} &bull; TMDB ${item.tmdb_rating.toFixed(1)}</div>
                        <div class="search-result-overview">${escapeHtml(item.overview)}</div>
                    </div>
                    <div class="search-result-actions">
                        <button class="btn btn-primary btn-xs" onclick="addFromSearch(${item.tmdb_id}, 'watchlist')">+ Watchlist</button>
                        <button class="btn btn-success btn-xs" onclick="addFromSearch(${item.tmdb_id}, 'watched')">+ Watched</button>
                    </div>
                </div>
            `).join('');
        }
    } catch (err) {
        container.innerHTML = `<p class="search-hint" style="color: var(--danger)">Error: ${err.message}</p>`;
    }
}

async function addFromSearch(tmdbId, status) {
    const endpoint = searchType === 'movie' ? '/api/movies' : '/api/tvshows';
    try {
        const result = await api(endpoint, {
            method: 'POST',
            body: { tmdb_id: tmdbId, status: status },
        });
        showToast(`Added "${result.title}" to your ${status}!`, 'success');
        closeSearchModal();
        if (searchAddCallback) searchAddCallback();
        if (typeof loadPageData === 'function') loadPageData();
    } catch (err) {
        if (err.message.includes('already')) {
            showToast('Already in your list!', 'info');
        } else {
            showToast(`Error: ${err.message}`, 'error');
        }
    }
}

async function addAnimeFromSearch(malId, status) {
    try {
        const result = await api('/api/anime', {
            method: 'POST',
            body: { mal_id: malId, status: status },
        });
        const statusLabel = status === 'plan_to_watch' ? 'plan to watch' : status;
        showToast(`Added "${result.title}" as ${statusLabel}!`, 'success');
        closeSearchModal();
        if (searchAddCallback) searchAddCallback();
        if (typeof loadPageData === 'function') loadPageData();
    } catch (err) {
        if (err.message.includes('already')) {
            showToast('Already in your list!', 'info');
        } else {
            showToast(`Error: ${err.message}`, 'error');
        }
    }
}

// Search input debounce
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('searchInput');
    if (input) {
        input.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            const query = e.target.value.trim();
            if (query.length < 2) {
                document.getElementById('searchResults').innerHTML = '<p class="search-hint">Start typing to search...</p>';
                return;
            }
            searchTimeout = setTimeout(() => performSearch(query), 400);
        });
    }

    // Close modals on overlay click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.remove('open');
            }
        });
    });

    // Keyboard shortcut: Escape closes modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
        }
    });
});

/* ─── Detail Modal ───────────────────────────────────────────────── */

let currentDetailItem = null;
let currentDetailType = null;

function openDetailModal(item, type) {
    currentDetailItem = item;
    currentDetailType = type;

    document.getElementById('detailTitle').textContent = item.title;

    const isMovie = type === 'movie';
    const dateLabel = isMovie ? item.release_date : item.first_air_date;
    const year = dateLabel ? dateLabel.substring(0, 4) : 'N/A';

    let metaHtml = `<span>${year}</span>`;
    if (isMovie && item.runtime) metaHtml += `<span>${item.runtime} min</span>`;
    if (!isMovie) {
        if (item.number_of_seasons) metaHtml += `<span>${item.number_of_seasons} season${item.number_of_seasons > 1 ? 's' : ''}</span>`;
        if (item.number_of_episodes) metaHtml += `<span>${item.number_of_episodes} episodes</span>`;
    }
    metaHtml += `<span>TMDB ${item.tmdb_rating.toFixed(1)}</span>`;

    const statusOptions = ['watchlist', 'watching', 'watched', 'dropped'];

    document.getElementById('detailBody').innerHTML = `
        <div class="detail-poster-row">
            <div class="detail-poster">
                ${item.poster_path ? `<img src="${item.poster_path}" alt="">` : '<div class="no-poster" style="height:210px;display:flex;align-items:center;justify-content:center;background:var(--card);border-radius:8px">No Poster</div>'}
            </div>
            <div class="detail-info">
                <div class="detail-genres">
                    ${(item.genres || []).map(g => `<span class="genre-tag">${g}</span>`).join('')}
                </div>
                <div class="detail-meta">${metaHtml}</div>
                <div style="margin-bottom:12px">
                    <label style="font-size:0.82rem;color:var(--text-muted);display:block;margin-bottom:4px">Status</label>
                    <select class="form-input" style="width:auto;padding:6px 10px" onchange="updateStatus(this.value)">
                        ${statusOptions.map(s => `<option value="${s}" ${item.status === s ? 'selected' : ''}>${s.charAt(0).toUpperCase() + s.slice(1)}</option>`).join('')}
                    </select>
                </div>
            </div>
        </div>
        <div class="detail-overview">${item.overview || 'No overview available.'}</div>
        <div class="detail-rating">
            <h4>Your Rating</h4>
            ${renderStars(item.user_rating || 0, true, 'rateItem')}
            <div class="detail-rating-label" id="detailRatingLabel">${item.user_rating ? RATING_LABELS[item.user_rating] : 'Not rated yet'}</div>
        </div>
        <div class="detail-notes">
            <label style="font-size:0.82rem;color:var(--text-muted);display:block;margin-bottom:4px">Notes</label>
            <textarea id="detailNotes" placeholder="Add personal notes...">${item.notes || ''}</textarea>
        </div>
        <div class="detail-actions">
            <button class="btn btn-primary btn-sm" onclick="saveDetail()">Save Changes</button>
            <button class="btn btn-danger btn-sm" onclick="deleteDetail()">Remove</button>
        </div>
    `;

    document.getElementById('detailModal').classList.add('open');
}

function closeDetailModal() {
    document.getElementById('detailModal').classList.remove('open');
}

function rateItem(rating) {
    currentDetailItem.user_rating = rating;
    document.querySelectorAll('#detailModal .star-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.value) <= rating);
    });
    document.getElementById('detailRatingLabel').textContent = RATING_LABELS[rating];
}

async function updateStatus(status) {
    const endpoint = currentDetailType === 'movie'
        ? `/api/movies/${currentDetailItem.id}`
        : `/api/tvshows/${currentDetailItem.id}`;

    try {
        await api(endpoint, { method: 'PUT', body: { status } });
        currentDetailItem.status = status;
        showToast(`Status updated to ${status}`, 'success');
    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
    }
}

async function saveDetail() {
    const endpoint = currentDetailType === 'movie'
        ? `/api/movies/${currentDetailItem.id}`
        : `/api/tvshows/${currentDetailItem.id}`;

    const notes = document.getElementById('detailNotes').value;

    try {
        await api(endpoint, {
            method: 'PUT',
            body: {
                user_rating: currentDetailItem.user_rating,
                notes: notes,
            },
        });
        showToast('Saved!', 'success');
        closeDetailModal();
        if (typeof loadPageData === 'function') loadPageData();
    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
    }
}

async function deleteDetail() {
    if (!confirm(`Remove "${currentDetailItem.title}" from your list?`)) return;

    const endpoint = currentDetailType === 'movie'
        ? `/api/movies/${currentDetailItem.id}`
        : `/api/tvshows/${currentDetailItem.id}`;

    try {
        await api(endpoint, { method: 'DELETE' });
        showToast('Removed!', 'success');
        closeDetailModal();
        if (typeof loadPageData === 'function') loadPageData();
    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
    }
}

/* ─── Helpers ────────────────────────────────────────────────────── */

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMediaCard(item, type) {
    const year = (item.release_date || item.first_air_date || '').substring(0, 4);
    return `
        <div class="media-card" onclick='openDetailModal(${JSON.stringify(item).replace(/'/g, "&#39;")}, "${type}")'>
            <div class="poster-wrap">
                ${item.poster_path
                    ? `<img src="${item.poster_path}" alt="${escapeHtml(item.title)}" loading="lazy">`
                    : '<div class="no-poster">No Poster</div>'}
                ${item.user_rating ? `<div class="card-badge">&#9733; ${item.user_rating} &mdash; ${RATING_LABELS[item.user_rating]}</div>` : ''}
                <div class="status-badge ${item.status}">${item.status}</div>
            </div>
            <div class="card-info">
                <div class="card-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
                <div class="card-meta">
                    <span>${year || 'N/A'}</span>
                </div>
                ${item.user_rating ? renderStars(item.user_rating) : ''}
            </div>
        </div>
    `;
}
