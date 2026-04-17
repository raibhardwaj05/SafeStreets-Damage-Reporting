// Report Damage Screen JavaScript
// Handles: Photo tab (existing), Video tab, Realtime tab

// =====================================================
// SHARED STATE
// =====================================================
let selectedFile = null;
let detectionResult = null;
let annotatedImageB64 = null;  // stores base64 annotated image from /detect

// Shared GPS state — acquired once, used by all tabs
let gpsData = { lat: null, lng: null, locationText: 'Acquiring location...' };

// =====================================================
// INIT
// =====================================================
document.addEventListener('DOMContentLoaded', async () => {
    Auth.requireAuth();
    initReportForm();
    initRealtimeTab();

    // Auto start dashcam detection
    setTimeout(() => {
        startRealtime('environment'); // start with back camera
    }, 500);
});

// =====================================================
// TAB SWITCHING
// =====================================================
function switchTab(tab) {
    // Deactivate all
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

    // Activate selected
    document.getElementById('tab' + tab.charAt(0).toUpperCase() + tab.slice(1)).classList.add('active');
    document.getElementById('panel' + tab.charAt(0).toUpperCase() + tab.slice(1)).classList.add('active');

    // Stop realtime if switching away
    if (tab !== 'realtime' && rtIsRunning) {
        stopRealtime();
    }
}

// =====================================================
// =====================================================
// TAB 1: PHOTO (existing logic, unchanged)
// =====================================================
// =====================================================

function initReportForm() {
    const rtLocDisplay = document.getElementById('rtLocationDisplay');

    function setAllLocationDisplays(text) {
        if (rtLocDisplay) rtLocDisplay.textContent = text;
    }

    if (!("geolocation" in navigator)) {
        gpsData.locationText = 'Geolocation not supported';
        setAllLocationDisplays(gpsData.locationText);
        return;
    }

    setAllLocationDisplays('Acquiring GPS...');

    const handlePosition = (position) => {
        const { latitude, longitude } = position.coords;
        gpsData.lat = latitude;
        gpsData.lng = longitude;
        gpsData.locationText = `Lat: ${latitude.toFixed(5)}, Lng: ${longitude.toFixed(5)}`;
        setAllLocationDisplays(gpsData.locationText);
    };

    const handleError = () => {
        gpsData.locationText = 'Location permission REQUIRED';
        setAllLocationDisplays(gpsData.locationText);
        showAlert("Location Required", "Please enable GPS and allow precise location.", "warning");
    };

    // Initial fix to quickly get a location
    navigator.geolocation.getCurrentPosition(
        handlePosition,
        handleError,
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );

    // Continuous updates while driving so distance-based auto-submit works
    navigator.geolocation.watchPosition(
        handlePosition,
        handleError,
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 1000 }
    );
}

// =====================================================
// =====================================================
// TAB 3: REALTIME
// =====================================================
// =====================================================

let rtStream = null;
let rtIsRunning = false;
let rtInterval = null;
let rtRequestInFlight = false;
let rtTotalDetections = 0;
let rtFramesSent = 0;
let rtCanvas = null;
let rtCtx = null;
let rtCurrentFacingMode = 'environment'; // 'environment' = back, 'user' = front
let rtSocket = null;

// Dynamic FPS control
let rtDynamicDelay = 50;     // starting delay (~20 FPS)
const rtMinDelay = 30;       // max speed (~30 FPS)
const rtMaxDelay = 500;       // slowest (~2 FPS)

// 4 seconds cool down period between reports
let rtLastDetectionTime = 0;
const RT_DETECTION_COOLDOWN = 4000;

// Per-detection report submission
const RT_CONF_THRESHOLD = 0.4;
let rtSessionLog = []; // tracks all saved reports this session


function initRealtimeTab() {
    rtCanvas = document.createElement('canvas');
}

