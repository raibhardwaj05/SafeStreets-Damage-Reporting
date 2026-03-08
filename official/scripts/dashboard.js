// Officer Dashboard JavaScript

let allOfficerReports = [];
let filteredReports = [];
let currentPage = 1;
const pageSize = 4;
let sourceFilter = 'all';

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', async () => {
    Auth.requireRole('official');
    await loadReports();
});

/**
 * Fetch reports from API
 */
async function loadReports() {
    const tbody = document.getElementById('reportsTableBody');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 2rem;"><div class="spinner"></div> Loading reports...</td></tr>';
    }

    try {
        const response = await Auth.fetchWithAuth('/api/official/reports');
        if (!response.ok) throw new Error('Failed to fetch reports');

        allOfficerReports = await response.json();
        filteredReports = [...allOfficerReports];

        initDashboard();
    } catch (error) {
        console.error('Load Error:', error);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 2rem; color:red;">Error loading reports: ${error.message}</td></tr>`;
        }
    }
}

/**
 * Initialize dashboard
 */
function initDashboard() {
    updateKPIs();
    renderReportsTable();
}

/**
 * Update KPI cards
 */
function updateKPIs() {
    const total = allOfficerReports.length;
    const pending = allOfficerReports.filter(r => r.status === 'submitted').length; // 'submitted' is pending verification
    const inProgress = allOfficerReports.filter(r => ['verified', 'assigned', 'in-progress'].includes(r.status)).length;
    const critical = allOfficerReports.filter(r => r.severity === 'critical' || r.severity === 'high').length;

    document.getElementById('totalReports').textContent = total;
    document.getElementById('pendingReports').textContent = pending;
    document.getElementById('inProgressReports').textContent = inProgress;
    document.getElementById('criticalReports').textContent = critical;
}

/**
 * Apply filters
 */
function applyFilters() {
    const searchInput = document.getElementById('dashboardSearchInput');
    const searchText = (searchInput ? searchInput.value : '').toLowerCase();
    const issueTypeFilter = document.getElementById('issueTypeFilter').value;
    const severityFilter = document.getElementById('severityFilter').value;
    const statusFilter = document.getElementById('statusFilter').value;
    const startDate = document.getElementById('startDateFilter').value;
    const endDate = document.getElementById('endDateFilter').value;

    filteredReports = allOfficerReports.filter(report => {
        // 1. Search Logic
        const reportId = (report.id || '').toLowerCase();
        const location = (report.location || '').toLowerCase();
        const damageType = (report.damage_type || '').toLowerCase();
        const searchMatch = !searchText ||
            reportId.includes(searchText) ||
            location.includes(searchText) ||
            damageType.includes(searchText);

        // 2. Issue Type Logic
        const issueTypeMatch = !issueTypeFilter || (report.damage_type || '').toLowerCase().includes(issueTypeFilter);

        // 3. Severity Logic
        const severityMatch = !severityFilter || (report.severity || '').toLowerCase() === severityFilter;

        // 4. Status Logic
        let statusMatch = !statusFilter;
        if (statusFilter === 'verified') {
            statusMatch = report.status === 'verified' || report.status === 'approved';
        } else if (statusFilter) {
            statusMatch = report.status === statusFilter;
        }

        // 4. Date Logic
        let dateMatch = true;
        const reportDate = new Date(report.created_at);
        reportDate.setHours(0, 0, 0, 0);

        if (startDate) {
            const start = new Date(startDate);
            start.setHours(0, 0, 0, 0);
            if (reportDate < start) dateMatch = false;
        }
        if (endDate) {
            const end = new Date(endDate);
            end.setHours(23, 59, 59, 999);
            if (reportDate > end) dateMatch = false;
        }

        // 5. Source Logic
        let sourceMatch = true;
        if (sourceFilter === 'dashcam') {
            sourceMatch = false;
        }

        return searchMatch && issueTypeMatch && severityMatch && statusMatch && dateMatch && sourceMatch;
    });

    currentPage = 1;
    renderReportsTable();
}

function getReportSource(report) {
    const imageUrl = report.image_url || '';
    if (imageUrl.indexOf('VIDEO_REPORT') !== -1 || imageUrl.indexOf('rt_submit_') !== -1) {
        return 'dashcam';
    }
    return 'citizen';
}

/**
 * Clear all filters
 */
function clearFilters() {
    const searchInput = document.getElementById('dashboardSearchInput');
    if (searchInput) searchInput.value = '';
    document.getElementById('issueTypeFilter').value = '';
    document.getElementById('severityFilter').value = '';
    document.getElementById('statusFilter').value = '';
    document.getElementById('startDateFilter').value = '';
    document.getElementById('endDateFilter').value = '';
    sourceFilter = 'all';
    filteredReports = [...allOfficerReports];
    currentPage = 1;
    updateSourceButtons();
    renderReportsTable();
}

