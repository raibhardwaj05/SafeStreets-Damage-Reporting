const Auth = {
    API_URL: '/api/auth',

    // =========================
    // REGISTER
    // =========================
    async register(name, email, password, role) {
        try {
            const response = await fetch(`${this.API_URL}/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, email, password, role })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.msg || 'Registration failed');
            }

            return await response.json();
        } catch (error) {
            console.error('Register Error:', error);
            throw error;
        }
    },

    // =========================
    // LOGIN
    // =========================
    async login(email, password) {
        try {
            const response = await fetch(`${this.API_URL}/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.msg || 'Login failed');
            }

            const data = await response.json();
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('role', data.role);
            localStorage.setItem('user_name', data.name);

            return data;
        } catch (error) {
            console.error('Login Error:', error);
            throw error;
        }
    },

    // =========================
    // LOGOUT
    // =========================
    logout() {
        localStorage.removeItem('token');
        localStorage.removeItem('role');
        localStorage.removeItem('user_name');
        window.location.href = '/';
    },

    // =========================
    // TOKEN HELPERS
    // =========================
    getToken() {
        return localStorage.getItem('token');
    },

    getRole() {
        return localStorage.getItem('role');
    },

    isAuthenticated() {
        return !!this.getToken();
    },

    // =========================
    // ROLE PROTECTION
    // =========================
    requireRole(requiredRole) {
        if (!this.isAuthenticated()) {
            window.location.href = '/index.html';
            return;
        }

        const currentRole = this.getRole();
        if (currentRole !== requiredRole) {
            alert('Access Denied');
            this.logout();
        }
    },

    // =========================
    // AUTHORIZED FETCH
    // =========================
    async fetchWithAuth(url, options = {}, retries = 1) {
        const token = this.getToken();
        if (!token) {
            throw new Error('No token found. Please log in again.');
        }

        const headers = {
            'Authorization': `Bearer ${token}`,
            ...options.headers
        };

        try {
            const response = await fetch(url, { ...options, headers });

            if (response.status === 401 || response.status === 403) {
                console.warn('Session expired or unauthorized');
                this.logout();
                return response;
            }

            return response;
        } catch (error) {
            if (retries > 0) {
                console.warn(`Fetch failed, retrying... (${retries} left)`);
                return this.fetchWithAuth(url, options, retries - 1);
            }
            console.error('Fetch error:', error);
            throw error;
        }
    }
};

// Expose globally
window.Auth = Auth;
