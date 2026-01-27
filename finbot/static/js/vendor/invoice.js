/**
 * FinBot Vendor Portal - Invoice Management
 */

// Invoice state management
const InvoiceState = {
    invoices: [],
    isLoading: false,
    currentFilter: 'all',
    editingInvoiceId: null,
    isModalOpen: false
};

// Initialize invoices when DOM is loaded
ready(function () {
    initializeInvoices();
});

/**
 * Initialize invoice page
 */
async function initializeInvoices() {
    console.log('🚀 Initializing Invoice Management...');

    try {
        // Initialize UI components
        initializeInvoiceModal();
        initializeCreateButtons();

        // Load invoices data
        await loadInvoices();

        console.log('✅ Invoices initialized successfully');

    } catch (error) {
        console.error('❌ Invoice initialization failed:', error);
        showNotification('Failed to load invoices', 'error');
    }
}

/**
 * Initialize create invoice buttons
 */
function initializeCreateButtons() {
    // Header create button
    const createBtn = document.getElementById('create-invoice-btn');
    if (createBtn) {
        createBtn.addEventListener('click', () => openInvoiceModal());
    }

    // Empty state create button
    const emptyStateBtn = document.querySelector('.create-invoice-trigger');
    if (emptyStateBtn) {
        emptyStateBtn.addEventListener('click', () => openInvoiceModal());
    }
}

/**
 * Initialize invoice modal
 */
function initializeInvoiceModal() {
    const modal = document.getElementById('invoice-modal');
    const closeBtn = document.getElementById('close-invoice-modal-btn');
    const cancelBtn = document.getElementById('cancel-invoice-btn');
    const form = document.getElementById('invoice-form');

    if (!modal || !form) {
        console.warn('Invoice modal elements not found');
        return;
    }

    // Close modal handlers
    [closeBtn, cancelBtn].forEach(btn => {
        if (btn) {
            btn.addEventListener('click', closeInvoiceModal);
        }
    });

    // Close on backdrop click
    modal.addEventListener('click', function (e) {
        if (e.target === modal) {
            closeInvoiceModal();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
            closeInvoiceModal();
        }
    });

    // Form submission
    form.addEventListener('submit', handleInvoiceSubmit);

    // Set default invoice date to today
    const invoiceDateInput = document.getElementById('invoice-date');
    if (invoiceDateInput) {
        invoiceDateInput.value = formatDateForInput(new Date());
    }

    // Set default due date to 30 days from now
    const dueDateInput = document.getElementById('invoice-due-date');
    if (dueDateInput) {
        const dueDate = new Date();
        dueDate.setDate(dueDate.getDate() + 30);
        dueDateInput.value = formatDateForInput(dueDate);
    }
}

/**
 * Open invoice modal for create or edit
 * @param {Object|null} invoice - Invoice data for edit mode, null for create mode
 */
function openInvoiceModal(invoice = null) {
    const modal = document.getElementById('invoice-modal');
    const modalTitle = document.getElementById('invoice-modal-title');
    const submitText = document.getElementById('submit-invoice-text');
    const form = document.getElementById('invoice-form');

    if (!modal || !form) return;

    // Reset form
    form.reset();

    if (invoice) {
        // Edit mode
        InvoiceState.editingInvoiceId = invoice.id;
        modalTitle.textContent = 'Edit Invoice';
        submitText.textContent = 'Save Changes';

        // Populate form fields
        document.getElementById('invoice-id').value = invoice.id;
        document.getElementById('invoice-number').value = invoice.invoice_number || '';
        document.getElementById('invoice-amount').value = invoice.amount || '';
        document.getElementById('invoice-date').value = formatDateForInput(invoice.invoice_date);
        document.getElementById('invoice-due-date').value = formatDateForInput(invoice.due_date);
        document.getElementById('invoice-description').value = invoice.description || '';
    } else {
        // Create mode
        InvoiceState.editingInvoiceId = null;
        modalTitle.textContent = 'Create Invoice';
        submitText.textContent = 'Create Invoice';

        // Set default dates
        document.getElementById('invoice-date').value = formatDateForInput(new Date());
        const dueDate = new Date();
        dueDate.setDate(dueDate.getDate() + 30);
        document.getElementById('invoice-due-date').value = formatDateForInput(dueDate);
    }

    // Show modal
    modal.classList.remove('hidden');
    InvoiceState.isModalOpen = true;

    // Focus first input
    setTimeout(() => {
        document.getElementById('invoice-number').focus();
    }, 100);
}

