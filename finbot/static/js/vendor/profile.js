/**
 * FinBot Vendor Portal - Profile Management
 */

// Profile state management
const ProfileState = {
    vendorData: null,
    isEditing: false,
    isLoading: false,
    showSensitiveData: false
};

// Initialize profile when DOM is loaded
ready(function () {
    initializeProfile();
});

/**
 * Initialize profile page
 */
async function initializeProfile() {
    console.log('🚀 Initializing Vendor Profile...');

    try {
        // Load vendor profile data
        await loadProfileData();

        // Initialize UI components
        initializeProfileUI();
        initializeEditModal();
        initializeSensitiveDataToggle();

        console.log('✅ Profile initialized successfully');

    } catch (error) {
        console.error('❌ Profile initialization failed:', error);
        showNotification('Failed to load profile data', 'error');
    }
}

/**
 * Load profile data from API
 */
async function loadProfileData() {
    try {
        showLoadingOverlay('Loading profile data...');

        // Load vendor context to get current vendor ID
        const contextResponse = await api.get('/vendor/api/v1/vendors/context');
        const currentVendor = contextResponse.data.current_vendor;

        if (!currentVendor || !currentVendor.id) {
            throw new Error('No vendor context found');
        }

        // Get full vendor details using the vendor ID
        const vendorResponse = await api.get(`/vendor/api/v1/vendors/${currentVendor.id}`);
        const vendorDetails = vendorResponse.data;

        // Load dashboard metrics for statistics
        const metricsResponse = await api.get('/vendor/api/v1/dashboard/metrics');

        ProfileState.vendorData = {
            ...vendorDetails,
            metrics: metricsResponse.data.metrics
        };

        console.log('📊 Profile data loaded:', ProfileState.vendorData);

        // Update UI with profile data
        updateProfileUI();

        hideLoadingOverlay();

    } catch (error) {
        console.error('Error loading profile data:', error);
        hideLoadingOverlay();
        throw error;
    }
}

/**
 * Update profile UI with loaded data
 */
function updateProfileUI() {
    if (!ProfileState.vendorData) {
        console.warn('No vendor data to display');
        return;
    }

    const vendor = ProfileState.vendorData;

    // Update header
    updateElement('company-initials', getCompanyInitials(vendor.company_name));
    updateElement('company-name', vendor.company_name);
    updateElement('vendor-category', vendor.vendor_category || 'N/A');
    updateElement('vendor-status', vendor.status || 'pending');
    updateElement('vendor-id', `ID: ${vendor.id}`);
    updateElement('member-since', formatDate(vendor.created_at));

    // Update company information
    updateElement('profile-company-name', vendor.company_name);
    updateElement('profile-category', formatVendorCategory(vendor.vendor_category));
    updateElement('profile-industry', vendor.industry || 'N/A');
    updateElement('profile-services', vendor.services || 'No services listed');

    // Update contact information
    updateElement('profile-contact-name', vendor.contact_name || 'N/A');
    updateElement('profile-email', vendor.email || 'N/A');
    updateElement('profile-phone', vendor.phone || 'N/A');

    // Update payment information (masked by default)
    updateElement('profile-tin', maskSensitiveData(vendor.tin, 'tin'));
    updateElement('profile-bank-name', vendor.bank_name || 'N/A');
    updateElement('profile-account-holder', vendor.bank_account_holder_name || 'N/A');
    updateElement('profile-account-number', maskSensitiveData(vendor.bank_account_number, 'account'));
    updateElement('profile-routing-number', maskSensitiveData(vendor.bank_routing_number, 'routing'));

    // Update statistics
    updateStatistics();
}

/**
 * Update statistics section
 */
function updateStatistics() {
    if (!ProfileState.vendorData || !ProfileState.vendorData.metrics) {
        return;
    }

    const metrics = ProfileState.vendorData.metrics;
    const invoiceStats = metrics.invoices || {};

    updateElement('stats-total-invoices', invoiceStats.total_count || 0);
    updateElement('stats-total-revenue', formatCurrency(invoiceStats.total_amount || 0));
    updateElement('stats-pending-payments', invoiceStats.pending_count || 0);
    updateElement('stats-completion-rate', `${Math.round(metrics.completion_rate || 0)}%`);
    updateElement('stats-last-activity', 'Just now');
}

