// Work Monitoring Screen JavaScript for Citizen Reports

// Data fetched from API
let workOrdersData = [];
let currentWork = null;
let currentReport = null;

/**
 * Initialize monitoring page
 */
async function initMonitoring() {
    Auth.requireRole('official');

    const params = new URLSearchParams(window.location.search);
    const id = params.get('id');

    if (!id) {
        window.location.href = 'dashboard.html';
        return;
    }

    await fetchWorkOrders();
    await fetchReportDetails(id);

    // Try to find matching work order
    currentWork = workOrdersData.find(w => w.id === id || w.reportId === id);

    if (currentWork || currentReport) {
        // Check for persisted state in IndexedDB
        const savedState = await ReportStorage.get(id);
        if (savedState) {
            if (currentReport) {
                currentReport.status = 'resolved';
                currentReport.resolved_at = savedState.resolvedAt;
                currentReport.persistedDescription = savedState.description;
                currentReport.persistedOfficer = savedState.officer;
                currentReport.persistedAfterPhoto = savedState.afterPhoto;
            }
        }

        loadWorkDetails();
        
        // If persisted, show the success summary directly
        if (savedState) {
            showResolutionSummary();
        }
    } else {
        // Fallback
        document.getElementById('activeWorksList').style.display = 'block';
        renderActiveWorks();
    }
}

/**
 * Show resolution summary when report is resolved (persisted)
 */
function showResolutionSummary() {
    const completionSection = document.querySelector('.completion-section');
    if (completionSection && currentReport) {
        completionSection.innerHTML = `
            <h2>Report Resolved</h2>
            <div class="completion-card stat-card" style="background: #f0fdf4; border-color: #22c55e; padding: 1.5rem; border-radius: 12px; margin-top: 1rem;">
                <div style="display: flex; flex-direction: column; gap: 0.5rem; color: #166534;">
                    <div style="display: flex; align-items: center; gap: 0.75rem;">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                        <span style="font-weight: 700; font-size: 1.1rem;">Issue Successfully Resolved</span>
                    </div>
                    <p style="margin: 0.5rem 0 0.25rem 0; font-size: 0.95rem; opacity: 0.9;"><strong>Work Summary:</strong> ${currentReport.persistedDescription || 'Issue resolved according to standards.'}</p>
                    <p style="margin: 0; font-size: 0.9rem; font-weight: 600; opacity: 0.8;">Verified by: ${currentReport.persistedOfficer || 'Official'}</p>
                </div>
            </div>
        `;
        
        // Also update the After image if saved
        const afterImg = document.getElementById('afterPhoto');
        if (afterImg && currentReport.persistedAfterPhoto) {
            afterImg.src = currentReport.persistedAfterPhoto;
        }
    }
}

async function fetchReportDetails(id) {
    try {
        const response = await Auth.fetchWithAuth(`/api/official/reports/${id}`);
        if (response.ok) {
            currentReport = await response.json();
        }
    } catch (e) {
        console.error("Fetch Report Error", e);
    }
}

async function fetchWorkOrders() {
    try {
        const response = await Auth.fetchWithAuth('/api/official/work-reports');
        if (response.ok) {
            const data = await response.json();
            // Transform
            workOrdersData = data.map(r => ({
                id: r.id,
                reportId: r.id, 
                location: r.location,
                contractor: (r.contractor && r.contractor.name) || 'Not Assigned',
                status: r.status === 'resolved' ? 'completed' : (r.status === 'assigned' ? 'in-progress' : 'pending'),
                statusText: r.status === 'assigned' ? 'In Progress' : (r.status === 'verified' ? 'Pending' : r.status),
                assignedDate: r.created_at,
                expectedCompletion: 'TBD',
                beforePhoto: 'https://via.placeholder.com/600x400/cccccc/ffffff?text=No+Image',
                afterPhoto: null,
                logs: []
            }));
        }
    } catch (e) {
        console.error("Fetch Error", e);
    }
}

/**
 * Load work details
 */
function loadWorkDetails() {
    // Show work details section
    document.getElementById('workDetails').style.display = 'block';
    document.getElementById('activeWorksList').style.display = 'none';

    // Render timeline
    renderTimeline();

    // Render status indicator
    renderStatusIndicator();

    // Render photos
    renderPhotos();

    // Render logs
    renderLogs();

    // Show/hide mark completed button
    if (currentWork && currentWork.status === 'in-progress') {
        document.getElementById('markCompletedBtn').style.display = 'inline-block';
    } else {
        document.getElementById('markCompletedBtn').style.display = 'none';
    }
}

