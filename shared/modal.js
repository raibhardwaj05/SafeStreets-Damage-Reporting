// Modal System for Road Damage Detection System

/**
 * Show a modal dialog
 * @param {string} title - Modal title
 * @param {string} message - Modal message
 * @param {string} type - Modal type: 'success', 'warning', 'error', 'info', 'confirm', 'prompt'
 * @param {Function} onConfirm - Callback for confirm/prompt
 * @param {Function} onCancel - Callback for cancel
 * @param {string} defaultValue - Default value for prompt
 */
function showModal(title, message, type = 'info', onConfirm = null, onCancel = null, defaultValue = '') {
    // Create or get modal overlay
    let modalOverlay = document.getElementById('modalOverlay');
    if (!modalOverlay) {
        modalOverlay = document.createElement('div');
        modalOverlay.id = 'modalOverlay';
        modalOverlay.className = 'modal-overlay';
        document.body.appendChild(modalOverlay);
    }

    // Determine icon based on type
    const icons = {
        success: '✓',
        warning: '⚠',
        error: '✗',
        info: 'ℹ',
        confirm: '?',
        prompt: '✎'
    };

    const iconClass = type === 'confirm' || type === 'prompt' ? 'info' : type;

    // Build modal HTML
    let footerHTML = '';
    let inputHTML = '';

    if (type === 'confirm') {
        footerHTML = `
            <button class="btn btn-primary" id="modalConfirmBtn">Confirm</button>
            <button class="btn btn-secondary" id="modalCancelBtn">Cancel</button>
        `;
    } else if (type === 'prompt') {
        inputHTML = `<input type="text" class="modal-input" id="modalInput" value="${defaultValue}" placeholder="Enter value...">`;
        footerHTML = `
            <button class="btn btn-primary" id="modalConfirmBtn">OK</button>
            <button class="btn btn-secondary" id="modalCancelBtn">Cancel</button>
        `;
    } else {
        footerHTML = `<button class="btn btn-primary" id="modalCloseBtn">OK</button>`;
    }

    modalOverlay.innerHTML = `
        <div class="modal-container">
            <div class="modal-header">
                <h2 class="modal-title">${title}</h2>
                <button class="modal-close" id="modalCloseX">&times;</button>
            </div>
            <div class="modal-body">
                <div class="modal-icon ${iconClass}">${icons[type] || icons.info}</div>
                <div>${message}</div>
                ${inputHTML}
            </div>
            <div class="modal-footer">
                ${footerHTML}
            </div>
        </div>
    `;

    // Show modal
    modalOverlay.classList.add('active');

    // Focus input if prompt
    if (type === 'prompt') {
        setTimeout(() => {
            const input = document.getElementById('modalInput');
            if (input) {
                input.focus();
                input.select();
            }
        }, 100);
    }

    // Close handlers
    const closeModal = (result = null) => {
        modalOverlay.classList.remove('active');
        if (result !== null && onConfirm) {
            onConfirm(result);
        } else if (result === null && onCancel) {
            onCancel();
        }
    };

    // Close button
    document.getElementById('modalCloseX').addEventListener('click', () => closeModal(null));

    // OK/Close button
    const closeBtn = document.getElementById('modalCloseBtn');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => closeModal(null));
    }

    // Confirm button
    const confirmBtn = document.getElementById('modalConfirmBtn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', () => {
            if (type === 'prompt') {
                const input = document.getElementById('modalInput');
                closeModal(input ? input.value : defaultValue);
            } else {
                closeModal(true);
            }
        });
    }

    // Cancel button
    const cancelBtn = document.getElementById('modalCancelBtn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => closeModal(null));
    }

    // Close on overlay click
    modalOverlay.addEventListener('click', (e) => {
        if (e.target === modalOverlay) {
            closeModal(null);
        }
    });

    // Close on Escape key
    const escapeHandler = (e) => {
        if (e.key === 'Escape') {
            closeModal(null);
            document.removeEventListener('keydown', escapeHandler);
        }
    };
    document.addEventListener('keydown', escapeHandler);
}

/**
 * Show alert (wrapper for showModal)
 */
function showAlert(title, message, type = 'info', onClose = null) {
    showModal(title, message, type, onClose);
}

/**
 * Show confirm dialog
 */
function showConfirm(title, message, onConfirm, onCancel = null) {
    showModal(title, message, 'confirm', onConfirm, onCancel);
}

/**
 * Show prompt dialog
 */
function showPrompt(title, message, defaultValue = '', onConfirm, onCancel = null) {
    showModal(title, message, 'prompt', onConfirm, onCancel, defaultValue);
}
