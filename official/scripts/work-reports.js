// =====================================================
// OFFICIAL AUTH GUARD
// =====================================================
Auth.requireRole('official');

// =====================================================
// STATE
// =====================================================
let workReports = [];
let currentReports = [];

// =====================================================
// INIT
// =====================================================
document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
    setupDropZone();
});

async function initDashboard() {
    await loadReports();
    updateKPIs();
    renderTable();
}

// =====================================================
// LOAD REPORTS (CORRECT API)
// =====================================================
async function loadReports() {
    const tbody = document.getElementById('reportsTableBody');
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:2rem;"><div class="spinner"></div> Loading reports...</td></tr>`;

    try {
        const response = await Auth.fetchWithAuth('/api/official/work-reports');

        if (!response.ok) throw new Error('Failed to fetch reports');

        workReports = await response.json();
        currentReports = [...workReports];
        renderTable();
    } catch (error) {
        console.error('Error loading reports:', error);
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:2rem;color:red;">Error: ${error.message}</td></tr>`;
        showModal('Error', error.message);
    }
}

// =====================================================
// KPIs (MATCH BACKEND STATUSES)
// =====================================================
function updateKPIs() {
    document.getElementById('totalNotices').textContent = workReports.length;

    document.getElementById('pendingVerify').textContent =
        workReports.filter(r => r.status === 'pending').length;

    document.getElementById('criticalWork').textContent = '—';   // Not applicable to work notices
    document.getElementById('activeDiversions').textContent = '—'; // Not applicable to work notices
}


// =====================================================
// TABLE
// =====================================================
function renderTable() {
    const tbody = document.getElementById('reportsTableBody');

    if (currentReports.length === 0) {
        tbody.innerHTML = `
                <tr>
                    <td colspan="9" style="text-align:center;padding:2rem;">
                        No notices found
                    </td>
                </tr>`;
        return;
    }

    tbody.innerHTML = currentReports.map(report => `
            <tr>
                <td title="${report.notice_id || '-'}"><strong>${report.notice_id ? report.notice_id.split('-')[0].substring(0, 8) : '-'}</strong></td>
                <td>${report.location || '-'}</td>
                <td>${report.department || '-'}</td>
                <td>${report.work_type || '-'}</td>
                <td>${new Date(report.created_at).toLocaleDateString()}</td>
                <td>-</td>        <!-- Traffic Div (not applicable) -->
                <td>-</td>        <!-- Severity (not applicable) -->
                <td>${report.status}</td>
                <td>
                    <button class="btn btn-primary btn-sm"
                        onclick="openSidePanel('${report.id}')">
                        View
                    </button>
                </td>
            </tr>
        `).join('');
}


// =====================================================
// FILTERS
// =====================================================
function applyFilters() {
    const dept = document.getElementById('deptFilter').value;
    const status = document.getElementById('statusFilter').value;
    const startDate = document.getElementById('startDateFilter').value;
    const endDate = document.getElementById('endDateFilter').value;

    currentReports = workReports.filter(r => {
        const matchesDept = !dept || r.department === dept;
        const matchesStatus = !status || r.status === status;

        let matchesDate = true;
        if (r.created_at) {
            const reportDate = new Date(r.created_at).toISOString().split('T')[0];
            if (startDate && reportDate < startDate) matchesDate = false;
            if (endDate && reportDate > endDate) matchesDate = false;
        }

        return matchesDept && matchesStatus && matchesDate;
    });

    renderTable();
}

function clearFilters() {
    document.getElementById('deptFilter').value = '';
    document.getElementById('statusFilter').value = '';
    document.getElementById('startDateFilter').value = '';
    document.getElementById('endDateFilter').value = '';
    currentReports = [...workReports];
    renderTable();
}