/**
 * Close invoice modal
 */
function closeInvoiceModal() {
    const modal = document.getElementById('invoice-modal');
    if (!modal) return;

    modal.classList.add('hidden');
    InvoiceState.isModalOpen = false;
    InvoiceState.editingInvoiceId = null;

    // Reset form
    const form = document.getElementById('invoice-form');
    if (form) {
        form.reset();
    }
}

/**
 * Handle invoice form submission
 */
async function handleInvoiceSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const submitBtn = document.getElementById('submit-invoice-btn');
    const isEditMode = InvoiceState.editingInvoiceId !== null;

    try {
        const hideLoading = showLoading(submitBtn, isEditMode ? 'Saving...' : 'Creating...');

        // Get form data
        const formData = new FormData(form);
        const invoiceData = {
            invoice_number: formData.get('invoice_number'),
            amount: parseFloat(formData.get('amount')),
            description: formData.get('description'),
            invoice_date: formData.get('invoice_date'),
            due_date: formData.get('due_date')
        };

        // Validate data
        if (!invoiceData.invoice_number || !invoiceData.amount || !invoiceData.description) {
            hideLoading();
            showNotification('Please fill in all required fields', 'error');
            return;
        }

        if (invoiceData.amount <= 0) {
            hideLoading();
            showNotification('Amount must be greater than zero', 'error');
            return;
        }

        let response;
        if (isEditMode) {
            // Update invoice via API
            response = await api.put(
                `/vendor/api/v1/invoices/${InvoiceState.editingInvoiceId}`,
                invoiceData
            );
            showNotification('Invoice updated successfully!', 'success');
        } else {
            // Create invoice via API
            response = await api.post('/vendor/api/v1/invoices', invoiceData);
            showNotification('Invoice created successfully!', 'success');
        }

        hideLoading();

        // Close modal
        closeInvoiceModal();

        // Reload invoices
        await loadInvoices();

    } catch (error) {
        console.error('Error saving invoice:', error);

        // Handle API errors
        const errorMessage = handleAPIError(error, { showAlert: true });

        if (!(error.status === 403 && error.data?.error?.type === 'csrf_error')) {
            showNotification(`Failed to save invoice: ${errorMessage}`, 'error');
        }
    }
}

/**
 * Load invoices from API
 */
