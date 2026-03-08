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
document.addEventListener('DOMContentLoaded', () => {
    Auth.requireRole('citizen');
    initReportForm();
    initRealtimeTab();
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

    if ("geolocation" in navigator) {
        setAllLocationDisplays('Acquiring GPS...');
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const { latitude, longitude } = position.coords;
                gpsData.lat = latitude;
                gpsData.lng = longitude;
                gpsData.locationText = `Lat: ${latitude.toFixed(5)}, Lng: ${longitude.toFixed(5)}`;
                setAllLocationDisplays(gpsData.locationText);
            },
            (error) => {
            console.log("Geolocation error:", error);
            
            gpsData.locationText = 'Location permission REQUIRED';
            setAllLocationDisplays(gpsData.locationText);

            showAlert(
                "Location Required",
                "Please enable GPS and allow precise location. Error: " + error.message,
                "warning"
            );
        },
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
        );
    } else {
        gpsData.locationText = 'Geolocation not supported';
        setAllLocationDisplays(gpsData.locationText);
    }
}

// =====================================================
// =====================================================
// TAB 3: REALTIME
// =====================================================
// =====================================================

let rtStream = null;
let rtIsRunning = false;
let rtInterval = null;
let rtTotalDetections = 0;
let rtFramesSent = 0;
let rtCanvas = null;
let rtCtx = null;
let rtCurrentFacingMode = 'environment'; // 'environment' = back, 'user' = front

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
    video.srcObject = rtStream;
    video.style.display = 'block';
    document.getElementById('webcamPlaceholder').style.display = 'none';
    document.getElementById('liveBadge').style.display = 'flex';
    document.getElementById('detectionOverlay').style.display = 'block';

    document.getElementById('rtStartBtn').style.display = 'none';
    document.getElementById('rtStopBtn').style.display = 'block';
    document.getElementById('rtSwitchBtn').style.display = 'block';
    document.getElementById('rtStatus').textContent = 'Active';
    document.getElementById('rtStatus').style.color = '#22c55e';

    rtIsRunning = true;
    rtTotalDetections = 0;
    rtFramesSent = 0;

    // Wait for video to be ready then start polling
    video.onloadedmetadata = () => {
        rtCanvas.width = video.videoWidth;
        rtCanvas.height = video.videoHeight;
        rtCtx = rtCanvas.getContext('2d');
        rtInterval = setInterval(sendRealtimeFrame, 1000); // every 1 second
    };
}

let rtRequestInFlight = false;