/**
 * Initialize profile UI components
 */
function initializeProfileUI() {
    // Edit profile button
    const editBtn = document.getElementById('edit-profile-btn');
    if (editBtn) {
        editBtn.addEventListener('click', openEditModal);
    }
}

/**
 * Initialize edit modal
 */
function initializeEditModal() {
    const modal = document.getElementById('edit-profile-modal');
    const closeBtn = document.getElementById('close-modal-btn');
    const cancelBtn = document.getElementById('cancel-edit-btn');
    const form = document.getElementById('edit-profile-form');

    if (!modal || !form) {
        console.warn('Edit modal elements not found');
        return;
    }

    // Close modal handlers
    [closeBtn, cancelBtn].forEach(btn => {
        if (btn) {
            btn.addEventListener('click', closeEditModal);
        }
    });

    // Close on backdrop click
    modal.addEventListener('click', function (e) {
        if (e.target === modal) {
            closeEditModal();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
            closeEditModal();
        }
    });

    // Form submission
    form.addEventListener('submit', handleProfileUpdate);
}

/**
 * Open edit modal and populate form
 */
function openEditModal() {
    if (!ProfileState.vendorData) {
        showNotification('Profile data not loaded yet', 'warning');
        return;
    }

    const modal = document.getElementById('edit-profile-modal');
    if (!modal) return;

    // Populate form with current data
    const vendor = ProfileState.vendorData;
    document.getElementById('edit-company-name').value = vendor.company_name || '';
    document.getElementById('edit-services').value = vendor.services || '';
    document.getElementById('edit-contact-name').value = vendor.contact_name || '';
    document.getElementById('edit-email').value = vendor.email || '';
    document.getElementById('edit-phone').value = vendor.phone || '';

    // Show modal
    modal.classList.remove('hidden');
    ProfileState.isEditing = true;

    // Focus first input
    setTimeout(() => {
        document.getElementById('edit-company-name').focus();
    }, 100);
}

/**
 * Close edit modal
 */
function closeEditModal() {
    const modal = document.getElementById('edit-profile-modal');
    if (!modal) return;

    modal.classList.add('hidden');
    ProfileState.isEditing = false;

    // Clear form
    document.getElementById('edit-profile-form').reset();
}

/**
 * Handle profile update form submission
 */
async function handleProfileUpdate(e) {
    e.preventDefault();

    if (!ProfileState.vendorData) {
        showNotification('No profile data to update', 'error');
        return;
    }

    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');

    try {
        const hideLoading = showLoading(submitBtn, 'Saving Changes...');

        // Get form data
        const formData = new FormData(form);
        const updateData = {
            company_name: formData.get('company_name'),
            services: formData.get('services'),
            contact_name: formData.get('contact_name'),
            email: formData.get('email'),
            phone: formData.get('phone')
        };

        // Validate data
        if (!updateData.company_name || !updateData.email) {
            hideLoading();
            showNotification('Company name and email are required', 'error');
            return;
        }

        // Update profile via API
        const response = await api.put(
            `/vendor/api/v1/vendors/${ProfileState.vendorData.id}`,
            updateData
        );

        hideLoading();

        // Update local state
        ProfileState.vendorData = {
            ...ProfileState.vendorData,
            ...updateData
        };

        // Update UI
        updateProfileUI();

        // Close modal
        closeEditModal();

        // Show success message
        showNotification('Profile updated successfully!', 'success');

    } catch (error) {
        console.error('Error updating profile:', error);

        // Handle API errors
        const errorMessage = handleAPIError(error, { showAlert: true });

        if (!(error.status === 403 && error.data?.error?.type === 'csrf_error')) {
            showNotification(`Failed to update profile: ${errorMessage}`, 'error');
        }
    }
}

/**
 * Initialize sensitive data toggle
 */
