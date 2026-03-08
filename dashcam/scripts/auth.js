// ============================================
// DashCam Device Authentication
// ============================================

const Auth = {

    API_URL: "/api/device",

    // ============================================
    // REGISTER DEVICE
    // ============================================
    async register(vehicleNo, deviceId) {

        try {

            const response = await fetch(`${this.API_URL}/register`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    vehicle_no: vehicleNo,
                    device_id: deviceId
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.msg || "Device registration failed");
            }

            return data;

        } catch (error) {

            console.error("Register Error:", error);
            throw error;

        }
    },

    // ============================================
    // LOGIN DEVICE
    // ============================================
    async login(deviceCode) {

        try {

            const response = await fetch(`${this.API_URL}/login`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    device_code: deviceCode
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.msg || "Invalid device code");
            }

            // Save session data
            localStorage.setItem("device_token", data.token);
            localStorage.setItem("device_id", data.device_id);
            localStorage.setItem("vehicle_no", data.vehicle_no);

            return data;

        } catch (error) {

            console.error("Login Error:", error);
            throw error;

        }
    },

    // ============================================
    // LOGOUT DEVICE
    // ============================================
    logout() {

        localStorage.removeItem("device_token");
        localStorage.removeItem("device_id");
        localStorage.removeItem("vehicle_no");

        window.location.href = "/";

    },

    // ============================================
    // TOKEN HELPERS
    // ============================================
    getToken() {
        return localStorage.getItem("device_token");
    },

    getVehicle() {
        return localStorage.getItem("vehicle_no");
    },

    getDeviceId() {
        return localStorage.getItem("device_id");
    },

    isAuthenticated() {
        return !!this.getToken();
    },

    // ============================================
    // PROTECT DASHBOARD
    // ============================================
    requireAuth() {

        if (!this.isAuthenticated()) {
            window.location.href = "login.html";
        }

    },

    // ============================================
    // AUTHORIZED API CALL
    // ============================================
    async fetchWithAuth(url, options = {}, retries = 1) {

        const token = this.getToken();

        if (!token) {
            throw new Error("Device not authenticated");
        }

        const headers = {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
            ...options.headers
        };

        try {

            const response = await fetch(url, {
                ...options,
                headers
            });

            if (response.status === 401 || response.status === 403) {

                console.warn("Session expired. Logging out...");
                this.logout();

                return response;

            }

            return response;

        } catch (error) {

            if (retries > 0) {

                console.warn(`Retrying API request (${retries})`);
                return this.fetchWithAuth(url, options, retries - 1);

            }

            console.error("Fetch Error:", error);
            throw error;

        }

    }

};

// Make Auth globally accessible
window.Auth = Auth;