/**
 * Render status timeline
 */
function renderTimeline() {
    const timelineContainer = document.getElementById('statusTimeline');
    if (!timelineContainer || !currentReport) return;

    const steps = ['submitted', 'approved', 'assigned', 'in-progress', 'resolved'];
    const labels = ['Reported', 'Verified', 'Assigned', 'In Progress', 'Completed'];

    let currentStageIndex = steps.indexOf(currentReport.status);
    if (currentStageIndex === -1) {
        if (currentReport.status === 'verified' || currentReport.status === 'approved') currentStageIndex = 1;
        else if (currentReport.status === 'assigned') currentStageIndex = 3; 
        else if (currentReport.status === 'in-progress') currentStageIndex = 3;
        else if (currentReport.status === 'resolved') currentStageIndex = 4;
        else if (currentReport.status === 'rejected') currentStageIndex = 0;
        else currentStageIndex = 0;
    } else if (currentReport.status === 'assigned') {
        currentStageIndex = 3; 
    }

    const formatDate = (dateStr) => {
        if (!dateStr) return null;
        return new Date(dateStr).toLocaleString('en-US', { 
            year: 'numeric', 
            month: 'numeric', 
            day: 'numeric', 
            hour: 'numeric', 
            minute: 'numeric', 
            hour12: true 
        });
    };

    const timelineData = labels.map((item, idx) => {
        let dateDisplay = 'Pending';
        if (idx <= currentStageIndex) {
            let timestamp = currentReport.created_at; 

            if (idx === 1) {
                timestamp = currentReport.verified_at || currentReport.created_at;
            } else if (idx === 2) {
                timestamp = currentReport.assigned_at || (currentWork ? currentWork.assignedDate : currentReport.created_at);
            } else if (idx === 3) {
                timestamp = currentReport.in_progress_at || (currentWork ? currentWork.assignedDate : currentReport.created_at);
            } else if (idx === 4) {
                timestamp = currentReport.resolved_at || currentReport.created_at;
            }

            dateDisplay = formatDate(timestamp);
        }

        return {
            step: item,
            date: dateDisplay,
            completed: idx <= currentStageIndex
        };
    });

    timelineContainer.innerHTML = timelineData.map((item, index) => {
        let dotClass = 'timeline-dot';
        if (item.completed) dotClass += ' completed-active';

        let iconHtml = '';
        if (item.completed) {
            iconHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
        } else {
            iconHtml = `<div style="width: 6px; height: 6px; border-radius: 50%; background-color: #94a3b8;"></div>`;
        }

        return `
            <div class="timeline-item">
                <div class="${dotClass}">
                    ${iconHtml}
                </div>
                <div class="timeline-content-text">
                    <div class="timeline-title">${item.step}</div>
                    <div class="timeline-desc">${item.date}</div>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Render status indicator
 */
function renderStatusIndicator() {
    const indicator = document.getElementById('workStatusIndicator');
    if (!indicator) return;

    if (currentWork) {
        indicator.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 1rem;">
                <div>
                    <h3 style="margin: 0; color: #1e293b; font-size: 1.2rem;">Work Order #<span title="${currentWork.id}">${currentWork.id.split('-')[0].substring(0, 8)}</span></h3>
                    <p style="margin: 0.25rem 0 0 0; color: #64748b; font-size: 0.9rem;">Report Ref: <span title="${currentWork.reportId}">${currentWork.reportId.split('-')[0].substring(0, 8)}</span></p>
                </div>
                <div class="status-badge ${currentWork.status}" style="margin: 0;">${currentWork.statusText}</div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; text-align: left;">
                <div>
                    <span style="display: block; font-size: 0.85rem; color: #64748b; margin-bottom: 0.25rem; font-weight: 600; text-transform: uppercase;">Contractor</span>
                    <strong style="color: #1e293b; font-size: 1.05rem;">${currentWork.contractor}</strong>
                </div>
                <div>
                    <span style="display: block; font-size: 0.85rem; color: #64748b; margin-bottom: 0.25rem; font-weight: 600; text-transform: uppercase;">Assigned Date</span>
                    <strong style="color: #1e293b; font-size: 1.05rem;">${currentWork.assignedDate}</strong>
                </div>
                <div>
                    <span style="display: block; font-size: 0.85rem; color: #64748b; margin-bottom: 0.25rem; font-weight: 600; text-transform: uppercase;">Expected Completion</span>
                    <strong style="color: #1e293b; font-size: 1.05rem;">${currentWork.expectedCompletion}</strong>
                </div>
            </div>
        `;
    } else if (currentReport) {
        const reportIdFull = currentReport.id || '';
        const reportIdDisplay = reportIdFull ? reportIdFull.split('-')[0].substring(0, 8) : 'Unknown';
        
        const statusText = (currentReport.status || 'pending').charAt(0).toUpperCase() + (currentReport.status || 'pending').slice(1);
        const statusClass = ['in-progress', 'assigned'].includes(currentReport.status) ? 'in-progress' :
            (currentReport.status === 'resolved' ? 'completed' : 'pending');

        indicator.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 1rem;">
                <div>
                    <h3 style="margin: 0; color: #1e293b; font-size: 1.2rem;">Report #<span title="${reportIdFull}">${reportIdDisplay}</span></h3>
                    <p style="margin: 0.25rem 0 0 0; color: #64748b; font-size: 0.9rem;">Filed by: ${currentReport.reported_by || 'Unknown'}</p>
                </div>
                <div class="status-badge ${statusClass}" style="margin: 0;">${statusText}</div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; text-align: left;">
                <div>
                    <span style="display: block; font-size: 0.85rem; color: #64748b; margin-bottom: 0.25rem; font-weight: 600; text-transform: uppercase;">Location</span>
                    <strong style="color: #1e293b; font-size: 1.05rem;">${currentReport.location || 'N/A'}</strong>
                </div>
            </div>
        `;
    }
}

/**
 * Render photos dynamically from report data
 */
async function renderPhotos() {
    const beforeImg = document.getElementById('beforePhoto');
    const afterImg = document.getElementById('afterPhoto');

    if (!beforeImg || !afterImg) return;

    // 1. Try to get the "Before" image from the currentReport object
    if (currentReport && currentReport.image_url) {
        try {
            const response = await Auth.fetchWithAuth(currentReport.image_url);
            if (response.ok) {
                const blob = await response.blob();
                beforeImg.src = URL.createObjectURL(blob);
                beforeImg.style.display = 'block';
            } else {
                beforeImg.src = currentReport.image_url;
            }
        } catch (err) {
            console.error('Before Image load failed', err);
            beforeImg.src = 'https://via.placeholder.com/600x400/f1f5f9/94a3b8?text=Image+Load+Failed';
        }
    }
    // Fallback to currentWork data if currentReport isn't populated
    else if (currentWork && currentWork.beforePhoto) {
        beforeImg.src = currentWork.beforePhoto;
    }
    // Final fallback: Placeholder
    else {
        beforeImg.src = 'https://via.placeholder.com/600x400/f1f5f9/94a3b8?text=Original+Report+Photo+Missing';
    }

    // 2. Handle the "After" image (Repair documentation)
    // If not persisted, check currentWork
    if (currentReport && currentReport.persistedAfterPhoto) {
        afterImg.src = currentReport.persistedAfterPhoto;
    } else if (currentWork && currentWork.afterPhoto) {
        afterImg.src = currentWork.afterPhoto;
    } else {
        afterImg.src = 'https://via.placeholder.com/600x400/f1f5f9/94a3b8?text=Repair+Photo+Pending';
    }
}

/**
 * Render logs
 */
function renderLogs() {
    const container = document.getElementById('logsContainer');
    if (!container) return;

    if (currentWork && currentWork.logs && currentWork.logs.length > 0) {
        container.innerHTML = currentWork.logs.map(log => `
            <div class="log-entry">
                <div class="log-entry-header">
                    <span>🕐 ${log.timestamp}</span>
                    <span>📍 ${log.location}</span>
                </div>
                <div class="log-entry-details">
                    <strong>Action:</strong> ${log.action}<br>
                    <strong>Contractor:</strong> ${log.contractor}
                </div>
            </div>
        `).join('');
    } else {
        container.innerHTML = '<p style="color: #999; text-align: center;">No logs available for this work order.</p>';
    }
}

/**
 * Render active works grid
 */
function renderActiveWorks() {
    const grid = document.getElementById('worksGrid');
    if (!grid) return;

    if (workOrdersData.length === 0) {
        grid.innerHTML = '<p style="color: #999; grid-column: 1/-1; text-align: center;">No active work orders found.</p>';
        return;
    }

    grid.innerHTML = workOrdersData.map(work => `
        <div class="work-card" onclick="selectWork('${work.id}')">
            <div class="work-card-header">
                <div class="work-card-title">${work.id}</div>
                <span class="status-badge ${work.status}">${work.statusText}</span>
            </div>
            <div class="work-card-meta">
                <strong>Report:</strong> ${work.reportId}<br>
                <strong>Location:</strong> ${work.location}<br>
                <strong>Contractor:</strong> ${work.contractor}<br>
                <strong>Expected:</strong> ${work.expectedCompletion}
            </div>
        </div>
    `).join('');
}

/**
 * Select work from grid
 */
function selectWork(workId) {
    window.location.href = `monitoring.html?id=${workId}`;
}

/**
 * Mark work as completed
 */
function markCompleted() {
    if (!currentWork) return;

    showConfirm('Confirm Completion', `Mark work order ${currentWork.id} as completed?`, () => {
        showAlert('Work Completed', `Work order ${currentWork.id} has been marked as completed.\n\nRedirecting to dashboard...`, 'success', () => {
            window.location.href = 'dashboard.html';
        });
    });
}

/**
 * Handle "After" image upload preview
 */
function handleAfterImageUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Check if it's an image
    if (!file.type.startsWith('image/')) {
        showAlert('Invalid File', 'Please upload an image file.', 'error');
        return;
    }

    const reader = new FileReader();
    reader.onload = function(e) {
        const afterImg = document.getElementById('afterPhoto');
        if (afterImg) {
            const imageData = e.target.result;
            afterImg.src = imageData;
            
            // Store temporarily in currentReport for saving later
            if (!currentReport) currentReport = {};
            currentReport.tempAfterPhoto = imageData;
            currentReport.fileToUpload = file;
            
            // Enable verification checkbox
            const checkbox = document.getElementById('completionCheckbox');
            const wrapper = document.getElementById('checkboxWrapper');
            const helper = document.getElementById('uploadHelperText');
            
            if (checkbox && wrapper) {
                checkbox.disabled = false;
                wrapper.classList.remove('disabled');
                if (helper) helper.style.display = 'none';
            }
            
            showAlert('Success', 'Repair photo uploaded. You can now verify the report.', 'success');
        }
    };
    reader.readAsDataURL(file);
}

/**
 * Toggle Submit Button based on checkbox
 */
function toggleSubmitButton() {
    const checkbox = document.getElementById('completionCheckbox');
    const submitBtn = document.getElementById('submitReportBtn');
    if (checkbox && submitBtn) {
        submitBtn.disabled = !checkbox.checked;
    }
}

/**
 * Submit final report and resolve it
 */
async function submitFinalReport() {
    const descriptionField = document.getElementById('completionDescription');
    const description = descriptionField ? descriptionField.value : '';
    const officerName = localStorage.getItem('user_name') || 'Official';
    const resolvedAt = new Date().toISOString();
    
    // Safety check for ID
    const reportId = (currentReport && currentReport.id) || (new URLSearchParams(window.location.search)).get('id');

    if (!reportId) {
        showAlert('Error', 'Missing report identifier.', 'error');
        return;
    }

    try {
        const formData = new FormData();
        formData.append('description', description);
        if (currentReport && currentReport.fileToUpload) {
            formData.append('after_image', currentReport.fileToUpload);
        }

        const response = await Auth.fetchWithAuth(`/api/official/reports/${reportId}/resolve`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.msg || 'Resolution failed');
        }

        // Save to IndexedDB for persistence backup
        const stateToSave = {
            description: description,
            officer: officerName,
            resolvedAt: resolvedAt,
            afterPhoto: (currentReport && currentReport.tempAfterPhoto) || null
        };
        await ReportStorage.save(reportId, stateToSave);
        
        // Fetch updated report from backend
        await fetchReportDetails(reportId);

        // Refresh UI
        renderTimeline();
        renderStatusIndicator();
        renderPhotos();
        
        // Show success summary
        showResolutionSummary();
        
        showAlert('Success', 'Report has been marked as completed!', 'success');
        
    } catch (error) {
        console.error('Error submitting report:', error);
        showAlert('Error', 'Failed to update report status.', 'error');
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', initMonitoring);
