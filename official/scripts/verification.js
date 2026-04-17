// =====================================================
// LEAFLET MAP CONFIG
// =====================================================
let mapInstance = null;


// =====================================================
// INIT
// =====================================================
// =====================================================
// INIT
// =====================================================
document.addEventListener('DOMContentLoaded', () => {
    Auth.requireRole('official');

    const params = new URLSearchParams(window.location.search);
    const reportId = params.get('id');

    if (reportId) {
        window.currentReportId = reportId;
        loadReport();
    } else {
        window.location.href = 'dashboard.html';
    }
});

// =====================================================
// LOAD REPORT DATA
// =====================================================
async function loadReport() {
    const infoContainer = document.getElementById('reportInfo');
    if (infoContainer) {
        infoContainer.innerHTML = '<div class="spinner"></div> Loading report details...';
    }

    try {
        const response = await Auth.fetchWithAuth(
            `/api/official/reports/${window.currentReportId}`
        );

        if (!response.ok) {
            throw new Error('Failed to load report');
        }

        const report = await response.json();
        populateReport(report);

        // Kick-off Agent 3 in background — non-blocking, shows its own spinner
        checkAccountability();

    } catch (error) {
        console.error(error);
        if (infoContainer) {
            infoContainer.innerHTML = `<div style="color:red;">Error: ${error.message}</div>`;
        }
        showModal('Error', error.message);
    }
}

// =====================================================
// LOAD MAP WITH MARKERS (LEAFLET + OSM)
// =====================================================
function loadMap(lat, lng, detectionCount) {

    if (mapInstance) return; // prevent re-init

    document.getElementById('mapCoords').textContent =
        `Lat: ${lat}, Lng: ${lng}`;

    mapInstance = L.map('map', {
        zoomControl: true,     //✅ shows + / − buttons
        dragging: true,        // allow pan
        scrollWheelZoom: false // optional
    }).setView([lat, lng], 15);



    // OpenStreetMap tiles (FREE)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(mapInstance);

    // Markers
    let pins = 1;
    if (typeof detectionCount === 'number' && detectionCount > 1) {
        pins = detectionCount;
    }
    for (let i = 0; i < pins; i++) {
        L.marker([lat, lng])
            .addTo(mapInstance)
            .bindPopup('Reported Damage Location');
    }

    // OPTIONAL POLISH
    mapInstance.setMinZoom(10);
    mapInstance.setMaxZoom(18);

    // Fix layout render issues
    setTimeout(() => {
        mapInstance.invalidateSize();
    }, 100);
}


// =====================================================
// POPULATE UI
// =====================================================
async function populateReport(report) {
    // IMAGE (SECURE FETCH)
    const img = document.getElementById('reportImage');

    if (img) {
        img.style.display = 'none';
    }

    if (report.image_url && img) {
        try {
            const response = await Auth.fetchWithAuth(report.image_url);
            if (response.ok) {
                const blob = await response.blob();
                img.src = URL.createObjectURL(blob);
                img.style.display = 'block';
            }
        } catch (err) {
            console.error('Image load failed');
        }
    }

    // AI RESULT
    const wlogRiskHtml = (report.waterlogging_pothole_risk != null)
        ? `<div class="ai-result-item" style="
                margin-top: 10px;
                padding: 10px 14px;
                background: linear-gradient(135deg, #fff7ed, #ffedd5);
                border: 1.5px solid #f97316;
                border-radius: 10px;
                display: flex;
                align-items: center;
                gap: 10px;
            ">
                <span style="font-size: 1.4rem;">⚠️</span>
                <div>
                    <div style="font-weight: 700; color: #c2410c; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.05em;">Pothole Formation Risk</div>
                    <div style="font-size: 1.1rem; font-weight: 700; color: #ea580c;">
                        ${report.waterlogging_pothole_risk.toFixed(1)}% chance of a pothole forming here (30-day forecast)
                    </div>
                    <div style="font-size: 0.78rem; color: #9a3412; margin-top: 2px;">
                        Based on historical Poisson recurrence model — adjusted for sub-base saturation
                    </div>
                </div>
            </div>`
        : '';

    const aiHtml = `
        <div class="ai-result-item">
            <strong>Damage Type:</strong> ${report.damage_type || 'N/A'}
        </div>
        <div class="ai-result-item">
            <strong>Confidence:</strong>
            ${report.confidence !== null
            ? (report.confidence * 100).toFixed(2) + '%'
            : 'N/A'}
        </div>
        <div class="ai-result-item">
            <strong>Severity:</strong> ${report.severity || 'N/A'}
        </div>
        ${wlogRiskHtml}
    `;

    const aiResultEl = document.getElementById('aiResult');
    if (aiResultEl) {
        aiResultEl.innerHTML = aiHtml;
    }

    // LOCATION + MAP
    if (report.latitude != null && report.longitude != null) {
        loadMap(report.latitude, report.longitude, 1);
    } else {
        document.getElementById('mapCoords').textContent =
            'Location not available';
    }


    // REPORT INFO
    document.getElementById('reportInfo').innerHTML = `
        <div class="report-info-item"><strong>Report ID:</strong> <span title="${report.id}">${report.id.split('-')[0].substring(0, 8)}</span></div>
        <div class="report-info-item"><strong>Reported By:</strong> ${report.reported_by || 'Citizen'}</div>
        <div class="report-info-item"><strong>Date:</strong> ${new Date(report.created_at).toLocaleString()}</div>
        <div class="report-info-item"><strong>Status:</strong> ${report.status}</div>
    `;
}