async function loadInvoices() {
    const tableBody = document.getElementById('invoices-table-body');
    const emptyState = document.getElementById('invoices-empty-state');

    InvoiceState.isLoading = true;

    try {
        const response = await fetch('/vendor/api/v1/invoices');
        if (!response.ok) {
            throw new Error('Failed to load invoices');
        }

        const data = await response.json();
        const invoices = data.invoices || [];

        InvoiceState.invoices = invoices;

        // Clear loading state
        tableBody.innerHTML = '';

        if (invoices.length === 0) {
            // Show empty state
            document.querySelector('.neural-table').classList.add('hidden');
            emptyState.classList.remove('hidden');
            return;
        }

        // Hide empty state, show table
        document.querySelector('.neural-table').classList.remove('hidden');
        emptyState.classList.add('hidden');

        // Render invoices
        invoices.forEach(invoice => {
            const row = createInvoiceRow(invoice);
            tableBody.appendChild(row);
        });

    } catch (error) {
        console.error('Error loading invoices:', error);
        tableBody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-8 text-text-secondary">
                    Failed to load invoices. Please try again.
                </td>
            </tr>
        `;
    } finally {
        InvoiceState.isLoading = false;
    }
}

/**
 * Create invoice table row element
 */
function createInvoiceRow(invoice) {
    const row = document.createElement('tr');

    // Format amount
    const amount = formatCurrency(invoice.amount);

    // Format dates
    const invoiceDate = formatDate(invoice.invoice_date);
    const dueDate = formatDate(invoice.due_date);
    const isOverdue = new Date(invoice.due_date) < new Date() && invoice.status !== 'paid';

    // Status mapping
    const status = getStatusConfig(invoice.status);

    row.innerHTML = `
        <td>
            <span class="font-medium text-text-bright">${escapeHtml(invoice.invoice_number || 'N/A')}</span>
        </td>
        <td>
            <span class="font-semibold text-vendor-accent">${amount}</span>
        </td>
        <td>
            <span class="text-text-primary">${invoiceDate}</span>
        </td>
        <td>
            <span class="${isOverdue ? 'text-vendor-danger' : 'text-text-primary'}">${dueDate}</span>
        </td>
        <td>
            <span class="status-indicator ${status.class}">${status.label}</span>
        </td>
        <td>
            <div class="flex items-center space-x-2">
                <button class="action-btn view" data-invoice-id="${invoice.id}" title="View">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
                    </svg>
                </button>
                <button class="action-btn edit" data-invoice-id="${invoice.id}" title="Edit">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                    </svg>
                </button>
            </div>
        </td>
    `;

    // Add event listeners
    const viewBtn = row.querySelector('.action-btn.view');
    const editBtn = row.querySelector('.action-btn.edit');

    if (viewBtn) {
        viewBtn.addEventListener('click', () => viewInvoice(invoice.id));
    }
    if (editBtn) {
        editBtn.addEventListener('click', () => editInvoice(invoice.id));
    }

    return row;
}

/**
 * Get status configuration for display
 */
function getStatusConfig(status) {
    const statusConfig = {
        'submitted': { class: 'pending', label: 'Submitted' },
        'processing': { class: 'processing', label: 'Processing' },
        'approved': { class: 'approved', label: 'Approved' },
        'rejected': { class: 'rejected', label: 'Rejected' },
        'paid': { class: 'approved', label: 'Paid' }
    };

    return statusConfig[status] || { class: 'pending', label: status };
}

/**
 * Format date for display
 */
function formatDate(dateString) {
    if (!dateString) return 'N/A';

    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        });
    } catch (error) {
        console.error('Error formatting date:', error);
        return 'Invalid Date';
    }
}

/**
 * Format date for input field (YYYY-MM-DD)
 */
function formatDateForInput(dateString) {
    if (!dateString) return '';

    try {
        const date = new Date(dateString);
        return date.toISOString().split('T')[0];
    } catch (error) {
        console.error('Error formatting date for input:', error);
        return '';
    }
}

/**
 * Format currency for display
 */
function formatCurrency(amount) {
    if (amount === null || amount === undefined) return '$0';

    try {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD'
        }).format(amount);
    } catch (error) {
        console.error('Error formatting currency:', error);
        return `$${amount}`;
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * View invoice details
 */
async function viewInvoice(invoiceId) {
    try {
        const response = await api.get(`/vendor/api/v1/invoices/${invoiceId}`);
        const invoice = response.data.invoice;

        // For now, open in edit modal (read-only view can be added later)
        openInvoiceModal(invoice);
    } catch (error) {
        console.error('Error loading invoice:', error);
        showNotification('Failed to load invoice details', 'error');
    }
}

/**
 * Edit invoice
 */
async function editInvoice(invoiceId) {
    try {
        const response = await api.get(`/vendor/api/v1/invoices/${invoiceId}`);
        const invoice = response.data.invoice;

        openInvoiceModal(invoice);
    } catch (error) {
        console.error('Error loading invoice:', error);
        showNotification('Failed to load invoice details', 'error');
    }
}