async function startRealtime(facingMode) {
    if (facingMode) rtCurrentFacingMode = facingMode;

    try {
        rtStream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 640 },
                height: { ideal: 640 },
                facingMode: { ideal: rtCurrentFacingMode }
            },
            audio: false
        });
    } catch (err) {
        showAlert("Camera Error", "Could not access webcam. Please grant camera permission.", "error");
        return;
    }

    const video = document.getElementById('webcamVideo');
    if (video) {
        video.srcObject = rtStream;
        video.style.display = 'block';
    }

    const placeholder = document.getElementById('webcamPlaceholder');
    if (placeholder) {
        placeholder.style.display = 'none';
    }

    const liveBadge = document.getElementById('liveBadge');
    if (liveBadge) {
        liveBadge.style.display = 'flex';
    }

    const overlay = document.getElementById('detectionOverlay');
    if (overlay) {
        overlay.style.display = 'block';
    }

    const stopBtn = document.getElementById('rtStopBtn');
    if (stopBtn) {
        stopBtn.style.display = 'block';
    }

    const switchBtn = document.getElementById('rtSwitchBtn');
    if (switchBtn) {
        switchBtn.style.display = 'none';
    }

    const statusEl = document.getElementById('rtStatus');
    if (statusEl) {
        statusEl.textContent = 'Active';
        statusEl.style.color = '#22c55e';
    }

    rtIsRunning = true;
    rtTotalDetections = 0;
    rtFramesSent = 0;

    // Wait for video to be ready then start polling
    video.onloadedmetadata = () => {
        // Match TensorRT model tile size natively
        rtCanvas.width = 640;
        rtCanvas.height = 640;

        rtCtx = rtCanvas.getContext('2d');

        initWebSocket();
        startRealtimeLoop(); // start loop immediately, websocket will buffer slightly until open
    };
}
function initWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    rtSocket = new WebSocket(`${wsProtocol}//${window.location.host}/ws-detect`);
    
    rtSocket.onopen = () => {
        // Authenticate immediately
        rtSocket.send(JSON.stringify({ type: 'auth', token: Auth.getToken() }));
        console.log("WebSocket connected and authenticated for dashcam.");
    };
    
    rtSocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            updateRealtimeOverlay(data);
            
            if (data.detected) {
                rtTotalDetections++;
                document.getElementById('rtTotal').textContent = rtTotalDetections;
                
                if (data.report_id) {
                    console.log('Detection report saved automatically via WS:', data.report_id);
                    showToast(`Report #${data.report_id.toString().slice(0, 8)} saved`);

                    const imgSrc = data.annotated_image
                        ? (data.annotated_image.startsWith('data:')
                            ? data.annotated_image
                            : `data:image/jpeg;base64,${data.annotated_image}`)
                        : null;

                    rtSessionLog.push({
                        report_id: data.report_id.toString(),
                        damage_type: data.damage_type,
                        confidence: data.confidence,
                        image: imgSrc,
                        time: new Date().toLocaleTimeString()
                    });

                    updateSessionLogUI();
                }
            }
        } catch (err) {
            console.warn("WS parsing error", err);
        }
    };
    
    rtSocket.onclose = () => {
        if (rtIsRunning) {
            console.warn("WebSocket closed unexpectedly. Reconnecting in 2s...");
            setTimeout(initWebSocket, 2000);
        } else {
            console.log("WebSocket closed explicitly.");
        }
    };
}

async function sendRealtimeFrame() {

    if (!rtIsRunning || !rtSocket || rtSocket.readyState !== WebSocket.OPEN) return;
    if (rtRequestInFlight) return;

    rtRequestInFlight = true;

    const video = document.getElementById('webcamVideo');

    if (video.readyState < 2) {
        rtRequestInFlight = false;
        return;
    }

    // Capture frame on canvas natively scaled to 640x640
    rtCtx.drawImage(video, 0, 0, rtCanvas.width, rtCanvas.height);
    
    // Instead of Base64 toString processing overhead, use native binary Blobs
    rtCanvas.toBlob((blob) => {
        if (blob && rtSocket.readyState === WebSocket.OPEN) {
            // Push binary bytes to websocket
            rtSocket.send(blob);
            
            rtFramesSent++;
            document.getElementById('rtFrames').textContent = rtFramesSent;
            
            // Periodically ping GPS so server can track context
            if (rtFramesSent % 30 === 1) { // Send GPS on frame 1, 31, 61, etc.
                rtSocket.send(JSON.stringify({
                    type: 'gps',
                    location: gpsData.locationText || '',
                    lat: gpsData.lat,
                    lng: gpsData.lng
                }));
            }
        }
        // Allow next frame in loop
        rtRequestInFlight = false;
    }, 'image/jpeg', 0.6); // slight compression is still required to keep packets small
}

// Stores last realtime detection for manual submit
let rtLastDetection = null;

