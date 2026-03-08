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

// Dynamic FPS control
let rtDynamicDelay = 300;     // starting delay (~3 FPS)
const rtMinDelay = 200;       // max speed (~5 FPS)
const rtMaxDelay = 900;       // slowest (~1 FPS)

// 4 seconds cool down period
// 4 seconds cool down period
let rtLastDetectionTime = 0;
const RT_DETECTION_COOLDOWN = 4000;

// dashcam auto report session
let rtDetectionSession = null;
let rtSessionStartTime = null;

// Interval after which dashcam detections are grouped into a single report
const RT_REPORT_INTERVAL = 30000; // 30 seconds
const RT_CONF_THRESHOLD = 0.4;


function initRealtimeTab() {
    rtCanvas = document.createElement('canvas');
}

async function startRealtime(facingMode) {
    if (facingMode) rtCurrentFacingMode = facingMode;

    try {
        rtStream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 640 },
                height: { ideal: 480 },
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

        // Reduce resolution for faster detection
        rtCanvas.width = 416;
        rtCanvas.height = 416;

        rtCtx = rtCanvas.getContext('2d');

        startRealtimeLoop(); // start adaptive loop
    };
}

async function sendRealtimeFrame() {

    if (!rtIsRunning) return;
    if (rtRequestInFlight) return;

    rtRequestInFlight = true;

    const video = document.getElementById('webcamVideo');

    if (video.readyState < 2) {
        rtRequestInFlight = false;
        return;
    }

    // Capture frame
    rtCtx.drawImage(video, 0, 0, rtCanvas.width, rtCanvas.height);
    const frameData = rtCanvas.toDataURL('image/jpeg', 0.5);

    rtFramesSent++;
    document.getElementById('rtFrames').textContent = rtFramesSent;

    try {

        const res = await fetch("/api/dashcam/detect-frame", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${Auth.getToken()}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                frame: frameData,
                location: gpsData.locationText,
                latitude: gpsData.lat,
                longitude: gpsData.lng
            })
        });

        const data = await res.json();

        if (!res.ok) return;

        updateRealtimeOverlay(data);

        // -------------------------------------------------
        // HANDLE DETECTION
        // -------------------------------------------------

        if (data.detected) {

            const now = Date.now();

            // Always increment total detections
            rtTotalDetections++;
            document.getElementById('rtTotal').textContent = rtTotalDetections;

            // Cooldown only affects session logging
            if (now - rtLastDetectionTime < RT_DETECTION_COOLDOWN) {
                return;
            }

            rtLastDetectionTime = now;

            const currentLat = gpsData.lat;
            const currentLng = gpsData.lng;

            // Skip if GPS not ready
            if (currentLat == null || currentLng == null) return;

            // Ignore low confidence
            if (data.confidence < RT_CONF_THRESHOLD) return;

            // Start detection session
            if (!rtDetectionSession) {

                rtDetectionSession = {
                    first_damage: {
                        damage_type: data.damage_type,
                        confidence: data.confidence,
                        image: data.annotated_image,
                        lat: currentLat,
                        lng: currentLng,
                        text: gpsData.locationText
                    },
                    last_damage: null,
                    intermediate_locations: [],
                    valid_detections: 0
                };

                rtSessionStartTime = Date.now();

                console.log("Dashcam detection session started");
            }

            // Count valid detection
            rtDetectionSession.valid_detections++;

            // Limit payload size
            if (rtDetectionSession.intermediate_locations.length < 50) {

                rtDetectionSession.intermediate_locations.push({
                    lat: currentLat,
                    lng: currentLng,
                    confidence: data.confidence
                });

            }

            // Update last damage
            rtDetectionSession.last_damage = {
                damage_type: data.damage_type,
                confidence: data.confidence,
                image: data.annotated_image,
                lat: currentLat,
                lng: currentLng,
                text: gpsData.locationText
            };

        }

        // -------------------------------------------------
        // AUTO SUBMIT CHECK (runs every frame)
        // -------------------------------------------------

        if (rtDetectionSession && rtSessionStartTime) {

            const elapsed = Date.now() - rtSessionStartTime;

            if (elapsed >= RT_REPORT_INTERVAL) {

                console.log("Auto submitting dashcam report after 30 seconds");

                if (rtDetectionSession.last_damage) {
                    submitDashcamSession(rtDetectionSession);
                }

                rtDetectionSession = null;
                rtSessionStartTime = null;

                // Reset cooldown
                rtLastDetectionTime = Date.now();
            }
        }

    }
    catch (err) {
        console.warn("Realtime frame error:", err);
    }
    finally {
        rtRequestInFlight = false;
    }
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

        document.getElementById('rtLastDetectionLabel').textContent =
            `${data.damage_type} — ${(data.confidence * 100).toFixed(0)}% confidence`;

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
    }
}

async function submitDashcamSession(session) {

    try {

        const res = await fetch("/api/dashcam/submit-dashcam-session", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${Auth.getToken()}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                first_damage: session.first_damage,
                last_damage: session.last_damage,
                intermediate_locations: session.intermediate_locations
            })
        });

        const data = await res.json();

        if (res.ok) {
            console.log("Dashcam session saved:", data.report_id);
            showToast(`Dashcam report saved (${session.valid_detections} detections)`);
        }

    } catch (err) {
        console.warn("Dashcam session submit failed:", err);
    }
}

function stopRealtime() {
    rtIsRunning = false;

    if (rtInterval) {
        clearInterval(rtInterval);
        rtInterval = null;
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

            // Reduce resolution for faster detection
            rtCanvas.width = 416;
            rtCanvas.height = 416;

            rtCtx = rtCanvas.getContext('2d');

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

    // Adjust delay based on processing time
    if (elapsed > 600) {
        rtDynamicDelay = Math.min(rtDynamicDelay + 100, rtMaxDelay);
    } 
    else if (elapsed < 300) {
        rtDynamicDelay = Math.max(rtDynamicDelay - 50, rtMinDelay);
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