/**
 * Render reports table
 */
function renderReportsTable() {
    const tbody = document.getElementById('reportsTableBody');
    const summary = document.getElementById('reportsSummary');
    const pagination = document.getElementById('reportsPagination');

    if (!tbody) {
        return;
    }

    if (filteredReports.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 2rem;">No reports found matching the filters.</td></tr>';
        if (summary) {
            summary.textContent = 'Showing 0 to 0 of 0 reports';
        }
        if (pagination) {
            pagination.innerHTML = '';
        }
        return;
    }

    const total = filteredReports.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > totalPages) {
        currentPage = totalPages;
    }
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, total);
    const pageItems = filteredReports.slice(startIndex, endIndex);

    tbody.innerHTML = pageItems.map(report => {
        const severity = (report.severity || 'low').toLowerCase();
        const severityPill = `pill-${severity}`;
        const severityText = severity.charAt(0).toUpperCase() + severity.slice(1);

        // Status mapping
        let statusPill = 'pill-pending';
        let statusText = report.status;

        if (report.status === 'submitted') { statusPill = 'pill-pending'; statusText = 'Pending Review'; }
        else if (report.status === 'verified' || report.status === 'approved') { statusPill = 'pill-progress'; statusText = 'Verified'; }
        else if (report.status === 'assigned') { statusPill = 'pill-progress'; statusText = 'Assigned'; }
        else if (report.status === 'in-progress') { statusPill = 'pill-progress'; statusText = 'In Progress'; }
        else if (report.status === 'resolved') { statusPill = 'pill-resolved'; statusText = 'Resolved'; }
        else if (report.status === 'rejected') { statusPill = 'pill-resolved'; statusText = 'Rejected'; }

        const dateStr = report.created_at ? new Date(report.created_at).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' }) : 'N/A';
        const agoText = report.created_at ? formatTimeAgo(new Date(report.created_at)) : 'N/A';

        return `
            <tr>
                <td style="font-weight: 600;" title="${report.id}">${report.id.split('-')[0].substring(0, 8)}</td>
                <td>${report.location}</td>
                <td>${report.damage_type || 'Road Damage'}</td>
                <td><span class="pill ${statusPill}">${statusText}</span></td>
                <td><span class="pill pill-${severity}">${severityText}</span></td>
                <td style="color: var(--text-muted);">${dateStr}</td>
                <td>
                    <div class="action-btns">
                        <button class="action-btn" title="View Details" onclick="openPanel('${encodeURIComponent(JSON.stringify(report))}')">
                            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                            </svg>
                        </button>
                        ${report.status === 'submitted' ? `
                            <button class="action-btn" title="Verify" onclick="verifyReport('${report.id}')">
                                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                                </svg>
                            </button>
                        ` : ''}
                        ${(report.status === 'verified' || report.status === 'approved') ? `
                            <button class="action-btn" title="Assign" onclick="assignReport('${report.id}')">
                                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><polyline points="16 11 18 13 22 9"/>
                                </svg>
                            </button>
                        ` : ''}
                        ${(report.status === 'assigned' || report.status === 'in-progress') ? `
                            <button class="action-btn" title="Monitor" onclick="monitorReport('${report.id}')">
                                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><path d="M12 9v3l2 2"/><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                                </svg>
                            </button>
                        ` : ''}
                        <!-- <button class="action-btn" title="Edit">
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                            </svg>
                        </button> -->
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    if (summary) {
        summary.textContent = 'Showing ' + (startIndex + 1) + ' to ' + endIndex + ' of ' + total + ' reports';
    }

    if (pagination) {
        if (totalPages <= 1) {
            pagination.innerHTML = '';
        } else {
            let buttons = '';
            const prevPage = currentPage - 1;
            buttons += '<button class="page-btn' + (currentPage === 1 ? ' disabled' : '') + '" onclick="changePage(' + prevPage + ')"' + (currentPage === 1 ? ' disabled' : '') + '>&lt;</button>';
            for (let i = 1; i <= totalPages; i++) {
                buttons += '<button class="page-btn' + (i === currentPage ? ' active' : '') + '" onclick="changePage(' + i + ')">' + i + '</button>';
            }
            const nextPage = currentPage + 1;
            buttons += '<button class="page-btn' + (currentPage === totalPages ? ' disabled' : '') + '" onclick="changePage(' + nextPage + ')"' + (currentPage === totalPages ? ' disabled' : '') + '>&gt;</button>';
            pagination.innerHTML = buttons;
        }
    }
}

function changePage(page) {
    const totalPages = Math.max(1, Math.ceil(filteredReports.length / pageSize));
    if (page < 1 || page > totalPages) {
        return;
    }
    currentPage = page;
    renderReportsTable();
}

function setSourceFilter(source) {
    if (sourceFilter === source) {
        sourceFilter = 'all';
    } else {
        sourceFilter = source;
    }
    currentPage = 1;
    updateSourceButtons();
    applyFilters();
}

function updateSourceButtons() {
    const citizenBtn = document.getElementById('sourceCitizenBtn');
    const dashcamBtn = document.getElementById('sourceDashcamBtn');
    if (!citizenBtn || !dashcamBtn) {
        return;
    }
    citizenBtn.classList.remove('active');
    dashcamBtn.classList.remove('active');

    if (sourceFilter === 'citizen') {
        citizenBtn.classList.add('active');
    } else if (sourceFilter === 'dashcam') {
        dashcamBtn.classList.add('active');
    }
}

/**
 * Helper to format time ago
 */
function formatTimeAgo(date) {
    const now = new Date();
    const diffInSeconds = Math.floor((now - date) / 1000);
    const diffInMinutes = Math.floor(diffInSeconds / 60);
    const diffInHours = Math.floor(diffInMinutes / 60);
    const diffInDays = Math.floor(diffInHours / 24);

    if (diffInDays > 0) return `${diffInDays}d ago`;
    if (diffInHours > 0) return `${diffInHours}h ago`;
    if (diffInMinutes > 0) return `${diffInMinutes}m ago`;
    return 'Just now';
}

// Expose functions to window
window.applyFilters = applyFilters;
window.clearFilters = clearFilters;
window.changePage = changePage;
window.setSourceFilter = setSourceFilter;
window.viewReport = (id) => {
    const report = allOfficerReports.find(r => r.id === id);
    if (report) openPanel(encodeURIComponent(JSON.stringify(report)));
};

window.verifyReport = (id) => {
    window.location.href = `verification.html?id=${id}`;
};
window.assignReport = (id) => {
    window.location.href = `assignment.html?id=${id}`;
};
window.monitorReport = (id) => {
    window.location.href = `monitoring.html?id=${id}`;
};

// --- Slide Panel Logic ---
let panelMap = null;
let panelMarker = null;

function openPanel(reportJson) {
    const report = JSON.parse(decodeURIComponent(reportJson));

    // 1. Fill Text Data
    document.getElementById("panelDamageType").textContent = report.damage_type || "Unknown";
    document.getElementById("panelConfidence").textContent =
        report.confidence ? (report.confidence * 100).toFixed(1) + "%" : "N/A";
    document.getElementById("panelSeverity").textContent = report.severity || "Pending";
    document.getElementById("panelStatus").textContent = report.status || "Submitted";

    // 2. Open the Panel
    document.getElementById("reportPanel").classList.add("open");

    // 3. Load Map (Wait for transition to finish)
    setTimeout(() => {
        loadPanelMap(report.latitude, report.longitude);
    }, 300);
}

function closePanel() {
    document.getElementById("reportPanel").classList.remove("open");
}

function loadPanelMap(lat, lng) {
    if (!lat || !lng) {
        console.error("No coordinates available for this report.");
        return;
    }

    if (!panelMap) {
        // Initialize map if it doesn't exist
        panelMap = L.map("panelMap").setView([lat, lng], 15);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "© OpenStreetMap"
        }).addTo(panelMap);

        panelMarker = L.marker([lat, lng]).addTo(panelMap);
    } else {
        // Move existing map and marker
        panelMap.setView([lat, lng], 15);
        panelMarker.setLatLng([lat, lng]);
    }

    // Force Leaflet to recalculate size (prevents gray tiles)
    setTimeout(() => panelMap.invalidateSize(), 200);
}

// Expose open/close to window for HTML onclicks
window.openPanel = openPanel;
window.closePanel = closePanel;

/**
 * Toggle profile menu visibility
 */
window.toggleProfileMenu = function () {
    const menu = document.getElementById('profileMenu');
    if (menu) menu.classList.toggle('active');
};

/**
 * Export dashboard data (Placeholder)
 */
window.exportData = function () {
    alert("Exporting data as CSV...");
    // Logic for actual export can go here
};

// Close menu when clicking outside
document.addEventListener('click', (e) => {
    const profileSection = document.querySelector('.profile-section');
    const menu = document.getElementById('profileMenu');
    if (profileSection && !profileSection.contains(e.target) && menu) {
        menu.classList.remove('active');
    }
});