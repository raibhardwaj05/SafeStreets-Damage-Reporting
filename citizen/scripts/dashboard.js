// Citizen Dashboard JavaScript

// State
let allReports = [];
let filteredDashReports = [];
let blobImageCache = {};
const DASH_PER_PAGE = 4;
let dashCurrentPage = 1;

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', async () => {
    Auth.requireRole('citizen');
    initDashFilters();
    await loadReports();
});

/**
 * Initialize filter listeners
 */
function initDashFilters() {
    const searchInput = document.getElementById('dashSearchInput');
    const statusFilter = document.getElementById('dashStatusFilter');

    if (searchInput) {
        searchInput.addEventListener('input', () => {
            dashCurrentPage = 1;
            applyDashFilters();
        });
    }

    if (statusFilter) {
        statusFilter.addEventListener('change', () => {
            dashCurrentPage = 1;
            applyDashFilters();
        });
    }
}

/**
 * Fetch and render reports from API
 */
async function loadReports() {
    const tbody = document.getElementById('recentReportsList');
    tbody.innerHTML = `
        <tr class="loading-row">
            <td colspan="6">
                <div class="table-loading">
                    <div class="spinner-sm"></div>
                    Loading reports…
                </div>
            </td>
        </tr>`;

    try {
        const response = await Auth.fetchWithAuth('/api/citizen/reports');
        if (!response.ok) throw new Error('Failed to fetch reports');

        allReports = await response.json();
        updateStatusSummary(allReports);
        applyDashFilters();
        loadPreviewImages();

    } catch (error) {
        console.error('Load Error:', error);
        tbody.innerHTML = `
            <tr>
                <td colspan="6">
                    <div class="table-empty">
                        <strong>Unable to load reports</strong>
                        ${error.message}
                    </div>
                </td>
            </tr>`;
    }
}

/**
 * Apply search and status filter
 */
function applyDashFilters() {
    const searchTerm = (document.getElementById('dashSearchInput')?.value || '').toLowerCase().trim();
    const statusVal = document.getElementById('dashStatusFilter')?.value || 'all';

    filteredDashReports = allReports.filter(r => {
        // Search
        if (searchTerm) {
            const idMatch = String(r.id).toLowerCase().includes(searchTerm);
            const locMatch = (r.location || '').toLowerCase().includes(searchTerm);
            if (!idMatch && !locMatch) return false;
        }
        // Status filter
        if (statusVal !== 'all' && r.status !== statusVal) return false;
        return true;
    });

    // Sort by date descending
    filteredDashReports.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

    renderRecentReports();
    renderDashPagination();
}

/**
 * Load preview images using authenticated fetch
 */
async function loadPreviewImages() {
    for (const report of allReports) {
        const imageUrl = report.image_url;
        if (!imageUrl) continue;
        if (blobImageCache[imageUrl]) continue;

        try {
            const res = await Auth.fetchWithAuth(imageUrl);
            if (res.ok) {
                const blob = await res.blob();
                const blobUrl = URL.createObjectURL(blob);
                blobImageCache[imageUrl] = blobUrl;

                // Update visible thumbnail
                const imgEl = document.querySelector(`img[data-report-id="${report.id}"]`);
                if (imgEl) {
                    imgEl.src = blobUrl;
                    imgEl.style.display = 'block';
                    const placeholder = imgEl.parentElement.querySelector('.preview-placeholder');
                    if (placeholder) placeholder.style.display = 'none';
                }
            }
        } catch (e) {
            console.warn(`Failed to load image for report ${report.id}`, e);
        }
    }
}

/**
 * Map backend status to badge class and display text
 */
function getStatusBadge(status) {
    const map = {
        'submitted': { cls: 'badge-reported', text: 'Reported' },
        'approved': { cls: 'badge-reported', text: 'Verified' },
        'verified': { cls: 'badge-reported', text: 'Verified' },
        'assigned': { cls: 'badge-inprogress', text: 'Assigned' },
        'in-progress': { cls: 'badge-inprogress', text: 'In Progress' },
        'resolved': { cls: 'badge-completed', text: 'Completed' },
        'rejected': { cls: 'badge-rejected', text: 'Rejected' }
    };
    return map[status] || { cls: 'badge-default', text: status };
}

/**
 * Format report ID — show last segment for readability
 */
function formatReportId(id) {
    if (!id) return '#RD-0000';
    const short = String(id).replace(/-/g, '').slice(-8).toUpperCase();
    return `#RD-${short}`;
}

/**
 * Render recent reports table
 */
