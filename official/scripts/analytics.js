// =====================================================
// AUTH GUARD
// =====================================================
Auth.requireRole('official');

// =====================================================
// LOAD INITIAL DATA
// =====================================================
document.addEventListener('DOMContentLoaded', () => {
    loadSectors();
    loadAnalytics();
    bindFilters();
});

// =====================================================
// FILTER HANDLING
// =====================================================
function bindFilters() {
    document.getElementById('timeFilter').addEventListener('change', loadAnalytics);
    document.getElementById('sectorFilter').addEventListener('change', loadAnalytics);
}

// =====================================================
// LOAD SECTORS
// =====================================================
async function loadSectors() {
    const res = await Auth.fetchWithAuth('/api/official/sectors');
    const sectors = await res.json();

    const select = document.getElementById('sectorFilter');
    sectors.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.name;
        select.appendChild(opt);
    });
}

// =====================================================
// LOAD ANALYTICS
// =====================================================
async function loadAnalytics() {
    const days = document.getElementById('timeFilter').value;
    const sector = document.getElementById('sectorFilter').value;

    const res = await Auth.fetchWithAuth(
        `/api/official/analytics?days=${days}&sector=${sector}`
    );

    if (!res.ok) {
        showModal('Error', 'Failed to load analytics');
        return;
    }

    const data = await res.json();
    renderSummary(data.summary);
    renderRepairTime(data.repair_time);
    renderContractors(data.contractors);
    renderHealthIndex(data.health_index);
}

// =====================================================
// RENDER SUMMARY
// =====================================================
function renderSummary(summary) {
    document.getElementById('summaryStats').innerHTML = `
        <div class="stat-card"><div class="stat-value">${summary.total_reports}</div><div class="stat-label">Total Reports</div></div>
        <div class="stat-card"><div class="stat-value">${summary.completed_repairs}</div><div class="stat-label">Completed Repairs</div></div>
        <div class="stat-card"><div class="stat-value">${summary.avg_repair_time} days</div><div class="stat-label">Avg Repair Time</div></div>
        <div class="stat-card"><div class="stat-value">₹${summary.total_spent}</div><div class="stat-label">Total Spent</div></div>
    `;
}

// =====================================================
// RENDER REPAIR TIME BAR CHART
// =====================================================
function renderRepairTime(items) {
    const chart = document.getElementById('repairTimeChart');
    chart.innerHTML = '';

    items.forEach(i => {
        const bar = document.createElement('div');
        bar.className = 'chart-bar';
        bar.style.height = `${i.days * 10}px`;
        bar.title = `${i.sector}: ${i.days} days`;
        chart.appendChild(bar);
    });
}

// =====================================================
// RENDER CONTRACTOR PERFORMANCE
// =====================================================
function renderContractors(list) {
    const container = document.getElementById('contractorPerformance');
    container.innerHTML = '';

    list.forEach(c => {
        container.innerHTML += `
            <div class="performance-item">
                <span class="contractor-name">${c.name}</span>
                <div class="performance-bar">
                    <div class="performance-fill" style="width:${c.score}%"></div>
                </div>
                <span class="performance-score">${c.score}%</span>
            </div>
        `;
    });
}

// =====================================================
// RENDER ROAD HEALTH INDEX
// =====================================================
function renderHealthIndex(items) {
    const grid = document.getElementById('roadHealthGrid');
    grid.innerHTML = '';

    items.forEach(i => {
        const color = i.index >= 8 ? '#28a745' : i.index >= 6 ? '#ffc107' : '#dc3545';
        grid.innerHTML += `
            <div class="health-index-card">
                <div class="health-index-value" style="color:${color}">
                    ${i.index.toFixed(1)}
                </div>
                <div class="health-index-label">${i.sector}</div>
                <div class="health-index-status">${i.status}</div>
            </div>
        `;
    });
}

// =====================================================
// EXPORT
// =====================================================
async function exportReport() {
    const days = document.getElementById('timeFilter').value;
    const sector = document.getElementById('sectorFilter').value;

    window.location.href =
        `/api/official/analytics/export?days=${days}&sector=${sector}`;
}