function updateRealtimeOverlay(data) {

    const overlay = document.getElementById('detectionOverlay');

    if (data.detected && data.damage_type) {

        overlay.innerHTML = `
            <span class="detection-label">
                ${data.damage_type} &nbsp; ${(data.confidence * 100).toFixed(0)}%
            </span>
        `;

        rtLastDetection = data;

        const potLabel = document.getElementById('rtLastDetectionPothole');
        const waterLabel = document.getElementById('rtLastDetectionWaterlog');
        const hazardToast = document.getElementById('hazardToast');
        const hazardToastText = document.getElementById('hazardToastText');
        
        if (potLabel) potLabel.style.display = 'none';
        if (waterLabel) waterLabel.style.display = 'none';

        const rawTypes = data.damage_type.split(',').map(d => d.trim().toLowerCase());
        const confText = `— ${(data.confidence * 100).toFixed(0)}% confidence`;

        if (rawTypes.includes('pothole') && potLabel) {
             potLabel.textContent = `Pothole Detected ${confText}`;
             potLabel.style.display = 'block';
        }
        
        // Hazard / Accident Notification Logic
        let showHazard = false;
        
        if (rawTypes.includes('waterlogging') && waterLabel) {
             waterLabel.textContent = `Waterlogging Detected ${confText}`;
             waterLabel.style.display = 'block';
             
             if (data.hidden_pothole_prob && hazardToast) {
                 hazardToastText.textContent = `Wet road — ${data.hidden_pothole_prob}% chance of a hidden pothole!`;
                 showHazard = true;
             }
        }
        
        if (rawTypes.includes('accident')) {
             if (hazardToast) {
                 hazardToastText.textContent = `CRITICAL: Accident detected! Calling Emergency Services (100)...`;
                 showHazard = true;
             }
        }
        
        if (hazardToast) {
            if (showHazard) {
                if (window.hazardToastHideTid) {
                    clearTimeout(window.hazardToastHideTid);
                    window.hazardToastHideTid = null;
                }
                hazardToast.classList.add('show');
            } else if (hazardToast.classList.contains('show')) {
                if (!window.hazardToastHideTid) {
                    window.hazardToastHideTid = setTimeout(() => {
                        hazardToast.classList.remove('show');
                        window.hazardToastHideTid = null;
                    }, 1000);
                }
            }
        }
        
        if (!rawTypes.includes('pothole') && !rawTypes.includes('waterlogging') && potLabel) {
             potLabel.textContent = `${data.damage_type} ${confText}`;
             potLabel.style.display = 'block';
        }

        const img = document.getElementById('rtLastDetectionImg');

        if (data.annotated_image) {
            img.src = data.annotated_image.startsWith('data:')
                ? data.annotated_image
                : `data:image/jpeg;base64,${data.annotated_image}`;
            img.style.display = 'block';
        } else {
            img.style.display = 'none';
        }

        document.getElementById('rtLastDetectionCard').style.display = 'block';

    } else {

        overlay.innerHTML =
            `<span class="detection-label no-damage">✓ No Damage</span>`;
            
        const hazardToast = document.getElementById('hazardToast');
        if (hazardToast && hazardToast.classList.contains('show')) {
            if (!window.hazardToastHideTid) {
                window.hazardToastHideTid = setTimeout(() => {
                    hazardToast.classList.remove('show');
                    window.hazardToastHideTid = null;
                }, 1000);
            }
        }
    }
}


function updateSessionLogUI() {
    const container = document.getElementById('rtSessionLog');
    const countEl = document.getElementById('rtSavedCount');
    if (!container) return;

    if (countEl) countEl.textContent = rtSessionLog.length;

    // Show the session log section
    const section = document.getElementById('rtSessionLogSection');
    if (section) section.style.display = 'block';

    // Build log entries (newest first)
    container.innerHTML = rtSessionLog.slice().reverse().map(entry => `
        <div style="
            display:flex; gap:0.75rem; align-items:center;
            padding:0.6rem; background:#f8fafc;
            border:1px solid #e2e8f0; border-radius:8px;
        ">
            ${entry.image
                ? `<img src="${entry.image}" style="width:64px;height:64px;object-fit:cover;border-radius:6px;border:1px solid #cbd5e1;" alt="Detection"/>`
                : `<div style="width:64px;height:64px;background:#e2e8f0;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:1.5rem;">📷</div>`
            }
            <div style="flex:1;min-width:0;">
                <div style="font-weight:600;color:#1e293b;font-size:0.85rem;">
                    ${entry.damage_type} — ${(entry.confidence * 100).toFixed(0)}%
                </div>
                <div style="color:#64748b;font-size:0.75rem;margin-top:2px;">
                    ${entry.time} · Report #${entry.report_id.slice(0, 8)}
                </div>
            </div>
        </div>
    `).join('');
}

