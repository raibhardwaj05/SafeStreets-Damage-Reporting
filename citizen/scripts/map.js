(function initMap() {
    const mapEl = document.getElementById('leafletMap');
    if (!mapEl) return;

    // Default center (will be overridden by geolocation)
    const defaultLat = 19.0372;
    const defaultLng = 73.0214;

    const map = L.map('leafletMap', {
        zoomControl: true,
        attributionControl: false
    }).setView([defaultLat, defaultLng], 15);

    let userLatLng = null;
    const reportMarkers = [];

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
    }).addTo(map);

    // Custom blue icon for user location
    const userIcon = L.divIcon({
        className: 'user-loc-marker',
        html: '<div style="width:16px;height:16px;background:#2563eb;border:3px solid white;border-radius:50%;box-shadow:0 2px 8px rgba(37,99,235,0.5);"></div>',
        iconSize: [16, 16],
        iconAnchor: [8, 8]
    });

    // Red pin icon for report locations (larger, map-style)
    const reportIcon = L.divIcon({
        className: 'report-loc-marker',
        html: '<div style="position:relative;width:30px;height:30px;transform:translateY(-8px);"><div style="position:absolute;left:50%;top:4px;width:14px;height:14px;margin-left:-7px;border-radius:50% 50% 50% 0;background:#ef4444;transform:rotate(-45deg);box-shadow:0 2px 6px rgba(0,0,0,0.35);border:2px solid #ffffff;"></div><div style="position:absolute;left:50%;top:9px;width:6px;height:6px;margin-left:-3px;border-radius:50%;background:#ffffff;opacity:0.9;"></div></div>',
        iconSize: [30, 30],
        iconAnchor: [15, 28]
    });

    // Detect user location
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function (pos) {
            const lat = pos.coords.latitude;
            const lng = pos.coords.longitude;

            userLatLng = L.latLng(lat, lng);
            map.setView([lat, lng], 15);
            L.marker([lat, lng], { icon: userIcon })
                .addTo(map)
                .bindPopup('<strong>📍 Your Location</strong>')
                .openPopup();

            // Accuracy circle
            if (pos.coords.accuracy) {
                L.circle([lat, lng], {
                    radius: Math.min(pos.coords.accuracy, 300),
                    color: '#2563eb',
                    fillColor: '#2563eb',
                    fillOpacity: 0.08,
                    weight: 1
                }).addTo(map);
            }

            // Update coordinates display
            const coordsEl = document.getElementById('mapCoordsText');
            if (coordsEl) coordsEl.textContent = `Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}`;

        }, function () {
            userLatLng = L.latLng(defaultLat, defaultLng);
            L.marker([defaultLat, defaultLng], { icon: userIcon })
                .addTo(map)
                .bindPopup('<strong>📍 Your Location</strong>')
                .openPopup();
        }, { enableHighAccuracy: true, timeout: 10000 });
    }

    // Fetch ALL citizen reports and plot them with 100m damage radius
    async function loadAllReportMarkers() {
        try {
            // Try fetching all reports from the API
            const res = await Auth.fetchWithAuth('/api/citizen/reports');
            if (!res.ok) throw new Error('API error');
            const reports = await res.json();
            plotReports(reports);
        } catch (e) {
            // Fallback: use already-loaded reports from dashboard if available
            const waitForReports = setInterval(function () {
                if (typeof allReports !== 'undefined' && allReports.length > 0) {
                    clearInterval(waitForReports);
                    plotReports(allReports);
                }
            }, 500);
        }
    }

    function plotReports(reports) {
        reports.forEach(function (r) {
            if (!r.location) return;
            const match = r.location.match(/Lat:\s*([\d.-]+).*Lng:\s*([\d.-]+)/i);
            if (!match) return;

            const rLat = parseFloat(match[1]);
            const rLng = parseFloat(match[2]);
            const damageType = r.damage_type || r.damageType || 'Unknown';
            const severity = r.severity || 'Unknown';
            const status = r.status || 'submitted';
            const statusLabel = status === 'submitted' ? 'Reported' : status === 'resolved' ? 'Completed' : status.charAt(0).toUpperCase() + status.slice(1);

            // Report marker
            const marker = L.marker([rLat, rLng], { icon: reportIcon })
                .addTo(map)
                .bindPopup(
                    `<div style="font-family:Inter,sans-serif;font-size:12px;line-height:1.5;">
                                <strong>🚧 Damage Report</strong><br>
                                <b>Type:</b> ${damageType}<br>
                                <b>Severity:</b> ${severity}<br>
                                <b>Status:</b> ${statusLabel}
                            </div>`
                );

            reportMarkers.push(marker);
        });

        adjustViewToMarkers();
    }

    function adjustViewToMarkers() {
        if (!reportMarkers.length && !userLatLng) {
            return;
        }

        if (!reportMarkers.length && userLatLng) {
            map.setView(userLatLng, 16);
            return;
        }

        const group = L.featureGroup(reportMarkers);
        let bounds = group.getBounds();
        if (userLatLng) {
            bounds = bounds.extend(userLatLng);
        }

        map.fitBounds(bounds, { maxZoom: 17, padding: [40, 40] });
    }

    loadAllReportMarkers();

    // Fix map sizing when container is resized
    setTimeout(function () { map.invalidateSize(); }, 300);
    window.addEventListener('resize', function () { map.invalidateSize(); });
})();