function initializeSensitiveDataToggle() {
    // Add click handlers to show/hide buttons
    const toggleButtons = document.querySelectorAll('[data-toggle="sensitive-data"]');

    // Create show/hide button for payment section
    const paymentHeader = document.querySelector('.holo-card .holo-header button');
    if (paymentHeader) {
        paymentHeader.addEventListener('click', toggleSensitiveData);
    }
}

/**
 * Toggle sensitive data visibility
 */
function toggleSensitiveData() {
    ProfileState.showSensitiveData = !ProfileState.showSensitiveData;

    if (!ProfileState.vendorData) return;

    const vendor = ProfileState.vendorData;

    if (ProfileState.showSensitiveData) {
        // Show actual data
        updateElement('profile-tin', vendor.tin || 'N/A');
        updateElement('profile-account-number', vendor.bank_account_number || 'N/A');
        updateElement('profile-routing-number', vendor.bank_routing_number || 'N/A');
        showNotification('Sensitive data is now visible', 'info');
    } else {
        // Mask data
        updateElement('profile-tin', maskSensitiveData(vendor.tin, 'tin'));
        updateElement('profile-account-number', maskSensitiveData(vendor.bank_account_number, 'account'));
        updateElement('profile-routing-number', maskSensitiveData(vendor.bank_routing_number, 'routing'));
        showNotification('Sensitive data is now hidden', 'info');
    }
}

/**
 * Helper function to update element content
 */
function updateElement(id, content) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = content;
    }
}

/**
 * Get company initials from name
 */
function getCompanyInitials(companyName) {
    if (!companyName) return 'V';

    const words = companyName.split(' ').filter(word => word.length > 0);
    if (words.length === 0) return 'V';
    if (words.length === 1) return words[0].substring(0, 2).toUpperCase();

    return (words[0][0] + words[1][0]).toUpperCase();
}

/**
 * Format vendor category for display
 */
function formatVendorCategory(category) {
    if (!category) return 'N/A';

    const categoryMap = {
        'talent': 'Talent (Actors, Directors, Writers, Musicians)',
        'crew': 'Crew (Camera, Sound, Lighting, Grip, Production Assistants)',
        'equipment_rental': 'Equipment Rental (Cameras, Lenses, Lighting, Sound Gear)',
        'location_scouting': 'Location Scouting & Management',
        'catering': 'Catering & Craft Services',
        'vfx_animation': 'Visual Effects (VFX) & Animation',
        'post_production': 'Post-Production Services (Editing, Color Grading, Sound Mixing)',
        'legal_consulting': 'Legal & Business Consulting',
        'transportation': 'Transportation & Logistics',
        'set_design': 'Set Design & Construction',
        'costume_wardrobe': 'Costume & Wardrobe',
        'security': 'Security Services',
        'other_specialized': 'Other Specialized Services'
    };

    return categoryMap[category] || category;
}

/**
 * Mask sensitive data based on type
 */
function maskSensitiveData(data, type) {
    if (!data) return 'N/A';

    switch (type) {
        case 'tin':
            // Mask TIN/EIN: XX-XXXXXXX -> **-*******
            return data.replace(/\d/g, '*');
        case 'account':
            // Mask account number: show last 4 digits
            return '****' + data.slice(-4);
        case 'routing':
            // Mask routing number: show last 4 digits
            return '****' + data.slice(-4);
        default:
            return data.replace(/./g, '*');
    }
}

/**
 * Format date for display
 */
function formatDate(dateString) {
    if (!dateString) return 'N/A';

    try {
        const date = new Date(dateString);
        const options = { year: 'numeric', month: 'long', day: 'numeric' };
        return date.toLocaleDateString('en-US', options);
    } catch (error) {
        console.error('Error formatting date:', error);
        return 'Invalid Date';
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
            currency: 'USD',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(amount);
    } catch (error) {
        console.error('Error formatting currency:', error);
        return `$${amount}`;
    }
}

/**
 * Show loading overlay
 */
function showLoadingOverlay(message = 'Loading...') {
    // Use existing loading notification
    showNotification(message, 'info');
}

/**
 * Hide loading overlay
 */
function hideLoadingOverlay() {
    // Handled by notification auto-hide
}