async function sendRealtimeFrame() {

    if (!rtIsRunning || rtRequestInFlight) return;

    const video = document.getElementById('webcamVideo');

    if (video.readyState < 2) return;

    rtRequestInFlight = true;

    try {

        rtCtx.drawImage(video, 0, 0, rtCanvas.width, rtCanvas.height);

        const frameData = rtCanvas.toDataURL('image/jpeg', 0.6);

        rtFramesSent++;
        document.getElementById('rtFrames').textContent = rtFramesSent;

        const res = await fetch("/api/citizen/detect-frame", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${Auth.getToken()}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                frame: frameData
            })
        });

        const data = await res.json();

        if (!res.ok) return;

        updateRealtimeOverlay(data);

        if (data.detected) {
            rtTotalDetections++;
            document.getElementById('rtTotal').textContent = rtTotalDetections;
        }

    } catch (err) {
        console.warn("Realtime error:", err);
    }

    rtRequestInFlight = false;
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
        // Update last detection card
        rtLastDetection = data;
        document.getElementById('rtLastDetectionLabel').textContent =
            `${data.damage_type} — ${(data.confidence * 100).toFixed(0)}% confidence`;
        // Show annotated frame if available
        const img = document.getElementById('rtLastDetectionImg');
        if (data.annotated_image) {
            img.src = data.annotated_image.startsWith('data:') ? data.annotated_image : `data:image/jpeg;base64,${data.annotated_image}`;
            img.style.display = 'block';
        } else {
            img.style.display = 'none';
        }
        // Reset submit button state
        const submitBtn = document.getElementById('rtSubmitBtn');
        const submitStatus = document.getElementById('rtSubmitStatus');
        submitBtn.disabled = false;
        submitBtn.textContent = '📤 Submit Report';
        submitStatus.style.display = 'none';
        document.getElementById('rtLastDetectionCard').style.display = 'block';
    } else {
        overlay.innerHTML = `<span class="detection-label no-damage">✓ No Damage</span>`;
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
    video.srcObject = null;
    video.style.display = 'none';

    document.getElementById('webcamPlaceholder').style.display = 'block';
    document.getElementById('liveBadge').style.display = 'none';
    document.getElementById('detectionOverlay').style.display = 'none';
    document.getElementById('rtStartBtn').style.display = 'block';
    document.getElementById('rtStopBtn').style.display = 'none';
    document.getElementById('rtSwitchBtn').style.display = 'none';
    document.getElementById('rtStatus').textContent = 'Stopped';
    document.getElementById('rtStatus').style.color = '#999';
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
    switchBtn.textContent = rtCurrentFacingMode === 'environment' ? '🔄 Switch to Front' : '🔄 Switch to Back';
    switchBtn.disabled = true;

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
            rtCanvas.width = video.videoWidth;
            rtCanvas.height = video.videoHeight;
            rtCtx = rtCanvas.getContext('2d');
            rtInterval = setInterval(sendRealtimeFrame, 1000);
            switchBtn.disabled = false;
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

/**
 * Submit a report for the last realtime detection frame.
 */
async function submitRealtimeReport() {
    if (!rtLastDetection) return;

    const btn = document.getElementById('rtSubmitBtn');
    const status = document.getElementById('rtSubmitStatus');
    btn.disabled = true;
    btn.textContent = '⏳ Submitting...';
    status.style.display = 'none';

    const formData = new FormData();
    formData.append('damage_type', rtLastDetection.damage_type);
    formData.append('confidence', rtLastDetection.confidence);
    formData.append('location', gpsData.locationText || '');
    if (gpsData.lat !== null) {
        formData.append('latitude', gpsData.lat);
        formData.append('longitude', gpsData.lng);
    }
    const desc = document.getElementById('rtDescriptionInput')?.value?.trim();
    if (desc) formData.append('description', desc);
    // Attach the annotated frame image
    if (rtLastDetection.annotated_image) {
        formData.append('frame_b64', rtLastDetection.annotated_image);
    }

    try {
        const res = await fetch('/api/citizen/submit-realtime-frame', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${Auth.getToken()}` },
            body: formData
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.msg || 'Submit failed');

        btn.textContent = '✅ Submitted';
        status.textContent = `Report #${data.report_id} saved successfully!`;
        status.style.color = '#22c55e';
        status.style.display = 'block';
        // Clear description after submit
        document.getElementById('rtDescriptionInput').value = '';
    } catch (err) {
        btn.disabled = false;
        btn.textContent = '📤 Submit Report';
        status.textContent = 'Error: ' + err.message;
        status.style.color = '#f87171';
        status.style.display = 'block';
    }
}

// Global exposure
window.switchTab = switchTab;
window.triggerFileInput = triggerFileInput;
window.handleFileSelect = handleFileSelect;
window.retakePhoto = retakePhoto;
window.submitReport = submitReport;
window.triggerVideoInput = triggerVideoInput;
window.handleVideoSelect = handleVideoSelect;
window.processVideo = processVideo;
window.resetVideoTab = resetVideoTab;
window.startRealtime = startRealtime;
window.stopRealtime = stopRealtime;
window.downloadAnnotatedImage = downloadAnnotatedImage;
window.downloadAnnotatedVideo = downloadAnnotatedVideo;
window.switchCamera = switchCamera;
window.submitVideoReport = submitVideoReport;
window.submitRealtimeReport = submitRealtimeReport;