function stopRealtime() {
    rtIsRunning = false;

    if (rtInterval) {
        clearInterval(rtInterval);
        rtInterval = null;
    }
    
    if (rtSocket) {
        rtSocket.close();
        rtSocket = null;
    }

    if (rtStream) {
        rtStream.getTracks().forEach(t => t.stop());
        rtStream = null;
    }

    const video = document.getElementById('webcamVideo');
    if (video) {
        video.srcObject = null;
        video.style.display = 'none';
    }

    const placeholder = document.getElementById('webcamPlaceholder');
    if (placeholder) {
        placeholder.style.display = 'block';
    }

    const liveBadge = document.getElementById('liveBadge');
    if (liveBadge) {
        liveBadge.style.display = 'none';
    }

    const overlay = document.getElementById('detectionOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }

    const startBtn = document.getElementById('rtStartBtn');
    if (startBtn) {
        startBtn.style.display = 'block';
    }

    const stopBtn = document.getElementById('rtStopBtn');
    if (stopBtn) {
        stopBtn.style.display = 'none';
    }

    const switchBtn = document.getElementById('rtSwitchBtn');
    if (switchBtn) {
        switchBtn.style.display = 'none';
    }

    const statusEl = document.getElementById('rtStatus');
    if (statusEl) {
        statusEl.textContent = 'Stopped';
        statusEl.style.color = '#999';
    }
}

/**
 * Switch between front and back camera while detection is running.
 */
async function switchCamera() {
    // Toggle facing mode
    rtCurrentFacingMode = rtCurrentFacingMode === 'environment' ? 'user' : 'environment';

    // Stop current stream and interval (but keep rtIsRunning = true)
    if (rtInterval) {
        clearInterval(rtInterval);
        rtInterval = null;
    }
    if (rtStream) {
        rtStream.getTracks().forEach(t => t.stop());
        rtStream = null;
    }

    // Update button label to show which camera is now active
    const switchBtn = document.getElementById('rtSwitchBtn');
    if (switchBtn) {
        switchBtn.textContent = rtCurrentFacingMode === 'environment' ? '🔄 Switch to Front' : '🔄 Switch to Back';
        switchBtn.disabled = true;
    }

    // Restart with new camera
    try {
        rtStream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 640 },
                height: { ideal: 480 },
                facingMode: { ideal: rtCurrentFacingMode }
            },
            audio: false
        });

        const video = document.getElementById('webcamVideo');
        video.srcObject = rtStream;

        video.onloadedmetadata = () => {
            // Match TensorRT model tile size natively
            rtCanvas.width = 640;
            rtCanvas.height = 640;

            rtCtx = rtCanvas.getContext('2d');
            
            // Re-init socket for new camera config context
            if(!rtSocket || rtSocket.readyState !== WebSocket.OPEN) {
                initWebSocket();
            }

            startRealtimeLoop(); // start adaptive loop
        };
    } catch (err) {
        showAlert("Camera Error", "Could not switch camera: " + err.message, "error");
        // Revert facing mode
        rtCurrentFacingMode = rtCurrentFacingMode === 'environment' ? 'user' : 'environment';
        switchBtn.disabled = false;
    }
}

// =====================================================
// HELPERS
// =====================================================
function formatBytes(bytes) {
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/**
 * Show a brief toast notification at the bottom of the screen.
 */
function showToast(message, duration = 3000) {
    const toast = document.createElement('div');
    toast.textContent = message;
    toast.style.cssText = [
        'position:fixed', 'bottom:1.5rem', 'right:1.5rem',
        'background:#4f46e5', 'color:#fff',
        'padding:0.6rem 1.1rem', 'border-radius:8px',
        'font-size:0.9rem', 'z-index:9999',
        'box-shadow:0 4px 16px rgba(0,0,0,0.3)',
        'transition:opacity 0.4s'
    ].join(';');
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

/**
 * Download the annotated image from the Photo tab.
 */
function downloadAnnotatedImage() {
    const src = annotatedImageB64
        ? `data:image/jpeg;base64,${annotatedImageB64}`
        : document.getElementById('annotatedImagePreview').src;
    if (!src) return;
    const a = document.createElement('a');
    a.href = src;
    a.download = `pothole_detection_${Date.now()}.jpg`;
    a.click();
}

/**
 * Download the full annotated video from the Video tab.
 */
function downloadAnnotatedVideo() {
    if (!videoToken) return;
    // Navigating to the URL triggers the browser's file download
    const a = document.createElement('a');
    a.href = `/api/citizen/get-video/${videoToken}`;
    a.download = `pothole_detection_${Date.now()}.mp4`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (rtIsRunning) stopRealtime();
});

/**
 * Submit a report for the video analysis result.
 */
async function submitVideoReport() {
    if (!videoDetectionData) return;

    const btn = document.getElementById('videoSubmitBtn');
    const status = document.getElementById('videoSubmitStatus');
    btn.disabled = true;
    btn.textContent = '⏳ Submitting...';
    status.style.display = 'none';

    // Get top damage + confidence
    const topDamage = videoDetectionData.top_damage;
    const topConf = videoDetectionData.summary
        ?.find(s => s.damage_type === topDamage)?.avg_confidence ?? 0;

    try {
        const res = await fetch('/api/citizen/submit-video', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${Auth.getToken()}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                damage_type: topDamage,
                confidence: topConf,
                location: gpsData.locationText,
                latitude: gpsData.lat,
                longitude: gpsData.lng,
                description: document.getElementById('videoDescriptionInput')?.value?.trim() || ''
            })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.msg || 'Submit failed');

        btn.textContent = '✅ Submitted';
        status.textContent = `Report #${data.report_id} saved successfully!`;
        status.style.color = '#22c55e';
        status.style.display = 'block';
    } catch (err) {
        btn.disabled = false;
        btn.textContent = '📤 Submit Report';
        status.textContent = 'Error: ' + err.message;
        status.style.color = '#f87171';
        status.style.display = 'block';
    }
}

