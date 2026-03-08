// Shared Navigation Utilities

/**
 * Initialize navigation highlighting based on current page
 */
function initNavigation() {
    const currentPage = window.location.pathname.split('/').pop() || 'dashboard.html';
    const navLinks = document.querySelectorAll('.nav-link, .nav-item, .top-nav-link, .mobile-nav__link');

    navLinks.forEach(link => {
        const linkHref = link.getAttribute('href');
        if (!linkHref) return;
        
        const linkPage = linkHref.split('/').pop();
        if (linkPage === currentPage) {
            link.classList.add('active');
        } else {
            // Only remove if it's not a static active class that might be needed
            // But usually we want dynamic highlighting
            link.classList.remove('active');
        }
    });

    // Initialize profile menu data if elements exist
    updateProfileInfo();

    // Close profile menu when clicking outside
    document.addEventListener('click', (e) => {
        const profileSection = document.querySelector('.profile-section, .profile-container');
        const menu = document.getElementById('profileMenu');
        if (profileSection && menu && menu.classList.contains('active') && !profileSection.contains(e.target)) {
            menu.classList.remove('active');
        }
    });
}

/**
 * Update profile info from localStorage (login details)
 */
function updateProfileInfo() {
    const name = localStorage.getItem('user_name') || 'User';
    const role = localStorage.getItem('role') || '';

    const roleText = role === 'official' ? 'Lead Officer' : role ? role.charAt(0).toUpperCase() + role.slice(1) : '';

    // Update all .user-name elements (profile dropdown)
    document.querySelectorAll('.user-name').forEach(el => { el.textContent = name; });

    // Update all .user-role elements
    document.querySelectorAll('.user-role').forEach(el => { if (roleText) el.textContent = roleText; });

    // Update dashboard top bar user name
    const topBarName = document.getElementById('topBarUserName');
    if (topBarName) topBarName.textContent = name;

    // Update avatar if present (official portal)
    const headerAvatar = document.getElementById('headerAvatar');
    if (headerAvatar) {
        headerAvatar.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=f1f5f9&color=64748b`;
    }
}

/**
 * Toggle profile dropdown menu
 */
function toggleProfileMenu() {
    const menu = document.getElementById('profileMenu');
    if (menu) {
        menu.classList.toggle('active');
    }
}

/**
 * Toggle mobile navigation drawer
 */
function toggleMobileNav() {
    const nav = document.getElementById('mobileNav');
    const overlay = document.getElementById('mobileNavOverlay');
    const btn = document.getElementById('hamburgerBtn');
    
    if (nav && overlay && btn) {
        const isOpen = nav.classList.toggle('active');
        overlay.classList.toggle('active', isOpen);
        btn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    }
}

/**
 * Show logout confirmation and perform logout
 */
function confirmLogout() {
    if (typeof showConfirm === 'function') {
        showConfirm(
            'Confirm Logout',
            'Are you sure you want to log out of the system?',
            (confirmed) => {
                if (confirmed) {
                    // Determine which Auth object to use
                    // Dashcam has its own Auth, other portals use shared Auth
                    const authObj = window.Auth;
                    if (authObj && typeof authObj.logout === 'function') {
                        authObj.logout();
                    } else {
                        // Fallback in case Auth is not loaded or missing logout
                        localStorage.removeItem('token');
                        localStorage.removeItem('device_token');
                        localStorage.removeItem('role');
                        localStorage.removeItem('user_name');
                        localStorage.removeItem('device_id');
                        localStorage.removeItem('vehicle_no');
                        window.location.href = '/';
                    }
                }
            }
        );
    } else {
        // Fallback to standard confirm if modal system is not loaded
        if (confirm('Are you sure you want to log out?')) {
            if (window.Auth && typeof window.Auth.logout === 'function') {
                window.Auth.logout();
            } else {
                window.location.href = '/';
            }
        }
    }
}

/**
 * Navigate to a different page
 */
function navigateTo(url) {
    window.location.href = url;
}

// Initialize navigation when DOM is loaded
document.addEventListener('DOMContentLoaded', initNavigation);