function renderRecentReports() {
    const tbody = document.getElementById('recentReportsList');

    if (!filteredDashReports || filteredDashReports.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6">
                    <div class="table-empty">
                        <strong>No reports found</strong>
                        Try adjusting your search or submit your first report!
                    </div>
                </td>
            </tr>`;
        return;
    }

    const total = filteredDashReports.length;
    const start = (dashCurrentPage - 1) * DASH_PER_PAGE;
    const end = Math.min(start + DASH_PER_PAGE, total);
    const pageReports = filteredDashReports.slice(start, end);

    tbody.innerHTML = pageReports.map(report => {
        const badge = getStatusBadge(report.status);
        const reportId = formatReportId(report.id);
        const location = report.location || 'Unknown Location';
        const dateStr = report.created_at
            ? new Date(report.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
            : '—';

        const imageUrl = report.image_url || '';
        const blobUrl = blobImageCache[imageUrl] || '';
        const hasImage = blobUrl.length > 0;

        return `
            <tr>
                <td>
                    <div class="preview-thumb">
                        ${hasImage
                ? `<img src="${blobUrl}" alt="Preview" class="preview-img" data-report-id="${report.id}">`
                : `<div class="preview-placeholder" data-report-id-ph="${report.id}"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg></div><img src="" alt="Preview" class="preview-img" data-report-id="${report.id}" style="display:none;">`
            }
                    </div>
                </td>
                <td class="report-id">${reportId}</td>
                <td class="report-location">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="#3b82f6" stroke="none" style="vertical-align:-1px;margin-right:3px;"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3" fill="white"/></svg>${location}
                </td>
                <td class="report-date">${dateStr}</td>
                <td><span class="badge ${badge.cls}">${badge.text}</span></td>
                <td>
                    <button class="view-link" onclick="viewReport('${report.id}')">View Details</button>
                </td>
            </tr>`;
    }).join('');
}

/**
 * Render pagination
 */
function renderDashPagination() {
    const total = filteredDashReports.length;
    const totalPages = Math.ceil(total / DASH_PER_PAGE);
    const start = Math.min((dashCurrentPage - 1) * DASH_PER_PAGE + 1, total);
    const end = Math.min(dashCurrentPage * DASH_PER_PAGE, total);

    const infoEl = document.getElementById('dashPaginationInfo');
    if (total === 0) {
        infoEl.innerHTML = '';
    } else {
        infoEl.innerHTML = `Showing <strong>${start}</strong> to <strong>${end}</strong> of <strong>${total}</strong> reports`;
    }

    const controlsEl = document.getElementById('dashPaginationControls');
    if (totalPages <= 1) {
        controlsEl.innerHTML = '';
        return;
    }

    let html = '';
    html += `<button class="page-btn page-nav ${dashCurrentPage === 1 ? 'disabled' : ''}" ${dashCurrentPage === 1 ? 'disabled' : ''} onclick="dashGoToPage(${dashCurrentPage - 1})">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
    </button>`;

    for (let i = 1; i <= totalPages; i++) {
        html += `<button class="page-btn ${i === dashCurrentPage ? 'active' : ''}" onclick="dashGoToPage(${i})">${i}</button>`;
    }

    html += `<button class="page-btn page-nav ${dashCurrentPage === totalPages ? 'disabled' : ''}" ${dashCurrentPage === totalPages ? 'disabled' : ''} onclick="dashGoToPage(${dashCurrentPage + 1})">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 6 15 12 9 18"/></svg>
    </button>`;

    controlsEl.innerHTML = html;
}

/**
 * Go to page
 */
function dashGoToPage(page) {
    const totalPages = Math.ceil(filteredDashReports.length / DASH_PER_PAGE);
    if (page < 1 || page > totalPages) return;
    dashCurrentPage = page;
    renderRecentReports();
    renderDashPagination();
}

/**
 * Update Status Summary Counts
 */
function updateStatusSummary(reports) {
    const reported = reports.filter(r => ['submitted', 'approved', 'verified'].includes(r.status)).length;
    const inProgress = reports.filter(r => ['assigned', 'in-progress'].includes(r.status)).length;
    const completed = reports.filter(r => ['resolved', 'rejected'].includes(r.status)).length;

    const el = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
    el('reportedCount', reported);
    el('inProgressCount', inProgress);
    el('completedCount', completed);
}

/**
 * Navigate to tracking page with report details
 */
function viewReport(reportId) {
    const report = allReports.find(r => String(r.id) === String(reportId));
    if (!report) {
        console.warn(`Report ${reportId} not found`);
        return;
    }
    renderDetailView(report);
}

/**
 * Close the report detail view and return to dashboard
 */
function closeReportDetail() {
    document.getElementById('reportDetailView').style.display = 'none';
    document.getElementById('dashboardContent').style.display = '';
    document.getElementById('reportNewIssueBtn').style.display = '';
}

/**
 * Render the report detail view
 */
function renderDetailView(report) {
    // Hide dashboard content, show detail
    document.getElementById('dashboardContent').style.display = 'none';
    document.getElementById('reportNewIssueBtn').style.display = 'none';
    document.getElementById('reportDetailView').style.display = '';

    // Report Info – use the same ID format as the table
    document.getElementById('detailReportId').textContent = formatReportId(report.id);
    document.getElementById('detailDate').textContent = report.created_at
        ? new Date(report.created_at).toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: 'numeric' }) +
        ', ' + new Date(report.created_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true })
        : '—';

    // Location — show coordinates cleanly
    document.getElementById('detailLocation').textContent = report.location || 'Unknown';

    // Status badge in top right of info card
    const badge = getStatusBadge(report.status);
    document.getElementById('detailStatusBadge').innerHTML =
        `<span class="badge ${badge.cls}">${badge.text}</span>`;

    // Status text in the grid
    document.getElementById('detailStatusText').textContent = badge.text;

    // Build horizontal timeline
    const steps = ['submitted', 'approved', 'assigned', 'in-progress', 'resolved'];
    const labels = ['Reported', 'Verified', 'Assigned', 'In Progress', 'Completed'];

    let currentStageIndex = steps.indexOf(report.status);
    if (currentStageIndex === -1 && report.status === 'rejected') currentStageIndex = 0;
    if (currentStageIndex === -1) currentStageIndex = 0;

    const timelineEl = document.getElementById('detailTimeline');
    timelineEl.innerHTML = labels.map((label, idx) => {
        const isCompleted = idx < currentStageIndex;
        const isActive = idx === currentStageIndex;

        let dotClass = 'tl-dot--pending';
        let stepClass = '';
        let subText = 'Pending';
        let dotIcon = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><circle cx="12" cy="12" r="4"/></svg>`;

        if (isCompleted || isActive) {
            dotClass = isActive ? 'tl-dot--active' : 'tl-dot--completed';
            stepClass = isActive ? 'tl-active' : 'tl-completed';
            dotIcon = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;

            if (idx === 0 && report.created_at) {
                const d = new Date(report.created_at);
                subText = `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}, ${d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`;
            } else {
                subText = isActive ? 'Current' : 'Done';
            }
        }

        return `
            <div class="tl-step ${stepClass}">
                <div class="tl-dot ${dotClass}">${dotIcon}</div>
                <div class="tl-text">
                    <div class="tl-text__title">${label}</div>
                    <div class="tl-text__sub">${subText}</div>
                </div>
            </div>
        `;
    }).join('');

    // Load before repair image
    const beforeImg = document.getElementById('beforeRepairImg');
    const beforePlaceholder = document.getElementById('beforePlaceholder');
    const imageUrl = report.image_url;

    if (imageUrl) {
        // Check cache first
        if (blobImageCache[imageUrl]) {
            beforeImg.src = blobImageCache[imageUrl];
            beforeImg.style.display = 'block';
            if (beforePlaceholder) beforePlaceholder.style.display = 'none';
        } else {
            // Load via authenticated fetch
            beforePlaceholder.querySelector('span').textContent = 'Loading image...';
            beforePlaceholder.style.display = '';
            beforeImg.style.display = 'none';

            Auth.fetchWithAuth(imageUrl).then(res => {
                if (res.ok) return res.blob();
                throw new Error('Failed');
            }).then(blob => {
                const blobUrl = URL.createObjectURL(blob);
                blobImageCache[imageUrl] = blobUrl;
                beforeImg.src = blobUrl;
                beforeImg.style.display = 'block';
                if (beforePlaceholder) beforePlaceholder.style.display = 'none';
            }).catch(() => {
                beforePlaceholder.querySelector('span').textContent = 'Image not available';
            });
        }
    } else {
        beforeImg.style.display = 'none';
        beforePlaceholder.querySelector('span').textContent = 'No image uploaded';
        beforePlaceholder.style.display = '';
    }

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Make accessible globally
window.viewReport = viewReport;
window.dashGoToPage = dashGoToPage;
window.closeReportDetail = closeReportDetail;
