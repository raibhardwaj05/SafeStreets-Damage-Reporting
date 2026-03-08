// Add Contractor Script

document.addEventListener('DOMContentLoaded', () => {
    Auth.requireRole('official');

    const form = document.getElementById('addContractorForm');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const data = {
            name: document.getElementById('contractorName').value,
            specialization: document.getElementById('specialization').value,
            contact: document.getElementById('contact').value
        };

        try {
            const response = await Auth.fetchWithAuth('/api/official/contractors', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                showModal('Success', 'Contractor added successfully', 'success');
                setTimeout(() => {
                    window.location.href = 'assignment.html';
                }, 1500);
            } else {
                const err = await response.json();
                throw new Error(err.msg || 'Failed to add contractor');
            }
        } catch (error) {
            showModal('Error', error.message);
        }
    });
});
