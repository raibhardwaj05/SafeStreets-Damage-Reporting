// =====================================================
// GLOBAL STATE
// =====================================================
const params = new URLSearchParams(window.location.search);
const reportId = params.get('id');
let reportData = null;
let contractors = [];

// =====================================================
// INIT
// =====================================================
async function initAssignment() {
    Auth.requireRole('official');

    if (reportId) {
        try {
            await loadReport();
            await loadContractors();
            setDefaultDate();
            bindPreviewUpdates();
            updatePreview();
        } catch (err) {
            showModal('Error', err.message);
        }
    } else {
        window.location.href = 'dashboard.html';
    }
}

// =====================================================
// LOAD APPROVED REPORT
// =====================================================
async function loadReport() {
    const res = await Auth.fetchWithAuth(
        `/api/official/reports/${reportId}`
    );

    if (!res.ok) {
        throw new Error('Failed to load report');
    }

    const report = await res.json();

    if (report.status.toUpperCase() !== 'APPROVED') {
        throw new Error('Only approved reports can be assigned');
    }

    reportData = report;
    renderReportDetails(report);
}

// =====================================================
// LOAD CONTRACTORS
// =====================================================
async function loadContractors() {
    const res = await Auth.fetchWithAuth('/api/official/contractors');

    if (!res.ok) {
        throw new Error('Failed to load contractors');
    }

    contractors = await res.json();
    populateContractorSelect();
}

// =====================================================
// RENDER REPORT DETAILS
// =====================================================
function renderReportDetails(report) {
    const locStr = (report.latitude && report.longitude)
        ? `Lat: ${report.latitude.toFixed(4)}, Lng: ${report.longitude.toFixed(4)}`
        : report.location;

    document.getElementById('reportDetails').innerHTML = `
        <div class="report-detail-row"><strong>Report ID:</strong> <span title="${report.id}">${report.id.split('-')[0].substring(0, 8)}</span></div>
        <div class="report-detail-row"><strong>Location:</strong> ${locStr}</div>
        <div class="report-detail-row"><strong>Damage Type:</strong> ${report.damage_type}</div>
        <div class="report-detail-row"><strong>Severity:</strong> ${report.severity}</div>
        <div class="report-detail-row"><strong>Confidence:</strong> ${report.confidence ? (report.confidence * 100).toFixed(2) + '%' : 'N/A'}</div>
    `;
}

// =====================================================
// CONTRACTOR SELECT
// =====================================================
function populateContractorSelect() {
    const select = document.getElementById('contractorSelect');

    contractors.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.name} (${c.specialization}) ⭐ ${c.rating}`;
        select.appendChild(opt);
    });
}

// =====================================================
// DEFAULT DATE
// =====================================================
function setDefaultDate() {
    const date = new Date();
    date.setDate(date.getDate() + 7);
    document.getElementById('completionDate').valueAsDate = date;
}

// =====================================================
// PREVIEW UPDATES
// =====================================================
function bindPreviewUpdates() {
    ['contractorSelect', 'prioritySelect', 'completionDate', 'instructionsInput']
        .forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', updatePreview);
                el.addEventListener('input', updatePreview);
            }
        });
}

function updatePreview() {
    if (!reportData) return;

    const contractorId = document.getElementById('contractorSelect').value;
    const priority = document.getElementById('prioritySelect').value;
    const completionDate = document.getElementById('completionDate').value;
    const instructions = document.getElementById('instructionsInput').value;

    const contractor = contractors.find(c => c.id == contractorId);

    const locStr = (reportData.latitude && reportData.longitude)
        ? `Lat: ${reportData.latitude.toFixed(4)}, Lng: ${reportData.longitude.toFixed(4)}`
        : reportData.location;

    document.getElementById('workOrderPreview').textContent = `
WORK ORDER
========================================
Report ID: ${reportData.id}
Damage Type: ${reportData.damage_type}
Location: ${locStr}

----------------------------------------
Contractor: ${contractor ? contractor.name : '[Not Selected]'}
Priority: ${priority}
Expected Completion: ${completionDate || '[Not Set]'}

----------------------------------------
Special Instructions:
${instructions || 'None'}

========================================
    `.trim();
}

// =====================================================
// ASSIGN WORK ORDER
// =====================================================
async function assignWork() {
    const contractorId = document.getElementById('contractorSelect').value;
    const priority = document.getElementById('prioritySelect').value;
    const completionDate = document.getElementById('completionDate').value;
    const instructions = document.getElementById('instructionsInput').value;

    if (!contractorId || !completionDate) {
        showModal('Validation Error', 'Contractor and completion date are required');
        return;
    }

    try {
        const res = await Auth.fetchWithAuth(
            `/api/official/reports/${reportId}/assign`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    contractor_id: contractorId,
                    priority: priority,
                    expected_completion: completionDate,
                    instructions: instructions
                })
            }
        );

        if (!res.ok) {
            throw new Error('Assignment failed');
        }

        showModal(
            'Success',
            'Work order assigned successfully',
            'success'
        );

        setTimeout(() => {
            window.location.href = 'dashboard.html';
        }, 1500);

    } catch (err) {
        showModal('Error', err.message);
    }
}

// =====================================================
// CANCEL
// =====================================================
function cancelAssignment() {
    window.location.href = 'dashboard.html';
}

// =====================================================
// CONTRACTOR MANAGEMENT (ADD/DELETE)
// =====================================================
let deleteMode = false;

window.toggleDeleteMode = function () {
    deleteMode = !deleteMode;
    const btn = document.getElementById('toggleDeleteBtn');
    const select = document.getElementById('contractorSelect');

    if (deleteMode) {
        btn.textContent = 'Exit Delete Mode';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-secondary');
        showModal('Delete Mode', 'Click on a contractor in the list to delete them.', 'info');
    } else {
        btn.textContent = 'Delete Contractor';
        btn.classList.remove('btn-secondary');
        btn.classList.add('btn-danger');
    }
};

// Handle contractor selection (including deletion)
document.getElementById('contractorSelect').addEventListener('change', async (e) => {
    const contractorId = e.target.value;
    if (!contractorId) return;

    if (deleteMode) {
        const contractor = contractors.find(c => c.id == contractorId);
        if (!contractor) return;

        const confirmDelete = confirm(`Are you sure you want to delete contractor: ${contractor.name}?`);
        if (confirmDelete) {
            try {
                const res = await Auth.fetchWithAuth(`/api/official/contractors/${contractorId}`, {
                    method: 'DELETE'
                });

                if (res.ok) {
                    showModal('Deleted', 'Contractor removed successfully', 'success');
                    await loadContractors(); // Refresh list
                    e.target.value = ''; // Reset select
                } else {
                    const err = await res.json();
                    throw new Error(err.msg || 'Deletion failed');
                }
            } catch (err) {
                showModal('Error', err.message);
            }
        }
    }
});

// =====================================================
// INIT CALL
// =====================================================
document.addEventListener('DOMContentLoaded', initAssignment);