// /**
//  * Submit a report for the last realtime detection frame.
//  */
// async function submitRealtimeReport() {
//     if (!rtLastDetection) return;

//     const btn = document.getElementById('rtSubmitBtn');
//     const status = document.getElementById('rtSubmitStatus');
//     btn.disabled = true;
//     btn.textContent = '⏳ Submitting...';
//     status.style.display = 'none';

//     const formData = new FormData();
//     formData.append('damage_type', rtLastDetection.damage_type);
//     formData.append('confidence', rtLastDetection.confidence);
//     formData.append('location', gpsData.locationText || '');
//     if (gpsData.lat !== null) {
//         formData.append('latitude', gpsData.lat);
//         formData.append('longitude', gpsData.lng);
//     }
//     const desc = document.getElementById('rtDescriptionInput')?.value?.trim();
//     if (desc) formData.append('description', desc);
//     // Attach the annotated frame image
//     if (rtLastDetection.annotated_image) {
//         formData.append('frame_b64', rtLastDetection.annotated_image);
//     }

//     try {
//         const res = await fetch('/api/citizen/submit-realtime-frame', {
//             method: 'POST',
//             headers: { 'Authorization': `Bearer ${Auth.getToken()}` },
//             body: formData
//         });
//         const data = await res.json();
//         if (!res.ok) throw new Error(data.msg || 'Submit failed');

//         btn.textContent = '✅ Submitted';
//         status.textContent = `Report #${data.report_id} saved successfully!`;
//         status.style.color = '#22c55e';
//         status.style.display = 'block';
//         // Clear description after submit
//         document.getElementById('rtDescriptionInput').value = '';
//     } catch (err) {
//         btn.disabled = false;
//         btn.textContent = '📤 Submit Report';
//         status.textContent = 'Error: ' + err.message;
//         status.style.color = '#f87171';
//         status.style.display = 'block';
//     }
// }

function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371000; // meters
    const toRad = x => x * Math.PI / 180;

    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);

    const a =
        Math.sin(dLat/2) * Math.sin(dLat/2) +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
        Math.sin(dLon/2) * Math.sin(dLon/2);

    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

    return R * c;
}

async function startRealtimeLoop() {

    if (!rtIsRunning) return;

    const start = performance.now();

    await sendRealtimeFrame();

    const elapsed = performance.now() - start;

    // For Binary WebSocket sending, latency overhead is practically zero on the Javascript side.
    // However, to avoid fully saturating low-end device CPU, we keep a fast stable delay to target ~25 FPS
    const BASE_TARGET_DELAY = 40;
    
    // Adjust delay slightly to keep pushing bytes natively
    if (elapsed > 100) {
        rtDynamicDelay = Math.min(rtDynamicDelay + 10, 150);
    } 
    else if (elapsed < 30) {
        rtDynamicDelay = Math.max(rtDynamicDelay - 5, BASE_TARGET_DELAY);
    }

    setTimeout(startRealtimeLoop, rtDynamicDelay);
}

// Global exposure
window.switchTab = switchTab;
window.startRealtime = startRealtime;
window.stopRealtime = stopRealtime;
window.downloadAnnotatedImage = downloadAnnotatedImage;
window.downloadAnnotatedVideo = downloadAnnotatedVideo;
window.switchCamera = switchCamera;
window.submitVideoReport = submitVideoReport;
// window.submitRealtimeReport = submitRealtimeReport;