// =====================================================
// NAVIGATION (CRITICAL FIX)
// =====================================================
function goToVerification(reportId) {
    const report = workReports.find(r => r.id === reportId);
    let isDashcam = false;
    if (report) {
        if (report.report_source === 'dashcam') {
            isDashcam = true;
        } else if (report.image_url && report.image_url.includes('dashcam_first_')) {
            isDashcam = true;
        }
    }
    const page = isDashcam ? 'dashcam-verification.html' : 'verification.html';
    window.location.href = `${page}?id=${reportId}`;
}

// =====================================================
// SIDE PANEL (SAFE)
// =====================================================
function openSidePanel(reportId) {
    const report = workReports.find(r => r.id === reportId);
    if (!report) return;

    document.getElementById('panelContent').innerHTML = `
            <p><strong>Notice ID:</strong> ${report.notice_id || report.id}</p>
            <p><strong>Department:</strong> ${report.department}</p>
            <p><strong>Work Type:</strong> ${report.work_type}</p>
            <p><strong>Location:</strong> ${report.location}</p>
            <p><strong>Executing Agency:</strong> ${report.executing_agency || '-'}</p>
            <p><strong>Contractor Contact:</strong> ${report.contractor_contact || '-'}</p>
            <p><strong>Status:</strong> ${report.status}</p>
        `;

    document.getElementById('panelFooter').innerHTML = `
            <button class="btn btn-secondary" onclick="closeSidePanel()">Close</button>
            ${report.pdf_url ? `
                <button class="btn btn-primary"
                    onclick="downloadNotice('${report.id}')">
                    ⬇ Download PDF
                </button>
            ` : ''}
        `;

    document.getElementById('sidePanel').classList.add('open');
    document.getElementById('sidePanelOverlay').classList.add('open');
}


function closeSidePanel() {
    document.getElementById('sidePanel').classList.remove('open');
    document.getElementById('sidePanelOverlay').classList.remove('open');
}

async function downloadNotice(reportId) {
    try {
        const response = await Auth.fetchWithAuth(`/api/official/work-reports/${reportId}/download`);

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.msg || 'Download failed');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = `work-notice-${reportId}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();

        window.URL.revokeObjectURL(url);
    } catch (error) {
        showModal('Download Failed', error.message);
    }
}


// =====================================================
// CREATE REPORT MODAL
// =====================================================
function openCreateReportModal() {
    document.getElementById('createReportModal').style.display = 'flex';
}

function closeCreateReportModal() {
    document.getElementById('createReportModal').style.display = 'none';
}

window.openCreateReportModal = openCreateReportModal;
window.closeCreateReportModal = closeCreateReportModal;


// =====================================================
// DROP ZONE SETUP
// =====================================================
function setupDropZone() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');

    if (!dropZone || !fileInput) return;

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');

        const file = e.dataTransfer.files[0];
        if (file) uploadNoticePDF(file);
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files[0]) uploadNoticePDF(fileInput.files[0]);
    });
}

// =====================================================
// UPLOAD PDF
// =====================================================
async function uploadNoticePDF(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showModal('Invalid File', 'Please upload a PDF file only.');
        return;
    }

    const extractionStatus = document.getElementById('extractionStatus');
    extractionStatus.style.display = 'flex';

    const formData = new FormData();
    formData.append('pdf', file);

    try {
        const response = await Auth.fetchWithAuth('/api/official/work-reports/upload', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.msg || 'Upload failed');
        }

        showModal('Success', 'Notice uploaded and extracted successfully!');
        closeCreateReportModal();
        await loadReports();
        updateKPIs();
        renderTable();

    } catch (err) {
        console.error('Upload error:', err);
        showModal('Error', err.message);
    } finally {
        extractionStatus.style.display = 'none';
        document.getElementById('fileInput').value = ''; // Reset
    }
}


// =====================================================
// EXPORT GLOBALS
// =====================================================
window.goToVerification = goToVerification;
window.openSidePanel = openSidePanel;
window.closeSidePanel = closeSidePanel;
window.clearFilters = clearFilters;
window.downloadNotice = downloadNotice;

