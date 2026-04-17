// =====================================================
// AUTH GUARD
// =====================================================
Auth.requireRole('official');

// =====================================================
// GLOBALS
// =====================================================
let _hmYear      = new Date().getFullYear();
let _hmData      = null;   // cached heatmap API response
let _activeMonth = null;   // currently selected month (1-12 or null)

const CELL_SIZE = 13;   // px — matches CSS
const CELL_GAP  = 3;    // px — matches CSS
const WEEK_W    = CELL_SIZE + CELL_GAP;  // 16px per week-column

const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun',
                      'Jul','Aug','Sep','Oct','Nov','Dec'];

// =====================================================
// BOOT
// =====================================================
document.addEventListener('DOMContentLoaded', () => {
    loadHeatmap(_hmYear);
    loadPredictiveRisk();
});

// =====================================================
// 🗓️  HEATMAP — LOAD
// =====================================================
async function loadHeatmap(year) {
    document.getElementById('hmYearLabel').textContent = year;
    document.getElementById('hmCalendar').style.display  = 'none';
    document.getElementById('hmLoading').style.display   = 'flex';
    document.getElementById('hmMonthPanel').style.display = 'none';
    _activeMonth = null;

    try {
        const res = await Auth.fetchWithAuth(`/api/official/pothole-heatmap?year=${year}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        _hmData = await res.json();
        renderHeatmap(_hmData);
    } catch (err) {
        console.error('Heatmap load error:', err);
        document.getElementById('hmLoading').innerHTML =
            `<span style="color:#dc2626">⚠️ Could not load heatmap: ${err.message}</span>`;
    }
}

// =====================================================
// 🗓️  HEATMAP — RENDER 12 MONTHLY BLOCKS
// =====================================================
function renderHeatmap(data) {
    const { year, total, max_daily, daily_counts } = data;

    // ── Total pill ───────────────────────────────────
    document.getElementById('hmTotalPill').innerHTML =
        `<strong>${total.toLocaleString()}</strong> potholes reported in <strong>${year}</strong>`;

    // ── Build 12 monthly mini-calendar cards ─────────
    const container = document.getElementById('hmGrid');
    container.innerHTML = '';

    for (let m = 1; m <= 12; m++) {
        const card = buildMonthCard(m, year, daily_counts, max_daily);
        container.appendChild(card);
    }

    // ── Show calendar, hide loader ────────────────────
    document.getElementById('hmLoading').style.display  = 'none';
    document.getElementById('hmCalendar').style.display = 'block';
}

// ─── Build one monthly mini-calendar card ──────────────────────────────────
function buildMonthCard(month, year, daily_counts, max_daily) {
    const daysInMonth = new Date(year, month, 0).getDate();
    const firstDow    = new Date(year, month - 1, 1).getDay(); // 0=Sun … 6=Sat
    const prefix      = `${year}-${String(month).padStart(2, '0')}`;

    // Count total for this month
    const monthCount  = Object.entries(daily_counts)
        .filter(([k]) => k.startsWith(prefix))
        .reduce((s, [, v]) => s + v, 0);

    // Outer card
    const card = document.createElement('div');
    card.className    = 'hmm-card';
    card.dataset.month = month;

    // --- Header (month name + count badge) ---
    const header = document.createElement('div');
    header.className = 'hmm-header';
    header.innerHTML = `
        <span class="hmm-name">${MONTHS_SHORT[month - 1]}</span>
        <span class="hmm-count ${monthCount > 0 ? 'hmm-count-active' : ''}">${
            monthCount > 0 ? monthCount.toLocaleString() : '—'
        }</span>`;
    card.appendChild(header);

    // --- Weekday labels (S M T W T F S) ---
    const weekdays = document.createElement('div');
    weekdays.className = 'hmm-weekdays';
    ['S','M','T','W','T','F','S'].forEach(d => {
        const s = document.createElement('span');
        s.textContent = d;
        weekdays.appendChild(s);
    });
    card.appendChild(weekdays);

    // --- Day cell grid ---
    const grid = document.createElement('div');
    grid.className = 'hmm-day-grid';

    // Offset empty cells (so day 1 lands on correct column)
    for (let i = 0; i < firstDow; i++) {
        const ph = document.createElement('div');
        ph.className = 'hmm-cell hmm-cell-empty';
        grid.appendChild(ph);
    }

    // Day cells
    for (let d = 1; d <= daysInMonth; d++) {
        const dateStr = `${prefix}-${String(d).padStart(2, '0')}`;
        const count   = daily_counts[dateStr] || 0;
        const level   = getHeatLevel(count, max_daily);

        const cell = document.createElement('div');
        cell.className = `hmm-cell hmm-l${level}`;
        cell.title     = `${dateStr}: ${count} report${count !== 1 ? 's' : ''} — click to see hotspots`;

        // Day click: show hotspot cards for that day
        if (count > 0) {
            cell.style.cursor = 'pointer';
            cell.addEventListener('click', (e) => {
                e.stopPropagation();   // don't bubble to month card click
                onDayClick(dateStr);
            });
        }

        grid.appendChild(cell);
    }

    card.appendChild(grid);

    // Click → show prediction panel
    card.addEventListener('click', () => onMonthClick(month));

    return card;
}


// ── Compute colour level (0–4) ──────────────────────────────────────────────
function getHeatLevel(count, max) {
    if (count === 0 || max === 0) return 0;
    const r = count / max;
    if (r <= 0.10) return 1;
    if (r <= 0.30) return 2;
    if (r <= 0.65) return 3;
    return 4;
}

// =====================================================
// 🗓️  HEATMAP — YEAR NAVIGATION
// =====================================================
function changeHeatmapYear(delta) {
    _hmYear = (_hmYear || new Date().getFullYear()) + delta;
    loadHeatmap(_hmYear);
}

// =====================================================
// 🗓️  MONTH CLICK  →  simple monthly summary panel
// =====================================================
function onMonthClick(month) {
    if (!_hmData) return;
    _activeMonth = month;

    // Highlight clicked card
    document.querySelectorAll('.hmm-card').forEach(c => {
        c.classList.toggle('hmm-card-active', parseInt(c.dataset.month) === month);
    });

    const stats    = _hmData.monthly_stats[String(month)];
    const panel    = document.getElementById('hmMonthPanel');
    const total    = stats.count;
    const yearTotal = _hmData.total || 1;
    const pct      = yearTotal > 0 ? Math.round((total / yearTotal) * 100) : 0;
    const peakText = stats.peak_day
        ? `<strong>${stats.peak_count}</strong> on ${stats.peak_day}`
        : '—';
    const fillW    = Math.min(pct, 100);

    panel.style.display = 'block';
    panel.innerHTML = `
        <div class="hs-sum-panel">
            <div class="hs-sum-header">
                <span class="hs-sum-icon">📅</span>
                <div>
                    <div class="hs-sum-title">${stats.month_name} ${_hmYear}</div>
                    <div class="hs-sum-sub">Monthly pothole activity</div>
                </div>
                <button class="hs-sum-close" onclick="closeHotspotPanel()" title="Close">✕</button>
            </div>

            <div class="hs-sum-big">
                <span class="hs-sum-count">${total > 0 ? total.toLocaleString() : '—'}</span>
                <span class="hs-sum-count-lbl">potholes detected</span>
            </div>

            <div class="hs-sum-bar-wrap">
                <div class="hs-sum-bar">
                    <div class="hs-sum-bar-fill" style="width:${fillW}%"></div>
                </div>
                <span class="hs-sum-bar-pct">${pct}% of ${_hmYear} total</span>
            </div>

            <div class="hs-sum-stats">
                <div class="hs-sum-stat">
                    <div class="hs-sum-stat-val">${stats.daily_rate}</div>
                    <div class="hs-sum-stat-lbl">Avg per day</div>
                </div>
                <div class="hs-sum-stat">
                    <div class="hs-sum-stat-val">${stats.peak_count || 0}</div>
                    <div class="hs-sum-stat-lbl">Peak day count</div>
                </div>
                <div class="hs-sum-stat">
                    <div class="hs-sum-stat-val">${yearTotal.toLocaleString()}</div>
                    <div class="hs-sum-stat-lbl">Year total</div>
                </div>
            </div>

            ${stats.peak_day ? `<div class="hs-sum-peak">📍 Peak: ${peakText}</div>` : ''}
        </div>`;

    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // ── Animate numbers + width ─────────────────────────
    setTimeout(() => {
        animateValue(panel.querySelector('.hs-sum-count'), 0, total, 800);
        const barFill = panel.querySelector('.hs-sum-bar-fill');
        if (barFill) barFill.style.width = `${fillW}%`;
    }, 50);
}

// =====================================================
// 🗓️  DAY CLICK  →  simple daily summary panel
// =====================================================
function onDayClick(dateStr) {
    if (!_hmData) return;

    const count      = _hmData.daily_counts[dateStr] || 0;
    const panel      = document.getElementById('hmMonthPanel');
    const [y, m, d]  = dateStr.split('-');
    const dateLabel  = new Date(dateStr + 'T00:00:00').toLocaleDateString('en-GB',
        { day: 'numeric', month: 'long', year: 'numeric' });

    // Month share
    const monthStats = _hmData.monthly_stats[String(parseInt(m))];
    const monthTotal = monthStats?.count || 1;
    const pct        = monthTotal > 0 ? Math.round((count / monthTotal) * 100) : 0;
    const fillW      = Math.min(pct, 100);
    const maxDay     = _hmData.max_daily || 1;
    const dayPct     = Math.round((count / maxDay) * 100);

    panel.style.display = 'block';
    panel.innerHTML = `
        <div class="hs-sum-panel">
            <div class="hs-sum-header">
                <span class="hs-sum-icon">📅</span>
                <div>
                    <div class="hs-sum-title">${dateLabel}</div>
                    <div class="hs-sum-sub">Daily pothole detections</div>
                </div>
                <button class="hs-sum-close" onclick="closeHotspotPanel()" title="Close">✕</button>
            </div>

            <div class="hs-sum-big">
                <span class="hs-sum-count">0</span>
                <span class="hs-sum-count-lbl">potholes detected on this day</span>
            </div>

            ${count > 0 ? `
            <div class="hs-sum-bar-wrap">
                <div class="hs-sum-bar">
                    <div class="hs-sum-bar-fill" style="width:0%"></div>
                </div>
                <span class="hs-sum-bar-pct">${pct}% of ${monthStats?.month_name || ''} total (${monthTotal.toLocaleString()})</span>
            </div>

            <div class="hs-sum-stats">
                <div class="hs-sum-stat">
                    <div class="hs-sum-stat-val">${monthTotal.toLocaleString()}</div>
                    <div class="hs-sum-stat-lbl">${monthStats?.month_name || ''} total</div>
                </div>
                <div class="hs-sum-stat">
                    <div class="hs-sum-stat-val">${monthStats?.daily_rate || '—'}</div>
                    <div class="hs-sum-stat-lbl">Month avg / day</div>
                </div>
                <div class="hs-sum-stat">
                    <div class="hs-sum-stat-val">${dayPct}%</div>
                    <div class="hs-sum-stat-lbl">vs year peak</div>
                </div>
            </div>` : `<div class="hs-sum-no-data">No potholes recorded on this date.</div>`}
        </div>`;

    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // ── Animate numbers + width ─────────────────────────
    setTimeout(() => {
        animateValue(panel.querySelector('.hs-sum-count'), 0, count, 800);
        const barFill = panel.querySelector('.hs-sum-bar-fill');
        if (barFill) barFill.style.width = `${fillW}%`;
    }, 50);
}

// ── Shared Number Animation ──────────────────────────────────────────────────
function animateValue(obj, start, end, duration) {
    if (!obj || end === 0) {
        if (obj) obj.innerHTML = end;
        return;
    }
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        // easeOutQuart
        const ease = 1 - Math.pow(1 - progress, 4);
        obj.innerHTML = Math.floor(ease * (end - start) + start).toLocaleString();
        if (progress < 1) {
            window.requestAnimationFrame(step);
        } else {
            obj.innerHTML = end.toLocaleString();
        }
    };
    window.requestAnimationFrame(step);
}


function closeHotspotPanel() {
    const panel = document.getElementById('hmMonthPanel');
    if (panel) panel.style.display = 'none';
    document.querySelectorAll('.hmm-card').forEach(c => c.classList.remove('hmm-card-active'));
    _activeMonth = null;
}



// =====================================================
// 🔮 LAYER 3: PREDICTIVE RISK (Live DamageReport clusters)
// =====================================================

async function loadPredictiveRisk() {
    const container = document.getElementById('predictiveRiskContainer');
    if (!container) return;

    _setPredictiveRiskLoading(true);

    try {
        const res = await Auth.fetchWithAuth('/api/official/predictive-risk');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const payload = await res.json();
        window._prClusters = payload.clusters || [];   // cache for filter re-use
        renderPredictiveRiskSummary(payload);
        renderPredictiveRiskCards(window._prClusters);
    } catch (err) {
        console.error('Predictive risk load error:', err);
        const body = document.getElementById('predictiveRiskBody');
        if (body) {
            body.innerHTML = `<div class="pr-error">
                <span>⚠️</span> Could not load predictive risk data. ${err.message}
            </div>`;
        }
    } finally {
        _setPredictiveRiskLoading(false);
    }
}

function _setPredictiveRiskLoading(loading) {
    const spinner = document.getElementById('predictiveRiskSpinner');
    if (spinner) spinner.style.display = loading ? 'flex' : 'none';
}

function renderPredictiveRiskSummary(payload) {
    const highEl  = document.getElementById('prHighCount');
    const medEl   = document.getElementById('prMedCount');
    const lowEl   = document.getElementById('prLowCount');
    const totalEl = document.getElementById('prTotalCount');

    if (highEl)  highEl.textContent  = payload.high_risk   ?? 0;
    if (medEl)   medEl.textContent   = payload.medium_risk ?? 0;
    if (lowEl)   lowEl.textContent   = payload.low_risk    ?? 0;
    if (totalEl) totalEl.textContent = payload.total_clusters ?? 0;
}

function renderPredictiveRiskCards(clusters) {
    const body = document.getElementById('predictiveRiskBody');
    if (!body) return;
    body.innerHTML = '';

    // Read active filter
    const activeBtn   = document.querySelector('.pr-filter-btn.active');
    const activeFilter = activeBtn ? activeBtn.dataset.level : 'all';

    const filtered = activeFilter === 'all'
        ? clusters
        : clusters.filter(c => c.risk_level === activeFilter);

    if (filtered.length === 0) {
        body.innerHTML = `<div class="pr-empty">
            <span class="pr-empty-icon">🔍</span>
            <p>No ${activeFilter === 'all' ? '' : activeFilter + '-'}risk clusters found.</p>
        </div>`;
        return;
    }

    filtered.forEach((c, idx) => {
        const card = document.createElement('div');
        card.className = `pr-card pr-card-${c.risk_level}`;
        card.setAttribute('data-cluster-idx', idx);

        // prediction_pct = Poisson recurrence probability (the real forward-looking metric)
        const predPct     = c.prediction_pct ?? Math.round(c.risk_score * 100);
        const monthlyRate = c.monthly_rate  ?? '—';
        const levelIcon   = { high: '🔴', medium: '🟡', low: '🟢' }[c.risk_level] || '⚪';
        const levelLabel  = c.risk_level.charAt(0).toUpperCase() + c.risk_level.slice(1);
        const trendDir    = c.growth_trend > 0 ? 'up' : c.growth_trend < 0 ? 'down' : 'flat';
        const trendArrow  = c.growth_trend > 0 ? '▲' : c.growth_trend < 0 ? '▼' : '—';

        card.innerHTML = `
            <div class="pr-card-header">
                <div class="pr-level-badge pr-badge-${c.risk_level}">
                    ${levelIcon} ${levelLabel} Recurrence Risk
                </div>
                <div class="pr-score-ring" title="Recurrence Probability: ${predPct}%">
                    <svg viewBox="0 0 36 36" class="pr-donut">
                        <path class="pr-donut-track"
                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
                        <path class="pr-donut-segment pr-donut-${c.risk_level}"
                            stroke-dasharray="${predPct}, 100"
                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
                        <text x="18" y="20.35" class="pr-donut-text">${predPct}%</text>
                    </svg>
                </div>
            </div>

            <!-- Prediction banner -->
            <div class="pr-prediction-banner pr-pred-${c.risk_level}">
                🔮 <strong>${predPct}% chance</strong> of new pothole in next 30 days
                <span class="pr-rate-badge">${monthlyRate}/mo avg</span>
            </div>

            <div class="pr-card-body">
                <div class="pr-coords">
                    📍 <span>${c.latitude.toFixed(5)}, ${c.longitude.toFixed(5)}</span>
                    <a class="pr-map-link"
                       href="https://www.google.com/maps?q=${c.latitude},${c.longitude}"
                       target="_blank" rel="noopener">Open Map ↗</a>
                </div>

                <div class="pr-stats-row">
                    <div class="pr-stat">
                        <div class="pr-stat-val">${c.total_reports}</div>
                        <div class="pr-stat-lbl">Total</div>
                    </div>
                    <div class="pr-stat">
                        <div class="pr-stat-val">${c.reports_last_30}</div>
                        <div class="pr-stat-lbl">Last 30d</div>
                    </div>
                    <div class="pr-stat">
                        <div class="pr-stat-val">${c.unresolved ?? '—'}</div>
                        <div class="pr-stat-lbl">Open</div>
                    </div>
                    <div class="pr-stat">
                        <div class="pr-stat-val pr-trend-${trendDir}">
                            ${trendArrow}${Math.abs(c.growth_trend)}
                        </div>
                        <div class="pr-stat-lbl">Trend</div>
                    </div>
                </div>

                <div class="pr-reason">${c.reason}</div>
            </div>
        `;
        body.appendChild(card);
    });

    // Show empty state if filter removed everything
    if (body.children.length === 0) {
        body.innerHTML = `<div class="pr-empty">
            <span class="pr-empty-icon">🔍</span>
            <p>No ${activeFilter}-risk clusters found.</p>
        </div>`;
    }
}

async function triggerPredictiveRiskRefresh() {
    const btn = document.getElementById('prRefreshBtn');
    if (!btn) return;
    const orig = btn.innerHTML;
    btn.innerHTML = '<span class="pr-spinner-inline"></span> Refreshing...';
    btn.disabled = true;

    try {
        const res = await Auth.fetchWithAuth('/api/official/predictive-risk/refresh', {
            method: 'POST'
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload = await res.json();
        window._prClusters = payload.clusters || [];   // update cache
        renderPredictiveRiskSummary(payload);
        renderPredictiveRiskCards(window._prClusters);
        showModal('✅ Success', `Predictive risk refreshed — ${payload.total_clusters} clusters analysed.`);
    } catch (err) {
        console.error(err);
        showModal('Error', `Refresh failed: ${err.message}`);
    } finally {
        btn.innerHTML = orig;
        btn.disabled  = false;
    }
}

function filterPredictiveRisk(btn, level) {
    // Toggle active button
    document.querySelectorAll('.pr-filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    // Re-render from cached cluster list (no new network request)
    if (window._prClusters) {
        renderPredictiveRiskCards(window._prClusters);
    }
}

// no-op stub so no crash if old markup references it
function bindFilters() {}