// =====================================================
// AGENT 3 — ACCOUNTABILITY INVESTIGATION
// =====================================================
async function checkAccountability() {
    const panel = document.getElementById('accountabilityPanel');
    if (!panel) return;

    // Show loading state right away
    panel.innerHTML = `
        <div class="accountability-loading">
            <div class="acct-spinner"></div>
            <span>Running Agent 3 Investigation\u2026 (Gemini AI)</span>
        </div>
    `;

    try {
        const response = await Auth.fetchWithAuth(
            `/api/official/reports/${window.currentReportId}/accountability`
        );

        if (!response.ok) {
            throw new Error(`Server error ${response.status}`);
        }

        const data = await response.json();
        renderAccountability(data, panel);

    } catch (error) {
        console.error('Accountability check failed:', error);
        panel.innerHTML = `
            <div class="accountability-error">
                \u26A0\uFE0F Could not run accountability check: ${error.message}
            </div>
        `;
    }
}

function renderAccountability(data, panel) {
    const stmt = data.accountability_statement || 'No statement generated.';
    const top  = data.top_match;

    let badgeHtml = '';
    if (top && top.department) {
        const confidenceClass =
            top.confidence_label === 'HIGH'   ? 'acct-badge--high'   :
            top.confidence_label === 'MEDIUM' ? 'acct-badge--medium' :
                                                'acct-badge--low';

        badgeHtml = `
            <div class="acct-badge ${confidenceClass}">
                <div class="acct-badge-icon">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none"
                         stroke="currentColor" stroke-width="2.2">
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                    </svg>
                </div>
                <div class="acct-badge-body">
                    <span class="acct-badge-label">Accountable Department</span>
                    <span class="acct-badge-dept">${top.department}</span>
                    <span class="acct-badge-conf">${top.confidence_label} confidence
                        &bull; ${top.distance_meters ?? '?'}m away</span>
                </div>
            </div>
        `;
    } else {
        badgeHtml = `
            <div class="acct-badge acct-badge--none">
                <div class="acct-badge-icon">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none"
                         stroke="currentColor" stroke-width="2.2">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                </div>
                <div class="acct-badge-body">
                    <span class="acct-badge-label">No Match Found</span>
                    <span class="acct-badge-dept" style="font-size:0.85rem;font-weight:500;">No government work orders detected within 200 m.</span>
                </div>
            </div>
        `;
    }

    const evidenceHtml = data.evidence
        ? `<div class="acct-evidence"><strong>Evidence:</strong> ${data.evidence}</div>`
        : '';

    panel.innerHTML = `
        ${badgeHtml}
        <div class="acct-statement">${stmt}</div>
        ${evidenceHtml}
    `;
}

// =====================================================
// VERIFY ACTIONS
// =====================================================
async function submitVerification(status) {
    const reason = document.getElementById('reasonInput').value.trim();

    if (!reason) {
        showModal('Reason Required', 'Please provide a reason');
        return;
    }

    try {
        const response = await Auth.fetchWithAuth(
            `/api/official/reports/${window.currentReportId}/verify`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status, reason })
            }
        );

        if (!response.ok) {
            throw new Error('Verification failed');
        }

        showModal('Success', `Report ${status} successfully`, 'success');

        setTimeout(() => {
            // Redirect back to verification list
            window.location.href = 'verification.html';
        }, 1500);

    } catch (error) {
        console.error(error);
        showModal('Error', error.message);
    }
}

function approveReport() {
    submitVerification('approved');
}

function rejectReport() {
    submitVerification('rejected');
}

// EXPOSE
window.approveReport = approveReport;
window.rejectReport = rejectReport;
window.checkAccountability = checkAccountability;
