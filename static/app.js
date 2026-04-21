// ====================
// DISABLE LONG PRESS & TEXT SELECTION
// ====================

// Disable context menu (right click / long press menu)
document.addEventListener('contextmenu', function(e) {
    e.preventDefault();
    return false;
});

// Disable text selection on drag/select (but allow in input fields)
document.addEventListener('selectstart', function(e) {
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        e.preventDefault();
        return false;
    }
});

// Disable drag events on images and elements
document.addEventListener('dragstart', function(e) {
    e.preventDefault();
    return false;
});

// Disable copy events on non-input elements
document.addEventListener('copy', function(e) {
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        e.preventDefault();
        return false;
    }
});

// Disable cut events on non-input elements
document.addEventListener('cut', function(e) {
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        e.preventDefault();
        return false;
    }
});

function formatCurrency(amount) {
    return '₹' + parseFloat(amount).toFixed(2);
}

function formatPhoneNumber(phone) {
    if (!phone) return "";
    let formatted = phone;
    if (formatted.startsWith("+91")) {
        formatted = formatted.substring(3);
    }
    if (formatted.length > 10) {
        formatted = formatted.slice(-10);
    }
    return formatted;
}

function showNotification(message, type = 'info') {
    let container = document.getElementById('notificationContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notificationContainer';
        container.className = 'notification-container';
        document.body.appendChild(container);
    }
    
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    
    let icon = '';
    if (type === 'success') icon = '✅ ';
    else if (type === 'error') icon = '❌ ';
    else if (type === 'info') icon = 'ℹ️ ';
    else if (type === 'warning') icon = '⚠️ ';
    
    notification.innerHTML = `${icon} ${message}`;
    notification.onclick = () => notification.remove();
    
    container.appendChild(notification);
    setTimeout(() => notification.remove(), 5000);
}

// API Helper
async function apiCall(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        
        if (response.status === 401) {
            console.log('Authentication required, redirecting to login');
            sessionStorage.setItem('redirectAfterLogin', window.location.pathname);
            window.location.href = '/';
            throw new Error('Authentication required');
        }
        
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || 'Something went wrong');
            }
            return data;
        } else {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return null;
        }
    } catch (error) {
        console.error('API Error:', error);
        if (error.message !== 'Authentication required') {
            showNotification(error.message, 'error');
        }
        throw error;
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getRandomColor(seed) {
    const colors = ['#1a73e8', '#28a745', '#dc3545', '#ffc107', '#17a2b8', '#6f42c1', '#fd7e14', '#20c997', '#e83e8c', '#6c757d'];
    let numericId = typeof seed === 'string' ? seed.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) : (seed || 0);
    return colors[numericId % colors.length];
}

// ====================
// AUTH FUNCTIONS (for login page)
// ====================

async function sendOTP() {
    const phoneInput = document.getElementById('phone');
    const nameInput = document.getElementById('name');
    
    if (!phoneInput) {
        showNotification('Phone input not found', 'error');
        return;
    }
    
    const phone = phoneInput.value;
    const name = nameInput ? nameInput.value : '';
    
    if (!phone) {
        showNotification('📱 Please enter phone number', 'error');
        return;
    }
    
    const phoneRegex = /^\+?[0-9]{10,15}$/;
    if (!phoneRegex.test(phone.replace(/[\s\-\(\)]/g, ''))) {
        showNotification('Invalid phone number format', 'error');
        return;
    }
    
    try {
        const data = await apiCall('/send_otp', {
            method: 'POST',
            body: JSON.stringify({ phone, name })
        });
        
        showNotification(data.message || '📨 OTP sent successfully!', 'success');
        const step1 = document.getElementById('step1');
        const step2 = document.getElementById('step2');
        if (step1 && step2) {
            step1.classList.remove('active');
            step2.classList.add('active');
        }
    } catch (error) {
        console.error('Send OTP error:', error);
    }
}

let pendingUserData = null;
let validatedReferralCode = null;
let isProcessing = false;

async function verifyOTP() {
    const phoneInput = document.getElementById('phone');
    const otpInput = document.getElementById('otp');
    const nameInput = document.getElementById('name');
    
    if (!phoneInput || !otpInput) {
        showNotification('Form elements not found', 'error');
        return;
    }
    
    const phone = phoneInput.value;
    const otp = otpInput.value;
    const name = nameInput ? nameInput.value : '';
    
    if (!otp) {
        showNotification('Please enter OTP', 'error');
        return;
    }
    
    try {
        const response = await fetch('/verify_otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone, otp, name, referral_code: '' })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            if (data.user && data.user.is_new_user) {
                pendingUserData = data.user;
                
                const referralInput = document.getElementById('referralCodeInput');
                if (referralInput) {
                    referralInput.value = '';
                }
                validatedReferralCode = null;
                
                const validationDiv = document.getElementById('referralValidation');
                if (validationDiv) {
                    validationDiv.innerHTML = '';
                    validationDiv.className = 'validation-message';
                }
                
                const modal = document.getElementById('referralModal');
                if (modal) {
                    modal.style.display = 'block';
                }
            } else {
                showNotification('🎉 Login successful! Redirecting...', 'success');
                localStorage.setItem('user', JSON.stringify(data.user));
                if (data.jwt_token) {
                    localStorage.setItem('jwt_token', data.jwt_token);
                }
                
                const redirectTo = sessionStorage.getItem('redirectAfterLogin') || '/dashboard';
                sessionStorage.removeItem('redirectAfterLogin');
                
                setTimeout(() => {
                    window.location.href = redirectTo;
                }, 1000);
            }
        } else {
            showNotification(data.error || 'Invalid OTP', 'error');
        }
    } catch (error) {
        console.error('Verify OTP error:', error);
        showNotification(error.message || 'Failed to verify OTP', 'error');
    }
}

function initReferralValidation() {
    const referralInput = document.getElementById('referralCodeInput');
    if (referralInput) {
        referralInput.addEventListener('input', async function() {
            const code = this.value.trim().toUpperCase();
            const validationDiv = document.getElementById('referralValidation');
            const applyBtn = document.getElementById('applyReferralBtn');
            
            if (code.length === 0) {
                validationDiv.innerHTML = '';
                validationDiv.className = 'validation-message';
                validatedReferralCode = null;
                if (applyBtn) applyBtn.disabled = false;
                return;
            }
            
            if (code.length < 6) {
                validationDiv.innerHTML = '<i class="fas fa-spinner fa-pulse"></i> Checking...';
                validationDiv.className = 'validation-message';
                return;
            }
            
            try {
                const response = await fetch('/api/validate_referral_code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ referral_code: code })
                });
                
                const data = await response.json();
                
                if (response.ok && data.valid) {
                    validationDiv.innerHTML = `<i class="fas fa-check-circle"></i> ${data.message}`;
                    validationDiv.className = 'validation-message success';
                    validatedReferralCode = code;
                    if (applyBtn) applyBtn.disabled = false;
                } else {
                    validationDiv.innerHTML = `<i class="fas fa-times-circle"></i> ${data.error || 'Invalid referral code'}`;
                    validationDiv.className = 'validation-message error';
                    validatedReferralCode = null;
                    if (applyBtn) applyBtn.disabled = true;
                }
            } catch (error) {
                validationDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error validating code';
                validationDiv.className = 'validation-message error';
                validatedReferralCode = null;
                if (applyBtn) applyBtn.disabled = true;
            }
        });
    }
}

async function applyReferralCode() {
    if (isProcessing) return;
    isProcessing = true;
    
    const applyBtn = document.getElementById('applyReferralBtn');
    const skipBtn = document.getElementById('skipBtn');
    
    if (applyBtn) {
        applyBtn.disabled = true;
        applyBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    }
    if (skipBtn) skipBtn.disabled = true;
    
    try {
        const response = await fetch('/api/apply_referral', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                user_id: pendingUserData.id,
                referral_code: validatedReferralCode || ''
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            let bonusMessage = '🎉 Account created successfully! ₹100 credited to your wallet!';
            if (validatedReferralCode) {
                bonusMessage = '🎉 Referral code applied! ₹250 bonus added to your wallet!';
            }
            
            showNotification(bonusMessage, 'success');
            
            if (data.user) {
                localStorage.setItem('user', JSON.stringify(data.user));
            }
            
            const modal = document.getElementById('referralModal');
            if (modal) {
                modal.style.display = 'none';
            }
            
            const redirectTo = sessionStorage.getItem('redirectAfterLogin') || '/dashboard';
            sessionStorage.removeItem('redirectAfterLogin');
            
            setTimeout(() => {
                window.location.href = redirectTo;
            }, 1500);
        } else {
            showNotification(data.error || 'Failed to apply referral code', 'error');
            if (applyBtn) {
                applyBtn.disabled = false;
                applyBtn.innerHTML = '<i class="fas fa-check"></i> Apply & Continue';
            }
            if (skipBtn) skipBtn.disabled = false;
            isProcessing = false;
        }
    } catch (error) {
        console.error('Apply referral error:', error);
        showNotification('Failed to apply referral code. Please try again.', 'error');
        if (applyBtn) {
            applyBtn.disabled = false;
            applyBtn.innerHTML = '<i class="fas fa-check"></i> Apply & Continue';
        }
        if (skipBtn) skipBtn.disabled = false;
        isProcessing = false;
    }
}

async function skipReferral() {
    if (isProcessing) return;
    
    const modal = document.getElementById('referralModal');
    if (modal) {
        modal.style.display = 'none';
    }
    
    showNotification('🎉 Account created successfully! Redirecting...', 'success');
    localStorage.setItem('user', JSON.stringify(pendingUserData));
    
    const redirectTo = sessionStorage.getItem('redirectAfterLogin') || '/dashboard';
    sessionStorage.removeItem('redirectAfterLogin');
    
    setTimeout(() => {
        window.location.href = redirectTo;
    }, 1500);
}

function backToPhone() {
    const step1 = document.getElementById('step1');
    const step2 = document.getElementById('step2');
    const otpInput = document.getElementById('otp');
    
    if (step1 && step2) {
        step1.classList.add('active');
        step2.classList.remove('active');
    }
    if (otpInput) {
        otpInput.value = '';
    }
}

function togglePassword(fieldId) {
    const field = document.getElementById(fieldId);
    if (!field) return;
    
    const icon = field.nextElementSibling;
    if (!icon) return;
    
    if (field.type === 'password') {
        field.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
    } else {
        field.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
    }
}

// ====================
// DASHBOARD FUNCTIONS
// ====================

async function checkAndRedirectToPinSetup() {
    try {
        const response = await fetch('/api/check_pin_setup');
        if (response.status === 401) return false;
        
        const data = await response.json();
        if (data.needs_setup && window.location.pathname !== '/setup-pin') {
            window.location.href = '/setup-pin';
            return true;
        }
        return false;
    } catch (error) {
        console.error('PIN check error:', error);
        return false;
    }
}

async function loadDashboard() {
    try {
        console.log('Loading dashboard...');
        
        const needsSetup = await checkAndRedirectToPinSetup();
        if (needsSetup) return;
        
        console.log('Fetching user data...');
        const user = await apiCall('/api/user');
        console.log('User data received:', user);
        
        const balanceElement = document.getElementById('walletBalance');
        if (balanceElement) {
            balanceElement.textContent = formatCurrency(user.balance || 0);
        }
        
        console.log('Loading people...');
        await loadPeople();
        
        console.log('Loading contacts...');
        await loadContacts();
        
        console.log('Loading pending requests...');
        await loadPendingRequests();
        
        console.log('Loading recent transactions...');
        await loadRecentTransactions();
        
        const urlParams = new URLSearchParams(window.location.search);
        const sendTo = urlParams.get('sendTo');
        const requestFrom = urlParams.get('requestFrom');
        
        if (sendTo) {
            const identifierInput = document.getElementById('recipientIdentifier');
            if (identifierInput) {
                identifierInput.value = sendTo;
                showTab('send');
                const amountInput = document.getElementById('sendAmount');
                if (amountInput) amountInput.focus();
            }
        } else if (requestFrom) {
            const phoneInput = document.getElementById('requestPhone');
            if (phoneInput) {
                phoneInput.value = requestFrom;
                showTab('request');
                const amountInput = document.getElementById('requestAmount');
                if (amountInput) amountInput.focus();
            }
        }
        
        console.log('Dashboard loaded successfully');
    } catch (error) {
        console.error('Load dashboard error:', error);
        if (error.message !== 'Authentication required') {
            const peopleContainer = document.getElementById('peopleList');
            if (peopleContainer) {
                peopleContainer.innerHTML = '<div class="no-people">Error loading data. Please refresh the page.</div>';
            }
            
            const contactsContainer = document.getElementById('contactsList');
            if (contactsContainer) {
                contactsContainer.innerHTML = '<div class="no-contacts">Error loading contacts. Please refresh.</div>';
            }
        }
    }
}

async function loadRecentTransactions() {
    const container = document.getElementById('recentTransactionsList');
    if (!container) return;
    
    try {
        const transactions = await apiCall('/api/transactions');
        
        if (!transactions || transactions.length === 0) {
            container.innerHTML = '<div class="no-transactions">No transactions yet</div>';
            return;
        }
        
        const recent = transactions.slice(0, 5);
        
        container.innerHTML = recent.map(t => {
            const isSent = t.is_sent;
            const iconClass = isSent ? 'sent' : 'received';
            const amountClass = isSent ? 'sent' : 'received';
            const sign = isSent ? '-' : '+';
            let counterparty = isSent ? t.receiver_name : t.sender_name;
            let counterpartyPhone = isSent ? t.receiver_phone : t.sender_phone;
            
            if (!counterparty || counterparty === 'External User' || counterparty === 'null') {
                if (counterpartyPhone) {
                    counterparty = formatPhoneNumber(counterpartyPhone);
                } else {
                    counterparty = isSent ? 'Sent to User' : 'Received from User';
                }
            }
            
            return `
                <div class="transaction-item" onclick="viewReceipt('${t.id}')">
                    <div class="transaction-left">
                        <div class="transaction-icon ${iconClass}">
                            <i class="fas ${isSent ? 'fa-arrow-up' : 'fa-arrow-down'}"></i>
                        </div>
                        <div class="transaction-info">
                            <span class="transaction-name">${escapeHtml(counterparty)}</span>
                            <span class="transaction-date">${new Date(t.created_at).toLocaleDateString()}</span>
                        </div>
                    </div>
                    <div class="transaction-amount ${amountClass}">
                        ${sign} ${formatCurrency(t.amount)}
                    </div>
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Load recent transactions error:', error);
        container.innerHTML = '<div class="no-transactions">Unable to load transactions</div>';
    }
}

async function loadPeople() {
    try {
        console.log('Fetching people...');
        const people = await apiCall('/api/people');
        console.log('People received:', people);
        
        const container = document.getElementById('peopleList');
        const countElement = document.getElementById('peopleCount');
        
        if (countElement) {
            countElement.textContent = people.length;
        }
        
        if (!container) return;
        
        if (!people || people.length === 0) {
            container.innerHTML = '<div class="no-people"><i class="fas fa-users-slash"></i><p>No contacts yet. Add contacts to see them here!</p></div>';
            return;
        }
        
        const sortedPeople = [...people].sort((a, b) => {
            if (a.is_favorite && !b.is_favorite) return -1;
            if (!a.is_favorite && b.is_favorite) return 1;
            return a.name.localeCompare(b.name);
        });
        
        container.innerHTML = sortedPeople.map(person => {
            const identifier = person.id || person.phone;
            const initial = person.initial || 'ZP';
            const displayName = person.name.length > 12 ? person.name.substring(0, 12) + '...' : person.name;
            
            return `
                <div class="person-circle" 
                     onclick="goToTransactionHistory('${encodeURIComponent(identifier)}')"
                     title="${escapeHtml(person.name)} (${escapeHtml(person.phone)})">
                    <div class="circle-avatar" style="background: ${getRandomColor(identifier)}">
                        ${initial}
                        ${person.is_favorite ? '<i class="fas fa-star favorite-indicator"></i>' : ''}
                    </div>
                    <span class="person-name">${escapeHtml(displayName)}</span>
                    ${!person.is_registered ? '<span class="external-badge" title="External User"><i class="fas fa-external-link-alt"></i></span>' : ''}
                </div>
            `;
        }).join('');
    } catch (error) {
        console.error('Load people error:', error);
        const container = document.getElementById('peopleList');
        if (container) {
            container.innerHTML = '<div class="no-people">Unable to load contacts. Please refresh the page.</div>';
        }
    }
}

function goToTransactionHistory(identifier) {
    window.location.href = `/transaction-history/${identifier}`;
}

// ====================
// CONTACT FUNCTIONS
// ====================

async function loadContacts() {
    try {
        console.log('Fetching contacts...');
        const contacts = await apiCall('/api/contacts');
        console.log('Contacts received:', contacts);
        
        const container = document.getElementById('contactsList');
        
        if (!container) return;
        
        if (!contacts || contacts.length === 0) {
            container.innerHTML = '<div class="no-contacts"><i class="fas fa-address-book"></i><p>No contacts yet. Add your first contact!</p></div>';
            return;
        }
        
        const favoriteContacts = contacts.filter(c => c.is_favorite);
        const otherContacts = contacts.filter(c => !c.is_favorite);
        
        let html = '';
        
        if (favoriteContacts.length > 0) {
            html += '<div class="contact-section"><h4><i class="fas fa-star"></i> Favorites</h4>';
            favoriteContacts.forEach(contact => {
                html += createContactCard(contact);
            });
            html += '</div>';
        }
        
        if (otherContacts.length > 0) {
            html += '<div class="contact-section"><h4><i class="fas fa-users"></i> All Contacts</h4>';
            otherContacts.forEach(contact => {
                html += createContactCard(contact);
            });
            html += '</div>';
        }
        
        container.innerHTML = html;
    } catch (error) {
        console.error('Load contacts error:', error);
        const container = document.getElementById('contactsList');
        if (container) {
            container.innerHTML = '<div class="no-contacts">Error loading contacts</div>';
        }
    }
}

function createContactCard(contact) {
    const typeIcon = contact.is_registered ? 
        '<span class="contact-badge internal"><i class="fas fa-check-circle"></i> Zoro User</span>' : 
        '<span class="contact-badge external"><i class="fas fa-external-link-alt"></i> External</span>';
    
    const favoriteIcon = contact.is_favorite ? 
        '<button class="favorite-btn active" onclick="event.stopPropagation(); toggleFavorite(' + contact.id + ', false)"><i class="fas fa-star"></i></button>' : 
        '<button class="favorite-btn" onclick="event.stopPropagation(); toggleFavorite(' + contact.id + ', true)"><i class="far fa-star"></i></button>';
    
    const escapedName = escapeHtml(contact.name);
    const escapedPhone = escapeHtml(contact.phone);
    
    return `
        <div class="contact-card" onclick="sendToContact('${escapedPhone}', '${escapedName.replace(/'/g, "\\'")}')">
            <div class="contact-avatar">
                <i class="fas fa-user-circle"></i>
            </div>
            <div class="contact-info">
                <div class="contact-name">${escapedName}</div>
                <div class="contact-phone">${escapedPhone}</div>
                ${typeIcon}
            </div>
            <div class="contact-actions" onclick="event.stopPropagation()">
                ${favoriteIcon}
                <button class="send-btn" onclick="sendToContact('${escapedPhone}', '${escapedName.replace(/'/g, "\\'")}')">
                    <i class="fas fa-paper-plane"></i>
                </button>
            </div>
        </div>
    `;
}

async function toggleFavorite(contactId, isFavorite) {
    try {
        await apiCall(`/api/contacts/${contactId}/favorite`, {
            method: 'PUT',
            body: JSON.stringify({ is_favorite: isFavorite ? 1 : 0 })
        });
        await loadContacts();
        await loadPeople();
        showNotification(isFavorite ? 'Added to favorites' : 'Removed from favorites', 'success');
    } catch (error) {
        console.error('Toggle favorite error:', error);
    }
}

function sendToContact(phone, name) {
    const identifierInput = document.getElementById('recipientIdentifier');
    if (identifierInput) {
        identifierInput.value = phone;
    }
    showTab('send');
    showNotification(`Ready to send money to ${name}`, 'info');
}

function showAddContactModal() {
    const modal = document.getElementById('addContactModal');
    if (modal) {
        modal.style.display = 'block';
    }
}

function closeAddContactModal() {
    const modal = document.getElementById('addContactModal');
    const nameInput = document.getElementById('newContactName');
    const phoneInput = document.getElementById('newContactPhone');
    
    if (modal) {
        modal.style.display = 'none';
    }
    if (nameInput) {
        nameInput.value = '';
    }
    if (phoneInput) {
        phoneInput.value = '';
    }
}

async function addNewContact() {
    const nameInput = document.getElementById('newContactName');
    const phoneInput = document.getElementById('newContactPhone');
    
    if (!nameInput || !phoneInput) {
        console.error('Contact form elements not found');
        showNotification('Error: Contact form not ready', 'error');
        return;
    }
    
    const name = nameInput.value;
    let phone = phoneInput.value;
    
    if (!name || !phone) {
        showNotification('Please fill all fields', 'error');
        return;
    }
    
    phone = phone.replace(/[\s\-\(\)]/g, '');
    if (!phone.startsWith('+')) {
        phone = '+91' + phone;
    }
    
    try {
        await apiCall('/api/contacts', {
            method: 'POST',
            body: JSON.stringify({ name, phone })
        });
        
        showNotification('Contact added successfully!', 'success');
        closeAddContactModal();
        await loadContacts();
        await loadPeople();
        
        if (window.location.pathname === '/contacts-page') {
            await loadAllContacts();
        }
    } catch (error) {
        console.error('Add contact error:', error);
        if (error.message === 'Contact already exists') {
            showNotification('This contact already exists in your list!', 'warning');
        } else {
            showNotification(error.message || 'Failed to add contact', 'error');
        }
    }
}

// ====================
// TRANSACTION FUNCTIONS
// ====================

async function sendMoney(event) {
    event.preventDefault();
    
    const identifierInput = document.getElementById('recipientIdentifier');
    const amountInput = document.getElementById('sendAmount');
    const noteInput = document.getElementById('sendNote');
    
    if (!identifierInput || !amountInput) {
        showNotification('Form elements not found', 'error');
        return;
    }
    
    const identifier = identifierInput.value;
    const amount = amountInput.value;
    const note = noteInput ? noteInput.value : '';
    
    if (!identifier || !amount) {
        showNotification('Please fill all required fields', 'error');
        return;
    }
    
    if (parseFloat(amount) <= 0) {
        showNotification('Please enter a valid amount', 'error');
        return;
    }
    
    const transactionData = {
        identifier: identifier,
        amount: parseFloat(amount),
        note: note
    };
    
    sessionStorage.setItem('pendingTransaction', JSON.stringify(transactionData));
    window.location.href = '/verify-pin';
}

async function requestMoney(event) {
    event.preventDefault();
    
    const phoneInput = document.getElementById('requestPhone');
    const amountInput = document.getElementById('requestAmount');
    const noteInput = document.getElementById('requestNote');
    const smsStatusDiv = document.getElementById('smsStatus');
    
    if (!phoneInput || !amountInput) {
        showNotification('Form elements not found', 'error');
        return;
    }
    
    let phone = phoneInput.value;
    const amount = amountInput.value;
    const note = noteInput ? noteInput.value : '';
    
    if (!phone || !amount) {
        showNotification('Please fill all required fields', 'error');
        return;
    }
    
    if (parseFloat(amount) <= 0) {
        showNotification('Please enter a valid amount', 'error');
        return;
    }
    
    phone = phone.replace(/[\s\-\(\)]/g, '');
    if (!phone.startsWith('+')) {
        phone = '+91' + phone;
    }
    
    const submitBtn = event.submitter;
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending request...';
    
    if (smsStatusDiv) {
        smsStatusDiv.style.display = 'none';
        smsStatusDiv.innerHTML = '';
    }
    
    try {
        const response = await fetch('/api/request_money', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone, amount: parseFloat(amount), note })
        });
        
        if (response.status === 401) {
            sessionStorage.setItem('redirectAfterLogin', window.location.pathname);
            window.location.href = '/';
            return;
        }
        
        const data = await response.json();
        
        if (response.ok) {
            showNotification(data.message, 'success');
            
            if (smsStatusDiv && !data.is_registered) {
                smsStatusDiv.style.display = 'block';
                if (data.sms_sent) {
                    smsStatusDiv.innerHTML = `
                        <div class="sms-success">
                            <i class="fas fa-check-circle"></i> 
                            SMS invitation sent to ${data.target_phone}
                        </div>
                    `;
                    smsStatusDiv.className = 'sms-status success';
                } else {
                    smsStatusDiv.innerHTML = `
                        <div class="sms-warning">
                            <i class="fas fa-exclamation-triangle"></i> 
                            Request sent! We'll notify them.
                        </div>
                    `;
                    smsStatusDiv.className = 'sms-status warning';
                }
                
                setTimeout(() => {
                    smsStatusDiv.style.display = 'none';
                }, 5000);
            }
            
            phoneInput.value = '';
            amountInput.value = '';
            if (noteInput) noteInput.value = '';
            
            await loadPendingRequests();
        } else {
            showNotification(data.error || 'Failed to send request', 'error');
        }
    } catch (error) {
        console.error('Request money error:', error);
        if (error.message !== 'Authentication required') {
            showNotification(error.message || 'Failed to send request', 'error');
        }
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

// ====================
// PENDING REQUESTS FUNCTIONS
// ====================

async function loadPendingRequests() {
    try {
        const response = await fetch('/api/external_requests');
        if (response.status === 401) return;
        
        const requests = await response.json();
        
        const section = document.getElementById('pendingRequestsSection');
        const container = document.getElementById('pendingRequestsList');
        const countEl = document.getElementById('requestsCount');
        
        if (!section || !container) return;
        
        if (requests && requests.length > 0) {
            section.style.display = 'block';
            if (countEl) countEl.textContent = requests.length;
            
            container.innerHTML = requests.map(req => `
                <div class="pending-request-card">
                    <div class="request-details">
                        <div class="request-phone">${escapeHtml(formatPhoneNumber(req.target_phone))}</div>
                        <div class="request-amount">${formatCurrency(req.amount)}</div>
                        ${req.note ? `<div class="request-note">${escapeHtml(req.note)}</div>` : ''}
                        <div class="request-date">${new Date(req.created_at).toLocaleDateString()}</div>
                    </div>
                    <div class="request-status">
                        <i class="fas fa-hourglass-half"></i> Pending
                    </div>
                </div>
            `).join('');
        } else {
            section.style.display = 'none';
        }
    } catch (error) {
        console.error('Load pending requests error:', error);
    }
}

// ====================
// TRANSACTION HISTORY PAGE FUNCTIONS
// ====================

async function initTransactionHistoryPage() {
    const data = window.transactionHistoryData;
    if (!data) {
        showNotification('Error loading transaction history', 'error');
        return;
    }
    
    const otherUser = data.otherUser;
    const isExternal = data.isExternal;
    const isInContacts = data.isInContacts;
    const contactName = data.contactName;
    
    const avatarEl = document.getElementById('historyAvatar');
    const nameEl = document.getElementById('historyName');
    const phoneEl = document.getElementById('historyPhone');
    const badgeEl = document.getElementById('historyBadge');
    const addToContactBtn = document.getElementById('addToContactBtn');
    
    if (otherUser) {
        const phone = otherUser.phone || '';
        
        let displayName = '';
        if (isInContacts && contactName) {
            displayName = contactName;
        } else if (otherUser.name && otherUser.name !== phone) {
            displayName = otherUser.name;
        } else {
            displayName = formatPhoneNumber(phone);
        }
        
        const initial = displayName[0]?.toUpperCase() || 'ZP';
        
        if (avatarEl) {
            avatarEl.textContent = initial;
            avatarEl.style.background = getRandomColor(phone);
        }
        if (nameEl) nameEl.textContent = displayName;
        if (phoneEl) phoneEl.textContent = formatPhoneNumber(phone);
        
        if (!isInContacts && otherUser.id !== window.currentUserId) {
            if (addToContactBtn) {
                addToContactBtn.style.display = 'flex';
                window.pendingContactPhone = phone;
            }
        } else {
            if (addToContactBtn) addToContactBtn.style.display = 'none';
        }
        
        if (badgeEl) {
            if (isExternal) {
                badgeEl.innerHTML = '<span class="badge external"><i class="fas fa-external-link-alt"></i> External Contact</span>';
                const requestBtn = document.getElementById('requestFromUserBtn');
                if (requestBtn) requestBtn.style.display = 'none';
            } else {
                badgeEl.innerHTML = '<span class="badge internal"><i class="fas fa-check-circle"></i> Zoro Pay User</span>';
                const requestBtn = document.getElementById('requestFromUserBtn');
                if (requestBtn) requestBtn.style.display = 'flex';
            }
        }
    }
    
    const identifier = data.otherUserId || otherUser?.phone;
    await loadTransactionSummary(identifier);
    await loadTransactionHistory(identifier);
}

function getTransactionDisplayName(transaction, isSent, contactsMap) {
    let counterpartyPhone = isSent ? transaction.receiver_phone : transaction.sender_phone;
    let counterpartyName = isSent ? transaction.receiver_name : transaction.sender_name;
    
    if (counterpartyPhone && contactsMap && contactsMap.has(counterpartyPhone)) {
        const contact = contactsMap.get(counterpartyPhone);
        if (contact && contact.name) {
            return contact.name;
        }
    }
    
    if (counterpartyName && counterpartyName !== 'External User' && counterpartyName !== 'null') {
        return counterpartyName;
    }
    
    if (counterpartyPhone) {
        return formatPhoneNumber(counterpartyPhone);
    }
    
    return isSent ? 'Sent to User' : 'Received from User';
}

async function loadTransactionSummary(identifier) {
    try {
        const summary = await apiCall(`/api/transaction_summary/${encodeURIComponent(identifier)}`);
        
        const totalSentEl = document.getElementById('totalSent');
        const totalReceivedEl = document.getElementById('totalReceived');
        const transactionCountEl = document.getElementById('transactionCount');
        
        if (totalSentEl) totalSentEl.textContent = formatCurrency(summary.total_sent);
        if (totalReceivedEl) totalReceivedEl.textContent = formatCurrency(summary.total_received);
        if (transactionCountEl) transactionCountEl.textContent = summary.transaction_count;
    } catch (error) {
        console.error('Load transaction summary error:', error);
    }
}

async function loadTransactionHistory(identifier) {
    try {
        console.log('Loading transactions for:', identifier);
        
        let contactsMap = new Map();
        try {
            const contactsResponse = await fetch('/api/contacts');
            if (contactsResponse.ok) {
                const contacts = await contactsResponse.json();
                contacts.forEach(contact => {
                    if (contact.phone) {
                        contactsMap.set(contact.phone, {
                            name: contact.name,
                            is_registered: contact.is_registered
                        });
                    }
                });
            }
        } catch (error) {
            console.error('Error loading contacts for history:', error);
        }
        
        const transactions = await apiCall(`/api/transactions/with/${encodeURIComponent(identifier)}`);
        console.log('Transactions received:', transactions);
        
        const container = document.getElementById('transactionHistoryList');
        
        if (!container) return;
        
        if (!transactions || transactions.length === 0) {
            container.innerHTML = `
                <div class="no-transactions">
                    <i class="fas fa-exchange-alt"></i>
                    <p>No transactions yet</p>
                    <p class="no-transactions-hint">Send money to get started!</p>
                </div>
            `;
            return;
        }
        
        const grouped = groupTransactionsByDate(transactions);
        
        let html = '';
        
        for (const [date, txns] of Object.entries(grouped)) {
            html += `
                <div class="transaction-group">
                    <div class="group-header">
                        <i class="far fa-calendar-alt"></i> ${date}
                        <span class="group-count">${txns.length}</span>
                    </div>
            `;
            
            txns.forEach(t => {
                const isSent = t.is_sent;
                const cardClass = isSent ? 'sent' : 'received';
                const iconClass = isSent ? 'fa-arrow-up' : 'fa-arrow-down';
                const amountClass = isSent ? 'sent-amount' : 'received-amount';
                const sign = isSent ? '-' : '+';
                
                const displayName = getTransactionDisplayName(t, isSent, contactsMap);
                const displayPhone = t.counterparty_phone ? formatPhoneNumber(t.counterparty_phone) : '';
                
                html += `
                    <div class="transaction-history-card ${cardClass}" onclick="viewReceipt('${t.id}')">
                        <div class="transaction-icon">
                            <i class="fas ${iconClass}"></i>
                        </div>
                        <div class="transaction-details">
                            <div class="transaction-name">${escapeHtml(displayName)}</div>
                            ${displayPhone && displayName !== displayPhone ? `<div class="transaction-phone-small">${escapeHtml(displayPhone)}</div>` : ''}
                            <div class="transaction-note">${escapeHtml(t.note || 'No note')}</div>
                            <div class="transaction-date">${new Date(t.created_at).toLocaleString()}</div>
                            <div class="transaction-id">ID: ${t.id}</div>
                        </div>
                        <div class="transaction-amount ${amountClass}">
                            ${sign} ${formatCurrency(t.amount)}
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
        }
        
        container.innerHTML = html;
    } catch (error) {
        console.error('Load transaction history error:', error);
        const container = document.getElementById('transactionHistoryList');
        if (container) {
            container.innerHTML = '<div class="error-message">Error loading transactions. Please try again.</div>';
        }
    }
}

function groupTransactionsByDate(transactions) {
    const groups = {};
    
    transactions.forEach(t => {
        const date = new Date(t.created_at);
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        
        let dateKey;
        if (date.toDateString() === today.toDateString()) {
            dateKey = 'Today';
        } else if (date.toDateString() === yesterday.toDateString()) {
            dateKey = 'Yesterday';
        } else {
            dateKey = date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
        }
        
        if (!groups[dateKey]) {
            groups[dateKey] = [];
        }
        groups[dateKey].push(t);
    });
    
    return groups;
}

function goBack() {
    window.location.href = '/dashboard';
}

function sendToThisUser() {
    const data = window.transactionHistoryData;
    if (data && data.otherUser) {
        const phone = data.otherUser.phone;
        window.location.href = `/dashboard?sendTo=${encodeURIComponent(phone)}`;
    }
}

function requestFromThisUser() {
    const data = window.transactionHistoryData;
    if (data && data.otherUser && !data.isExternal) {
        const phone = data.otherUser.phone;
        window.location.href = `/dashboard?requestFrom=${encodeURIComponent(phone)}`;
    }
}

async function addToContactFromHistory() {
    const data = window.transactionHistoryData;
    if (!data || !data.otherUser) {
        showNotification('No user data available', 'error');
        return;
    }
    
    const otherUser = data.otherUser;
    const phone = otherUser.phone;
    
    if (!phone) {
        showNotification('No phone number available for this user', 'error');
        return;
    }
    
    try {
        const existingContacts = await apiCall('/api/contacts');
        const contactExists = existingContacts.some(contact => contact.phone === phone);
        
        if (contactExists) {
            showNotification('This contact is already in your list!', 'warning');
            const addToContactBtn = document.getElementById('addToContactBtn');
            if (addToContactBtn) addToContactBtn.style.display = 'none';
            return;
        }
        
        const defaultName = otherUser.name && otherUser.name !== phone ? otherUser.name : formatPhoneNumber(phone);
        const name = prompt('Enter name for this contact:', defaultName);
        
        if (!name || name.trim() === '') {
            showNotification('Contact name is required', 'error');
            return;
        }
        
        await apiCall('/api/contacts', {
            method: 'POST',
            body: JSON.stringify({ name: name.trim(), phone })
        });
        
        showNotification('Contact added successfully!', 'success');
        
        const addToContactBtn = document.getElementById('addToContactBtn');
        if (addToContactBtn) addToContactBtn.style.display = 'none';
        
        const nameEl = document.getElementById('historyName');
        if (nameEl) nameEl.textContent = name.trim();
        
        await loadContacts();
        await loadPeople();
        
    } catch (error) {
        console.error('Add contact error:', error);
        if (error.message === 'Contact already exists') {
            showNotification('This contact is already in your list!', 'warning');
            const addToContactBtn = document.getElementById('addToContactBtn');
            if (addToContactBtn) addToContactBtn.style.display = 'none';
        } else {
            showNotification(error.message || 'Failed to add contact', 'error');
        }
    }
}

// ====================
// PROFILE FUNCTIONS
// ====================

async function loadProfile() {
    try {
        const user = await apiCall('/api/user');
        const nameElement = document.getElementById('userName');
        const phoneElement = document.getElementById('userPhone');
        const upiElement = document.getElementById('userUpiId');
        
        if (nameElement) nameElement.textContent = user.name;
        if (phoneElement) phoneElement.textContent = formatPhoneNumber(user.phone);
        if (upiElement) upiElement.textContent = user.upi_id;
        
        const qrData = await apiCall('/api/generate_qr');
        const qrElement = document.getElementById('qrCode');
        if (qrElement) qrElement.src = qrData.qr_url;
        
        const referralData = await apiCall('/api/referral_stats');
        const codeElement = document.getElementById('referralCode');
        const countElement = document.getElementById('referralCount');
        const bonusElement = document.getElementById('referralBonus');
        
        if (codeElement) codeElement.textContent = referralData.referral_code;
        if (countElement) countElement.textContent = referralData.referral_count;
        if (bonusElement) bonusElement.textContent = formatCurrency(referralData.referral_bonus);
    } catch (error) {
        console.error('Load profile error:', error);
    }
}

function downloadQR() {
    const qrImg = document.getElementById('qrCode');
    if (qrImg && qrImg.src) {
        const link = document.createElement('a');
        link.download = 'zoropay_qr.png';
        link.href = qrImg.src;
        link.click();
        showNotification('QR code downloaded!', 'success');
    }
}

function copyReferralCode() {
    const codeElement = document.getElementById('referralCode');
    if (!codeElement) return;
    
    const code = codeElement.textContent;
    navigator.clipboard.writeText(code);
    showNotification('📋 Referral code copied!', 'success');
}

function copyUpiId() {
    const upiElement = document.getElementById('userUpiId');
    if (!upiElement) return;
    
    const upiId = upiElement.textContent;
    navigator.clipboard.writeText(upiId);
    showNotification('📋 UPI ID copied!', 'success');
}

// ====================
// SETTINGS FUNCTIONS
// ====================

async function loadSettings() {
    try {
        const user = await apiCall('/api/user');
        const nameInput = document.getElementById('userNameInput');
        const upiIdSpan = document.getElementById('upiId');
        const apiKeyInput = document.getElementById('apiKey');
        const apiUsageCount = document.getElementById('apiUsageCount');
        const lastApiUsed = document.getElementById('lastApiUsed');
        const cashbackEarned = document.getElementById('cashbackEarned');
        
        if (nameInput) nameInput.value = user.name;
        if (upiIdSpan) upiIdSpan.textContent = user.upi_id;
        if (apiKeyInput) apiKeyInput.value = user.api_key || 'No API key generated';
        if (apiUsageCount) apiUsageCount.textContent = user.api_usage_count || 0;
        if (cashbackEarned) cashbackEarned.textContent = formatCurrency(user.cashback_earned || 0);
        
        if (lastApiUsed && user.last_api_used) {
            lastApiUsed.textContent = new Date(user.last_api_used).toLocaleString();
        } else if (lastApiUsed) {
            lastApiUsed.textContent = 'Never';
        }
    } catch (error) {
        console.error('Load settings error:', error);
    }
}

async function updateName() {
    const nameInput = document.getElementById('userNameInput');
    
    if (!nameInput) {
        showNotification('Name input not found', 'error');
        return;
    }
    
    const name = nameInput.value;
    
    if (!name) {
        showNotification('Please enter a name', 'error');
        return;
    }
    
    try {
        await apiCall('/api/update_name', {
            method: 'POST',
            body: JSON.stringify({ name })
        });
        
        showNotification('✅ Name updated successfully!', 'success');
        loadSettings();
    } catch (error) {
        console.error('Update name error:', error);
    }
}

async function generateApiKey() {
    try {
        const data = await apiCall('/api/generate_api_key', { method: 'POST' });
        const apiKeyInput = document.getElementById('apiKey');
        if (apiKeyInput) apiKeyInput.value = data.api_key;
        showNotification('New API key generated successfully!', 'success');
        loadSettings();
    } catch (error) {
        showNotification('Failed to generate API key', 'error');
    }
}

function copyUPI() {
    const upiId = document.getElementById('upiId');
    if (upiId && upiId.textContent) {
        navigator.clipboard.writeText(upiId.textContent);
        showNotification('UPI ID copied to clipboard!', 'success');
    }
}

function copyAPIKey() {
    const apiKey = document.getElementById('apiKey');
    if (apiKey && apiKey.value && apiKey.value !== 'No API key generated') {
        navigator.clipboard.writeText(apiKey.value);
        showNotification('API key copied to clipboard!', 'success');
    } else {
        showNotification('Generate an API key first', 'warning');
    }
}

async function changePin() {
    const oldPinInput = document.getElementById('oldPin');
    const newPinInput = document.getElementById('newPin');
    
    if (!oldPinInput || !newPinInput) {
        showNotification('PIN inputs not found', 'error');
        return;
    }
    
    const oldPin = oldPinInput.value;
    const newPin = newPinInput.value;
    
    if (!oldPin || !newPin) {
        showNotification('Please fill all fields', 'error');
        return;
    }
    
    if ((newPin.length !== 4 && newPin.length !== 6) || !/^\d+$/.test(newPin)) {
        showNotification('PIN must be 4 or 6 digits', 'error');
        return;
    }
    
    try {
        await apiCall('/api/change_pin', {
            method: 'POST',
            body: JSON.stringify({ old_pin: oldPin, new_pin: newPin })
        });
        
        showNotification('🔐 PIN changed successfully!', 'success');
        oldPinInput.value = '';
        newPinInput.value = '';
    } catch (error) {
        console.error('Change PIN error:', error);
    }
}

async function logout() {
    try {
        await apiCall('/logout', { method: 'POST' });
        localStorage.removeItem('user');
        localStorage.removeItem('jwt_token');
        showNotification('👋 Logged out successfully', 'success');
        setTimeout(() => {
            window.location.href = '/';
        }, 1000);
    } catch (error) {
        console.error('Logout error:', error);
    }
}

// ====================
// RECEIPT FUNCTIONS
// ====================

async function loadReceipt() {
    const transactionId = window.location.pathname.split('/').pop();
    
    if (!transactionId) return;
    
    try {
        const transaction = await apiCall(`/api/transaction/${transactionId}`);
        
        if (transaction) {
            const txnIdElement = document.getElementById('txnId');
            const txnDateElement = document.getElementById('txnDate');
            const senderElement = document.getElementById('sender');
            const receiverElement = document.getElementById('receiver');
            const amountElement = document.getElementById('amount');
            const noteElement = document.getElementById('note');
            const statusElement = document.getElementById('status');
            const receiptStatus = document.getElementById('receiptStatus');
            
            if (txnIdElement) txnIdElement.textContent = transaction.id;
            if (txnDateElement) txnDateElement.textContent = new Date(transaction.created_at).toLocaleString();
            if (senderElement) senderElement.textContent = transaction.sender_name || 'System';
            if (receiverElement) receiverElement.textContent = transaction.receiver_name || 'External';
            if (amountElement) amountElement.textContent = formatCurrency(transaction.amount);
            if (noteElement) noteElement.textContent = transaction.note || 'No note';
            
            if (statusElement) {
                statusElement.innerHTML = '<span class="status-badge success"><i class="fas fa-check-circle"></i> Completed</span>';
            }
            if (receiptStatus) {
                receiptStatus.innerHTML = '<div class="status-message success"><i class="fas fa-check-circle"></i> Transaction completed successfully</div>';
            }
        } else {
            showNotification('Transaction not found', 'error');
        }
    } catch (error) {
        console.error('Load receipt error:', error);
        showNotification('Failed to load receipt', 'error');
    }
}

async function downloadReceipt() {
    const transactionId = window.location.pathname.split('/').pop();
    
    if (!transactionId) return;
    
    try {
        window.location.href = `/api/download_receipt/${transactionId}`;
        showNotification('📄 Receipt downloaded!', 'success');
    } catch (error) {
        console.error('Download receipt error:', error);
        showNotification('Failed to download receipt', 'error');
    }
}

function viewReceipt(transactionId) {
    window.location.href = `/receipt/${transactionId}`;
}

// ====================
// VERIFY PIN FUNCTIONS
// ====================

async function verifyPinAndCompleteTransaction() {
    const pinInputs = document.querySelectorAll('.pin-input');
    let pin = '';
    pinInputs.forEach(input => {
        pin += input.value;
    });
    
    if (!pin || pin.length < 4) {
        showNotification('Please enter complete PIN', 'error');
        return;
    }
    
    const pendingTransaction = sessionStorage.getItem('pendingTransaction');
    if (!pendingTransaction) {
        showNotification('No pending transaction found', 'error');
        window.location.href = '/dashboard';
        return;
    }
    
    const transaction = JSON.parse(pendingTransaction);
    
    try {
        const verifyBtn = document.querySelector('.verify-btn');
        if (verifyBtn) {
            verifyBtn.disabled = true;
            verifyBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
        }
        
        const response = await fetch('/api/send_money', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                identifier: transaction.identifier,
                amount: transaction.amount,
                note: transaction.note,
                pin: pin
            })
        });
        
        if (response.status === 401) {
            sessionStorage.setItem('pendingTransaction', JSON.stringify(transaction));
            window.location.href = '/';
            return;
        }
        
        const data = await response.json();
        
        if (response.ok) {
            let message = data.message;
            if (data.cashback) {
                message += ` + ₹${data.cashback} cashback earned!`;
            }
            showNotification(message, 'success');
            sessionStorage.removeItem('pendingTransaction');
            setTimeout(() => {
                window.location.href = '/dashboard';
            }, 2000);
        } else {
            showNotification(data.error, 'error');
            if (verifyBtn) {
                verifyBtn.disabled = false;
                verifyBtn.innerHTML = '<i class="fas fa-check-circle"></i> Verify & Pay';
            }
            pinInputs.forEach(input => {
                input.value = '';
                if (input.nextElementSibling) {
                    input.nextElementSibling.focus();
                }
            });
        }
    } catch (error) {
        console.error('Transaction error:', error);
        showNotification('Transaction failed. Please try again.', 'error');
        const verifyBtn = document.querySelector('.verify-btn');
        if (verifyBtn) {
            verifyBtn.disabled = false;
            verifyBtn.innerHTML = '<i class="fas fa-check-circle"></i> Verify & Pay';
        }
    }
}

function moveToNextPin(current, nextId) {
    if (current.value.length === current.maxLength) {
        if (nextId) {
            document.getElementById(nextId).focus();
        } else {
            verifyPinAndCompleteTransaction();
        }
    }
}

// ====================
// UI HELPERS
// ====================

function showTab(tab) {
    const tabs = document.querySelectorAll('.tab-btn');
    const contents = document.querySelectorAll('.tab-content');
    
    tabs.forEach(btn => btn.classList.remove('active'));
    contents.forEach(content => content.classList.remove('active'));
    
    if (tab === 'send') {
        if (tabs[0]) tabs[0].classList.add('active');
        const sendTab = document.getElementById('sendTab');
        if (sendTab) sendTab.classList.add('active');
    } else if (tab === 'request') {
        if (tabs[1]) tabs[1].classList.add('active');
        const requestTab = document.getElementById('requestTab');
        if (requestTab) requestTab.classList.add('active');
    } else if (tab === 'contacts') {
        if (tabs[2]) tabs[2].classList.add('active');
        const contactsTab = document.getElementById('contactsTab');
        if (contactsTab) contactsTab.classList.add('active');
    }
}

// ====================
// PIN SETUP FUNCTIONS
// ====================

let selectedPinType = '4';
let currentPin = '';

function updatePinDisplay() {
    const pinDisplay = document.getElementById('pinDisplay');
    if (!pinDisplay) return;
    
    const maxLength = selectedPinType === '4' ? 4 : 6;
    pinDisplay.innerHTML = '';
    
    for (let i = 0; i < maxLength; i++) {
        const dot = document.createElement('i');
        dot.className = i < currentPin.length ? 'fas fa-circle filled' : 'fas fa-circle';
        pinDisplay.appendChild(dot);
    }
}

function generateKeypad() {
    const keypad = document.getElementById('pinKeypad');
    if (!keypad) return;
    
    const buttons = [
        '1', '2', '3',
        '4', '5', '6',
        '7', '8', '9',
        '<i class="fas fa-backspace"></i>', '0', '<i class="fas fa-check"></i>'
    ];
    
    keypad.innerHTML = '';
    buttons.forEach(btn => {
        const btnElement = document.createElement('button');
        btnElement.className = 'keypad-btn';
        btnElement.innerHTML = btn;
        btnElement.onclick = () => handleKeypadClick(btn);
        keypad.appendChild(btnElement);
    });
}

function handleKeypadClick(value) {
    const maxLength = selectedPinType === '4' ? 4 : 6;
    
    if (value === '<i class="fas fa-backspace"></i>') {
        currentPin = currentPin.slice(0, -1);
        updatePinDisplay();
        const confirmBtn = document.getElementById('confirmPinBtn');
        if (confirmBtn) confirmBtn.disabled = currentPin.length !== parseInt(selectedPinType);
    } else if (value === '<i class="fas fa-check"></i>') {
        if (currentPin.length === parseInt(selectedPinType)) {
            confirmPin();
        }
    } else if (currentPin.length < maxLength) {
        currentPin += value;
        updatePinDisplay();
        const confirmBtn = document.getElementById('confirmPinBtn');
        if (confirmBtn) confirmBtn.disabled = currentPin.length !== parseInt(selectedPinType);
    }
}

async function confirmPin() {
    const confirmBtn = document.getElementById('confirmPinBtn');
    if (!confirmBtn) return;
    
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Setting up PIN...';
    
    try {
        const response = await fetch('/api/setup_pin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                pin: currentPin, 
                pin_type: selectedPinType 
            })
        });
        
        if (response.status === 401) {
            window.location.href = '/';
            return;
        }
        
        const data = await response.json();
        
        if (response.ok) {
            showNotification('✅ PIN setup successful! Redirecting...', 'success');
            setTimeout(() => {
                window.location.href = '/dashboard';
            }, 1500);
        } else {
            showNotification(data.error, 'error');
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '<i class="fas fa-check-circle"></i> Confirm PIN';
            currentPin = '';
            updatePinDisplay();
        }
    } catch (error) {
        showNotification('Failed to setup PIN', 'error');
        confirmBtn.disabled = false;
        confirmBtn.innerHTML = '<i class="fas fa-check-circle"></i> Confirm PIN';
        currentPin = '';
        updatePinDisplay();
    }
}

// ====================
// CONTACTS PAGE FUNCTIONS
// ====================

async function loadAllContacts() {
    try {
        const contacts = await apiCall('/api/contacts');
        const container = document.getElementById('allContactsList');
        
        if (!container) return;
        
        if (!contacts || contacts.length === 0) {
            container.innerHTML = '<div class="no-contacts"><i class="fas fa-address-book"></i><p>No contacts found</p></div>';
            return;
        }
        
        container.innerHTML = contacts.map(contact => `
            <div class="contact-management-card" onclick="openEditContactModal(${contact.id}, '${escapeHtml(contact.name).replace(/'/g, "\\'")}', '${escapeHtml(contact.phone)}')">
                <div class="contact-avatar">
                    <i class="fas fa-user-circle"></i>
                </div>
                <div class="contact-info">
                    <div class="contact-name">
                        ${escapeHtml(contact.name)}
                        ${contact.is_favorite ? '<i class="fas fa-star favorite-star"></i>' : ''}
                    </div>
                    <div class="contact-phone">${escapeHtml(formatPhoneNumber(contact.phone))}</div>
                    <div class="contact-type-badge">
                        ${contact.is_registered ? 
                            '<span class="badge internal"><i class="fas fa-check-circle"></i> Zoro User</span>' : 
                            '<span class="badge external"><i class="fas fa-external-link-alt"></i> External</span>'}
                    </div>
                </div>
                <div class="contact-management-actions">
                    <button class="icon-btn-small" onclick="event.stopPropagation(); toggleFavoriteFromPage(${contact.id}, ${!contact.is_favorite})">
                        <i class="fas fa-${contact.is_favorite ? 'star' : 'star-o'}"></i>
                    </button>
                    <button class="icon-btn-small" onclick="event.stopPropagation(); sendToContact('${escapeHtml(contact.phone)}', '${escapeHtml(contact.name).replace(/'/g, "\\'")}')">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Load all contacts error:', error);
    }
}

let currentEditContactId = null;

function openEditContactModal(id, name, phone) {
    currentEditContactId = id;
    const idInput = document.getElementById('editContactId');
    const nameInput = document.getElementById('editContactName');
    const phoneInput = document.getElementById('editContactPhone');
    const modal = document.getElementById('editContactModal');
    
    if (idInput) idInput.value = id;
    if (nameInput) nameInput.value = name;
    if (phoneInput) phoneInput.value = formatPhoneNumber(phone);
    if (modal) modal.style.display = 'block';
}

function closeEditContactModal() {
    const modal = document.getElementById('editContactModal');
    if (modal) modal.style.display = 'none';
    currentEditContactId = null;
}

async function updateContactDetails() {
    const nameInput = document.getElementById('editContactName');
    
    if (!nameInput || !currentEditContactId) {
        showNotification('Error updating contact', 'error');
        return;
    }
    
    const name = nameInput.value;
    
    if (!name) {
        showNotification('Name is required', 'error');
        return;
    }
    
    try {
        await apiCall(`/api/contacts/${currentEditContactId}`, {
            method: 'PUT',
            body: JSON.stringify({ name })
        });
        
        showNotification('Contact updated successfully!', 'success');
        closeEditContactModal();
        await loadAllContacts();
        await loadContacts();
        await loadPeople();
    } catch (error) {
        console.error('Update contact error:', error);
    }
}

async function deleteContactFromModal() {
    if (!currentEditContactId) return;
    
    if (confirm('Are you sure you want to delete this contact?')) {
        try {
            await apiCall(`/api/contacts/${currentEditContactId}`, {
                method: 'DELETE'
            });
            
            showNotification('Contact deleted successfully!', 'success');
            closeEditContactModal();
            await loadAllContacts();
            await loadContacts();
            await loadPeople();
        } catch (error) {
            console.error('Delete contact error:', error);
        }
    }
}

async function toggleFavoriteFromPage(contactId, isFavorite) {
    try {
        await apiCall(`/api/contacts/${contactId}/favorite`, {
            method: 'PUT',
            body: JSON.stringify({ is_favorite: isFavorite ? 1 : 0 })
        });
        await loadAllContacts();
        await loadContacts();
        await loadPeople();
        showNotification(isFavorite ? 'Added to favorites' : 'Removed from favorites', 'success');
    } catch (error) {
        console.error('Toggle favorite error:', error);
    }
}

// ====================
// ADD BALANCE FUNCTIONS
// ====================

let addBalancePin = '';

function updateAddBalancePinDisplay() {
    const pinDisplay = document.getElementById('pinDisplay');
    if (!pinDisplay) return;
    
    pinDisplay.innerHTML = '';
    for (let i = 0; i < 4; i++) {
        const dot = document.createElement('i');
        dot.className = i < addBalancePin.length ? 'fas fa-circle filled' : 'fas fa-circle';
        pinDisplay.appendChild(dot);
    }
}

function generateAddBalanceKeypad() {
    const keypad = document.getElementById('pinKeypad');
    if (!keypad) return;
    
    const buttons = [
        '1', '2', '3',
        '4', '5', '6',
        '7', '8', '9',
        '<i class="fas fa-backspace"></i>', '0', '<i class="fas fa-check"></i>'
    ];
    
    keypad.innerHTML = '';
    buttons.forEach(btn => {
        const btnElement = document.createElement('button');
        btnElement.className = 'keypad-btn';
        btnElement.innerHTML = btn;
        btnElement.onclick = () => handleAddBalanceKeypadClick(btn);
        keypad.appendChild(btnElement);
    });
}

function handleAddBalanceKeypadClick(value) {
    if (value === '<i class="fas fa-backspace"></i>') {
        addBalancePin = addBalancePin.slice(0, -1);
        updateAddBalancePinDisplay();
    } else if (value === '<i class="fas fa-check"></i>') {
        if (addBalancePin.length === 4) {
            processAddBalance();
        }
    } else if (addBalancePin.length < 4) {
        addBalancePin += value;
        updateAddBalancePinDisplay();
    }
}

async function processAddBalance() {
    const amountInput = document.getElementById('addAmount');
    const paymentMethod = document.querySelector('input[name="paymentMethod"]:checked');
    
    if (!amountInput) {
        showNotification('Amount input not found', 'error');
        return;
    }
    
    const amount = parseFloat(amountInput.value);
    
    if (isNaN(amount) || amount <= 0) {
        showNotification('Please enter a valid amount', 'error');
        return;
    }
    
    if (amount < 10) {
        showNotification('Minimum amount to add is ₹10', 'error');
        return;
    }
    
    if (amount > 50000) {
        showNotification('Maximum amount per transaction is ₹50,000', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/add_balance', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                amount: amount,
                pin: addBalancePin,
                payment_method: paymentMethod ? paymentMethod.value : 'card'
            })
        });
        
        if (response.status === 401) {
            window.location.href = '/';
            return;
        }
        
        const data = await response.json();
        
        if (response.ok) {
            showNotification(data.message, 'success');
            setTimeout(() => {
                window.location.href = '/dashboard';
            }, 1500);
        } else {
            showNotification(data.error, 'error');
            addBalancePin = '';
            updateAddBalancePinDisplay();
        }
    } catch (error) {
        console.error('Add balance error:', error);
        showNotification('Failed to add balance', 'error');
        addBalancePin = '';
        updateAddBalancePinDisplay();
    }
}

function setPresetAmount(amount) {
    const amountInput = document.getElementById('addAmount');
    if (amountInput) {
        amountInput.value = amount;
    }
    
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('data-amount') == amount) {
            btn.classList.add('active');
        }
    });
}

// ====================
// ALL TRANSACTIONS PAGE (FIXED)
// ====================

async function loadAllTransactionsPage() {
    try {
        const response = await fetch('/api/transactions');
        if (response.status === 401) {
            window.location.href = '/';
            return;
        }
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const transactions = await response.json();
        console.log('Loaded all transactions:', transactions);
        
        const container = document.getElementById('allTransactionsList');
        
        if (!container) return;
        
        if (!transactions || transactions.length === 0) {
            container.innerHTML = '<div class="no-transactions"><i class="fas fa-exchange-alt"></i><p>No transactions yet</p></div>';
            return;
        }
        
        // Load contacts for better display names
        let contactsMap = new Map();
        try {
            const contactsResponse = await fetch('/api/contacts');
            if (contactsResponse.ok) {
                const contacts = await contactsResponse.json();
                contacts.forEach(contact => {
                    if (contact.phone) {
                        contactsMap.set(contact.phone, {
                            name: contact.name,
                            is_registered: contact.is_registered
                        });
                    }
                });
            }
        } catch (error) {
            console.error('Error loading contacts:', error);
        }
        
        const grouped = groupTransactionsByDate(transactions);
        
        let html = '';
        for (const [date, txns] of Object.entries(grouped)) {
            html += `<div class="transaction-group"><div class="group-header"><i class="far fa-calendar-alt"></i> ${date}<span class="group-count">${txns.length}</span></div>`;
            txns.forEach(t => {
                const isSent = t.is_sent;
                const cardClass = isSent ? 'sent' : 'received';
                const iconClass = isSent ? 'fa-arrow-up' : 'fa-arrow-down';
                const amountClass = isSent ? 'sent-amount' : 'received-amount';
                const sign = isSent ? '-' : '+';
                
                // Get display name using contacts map
                let counterpartyPhone = isSent ? t.receiver_phone : t.sender_phone;
                let counterpartyName = isSent ? t.receiver_name : t.sender_name;
                let displayName = '';
                
                if (counterpartyPhone && contactsMap.has(counterpartyPhone)) {
                    const contact = contactsMap.get(counterpartyPhone);
                    displayName = contact.name;
                } else if (counterpartyName && counterpartyName !== 'External User' && counterpartyName !== 'null') {
                    displayName = counterpartyName;
                } else if (counterpartyPhone) {
                    displayName = formatPhoneNumber(counterpartyPhone);
                } else {
                    displayName = isSent ? 'Sent to User' : 'Received from User';
                }
                
                html += `
                    <div class="transaction-history-card ${cardClass}" onclick="viewReceipt('${t.id}')">
                        <div class="transaction-icon"><i class="fas ${iconClass}"></i></div>
                        <div class="transaction-details">
                            <div class="transaction-name">${escapeHtml(displayName)}</div>
                            <div class="transaction-date">${new Date(t.created_at).toLocaleString()}</div>
                            <div class="transaction-id">ID: ${t.id}</div>
                        </div>
                        <div class="transaction-amount ${amountClass}">
                            ${sign} ${formatCurrency(t.amount)}
                        </div>
                    </div>
                `;
            });
            html += '</div>';
        }
        
        container.innerHTML = html;
    } catch (error) {
        console.error('Load all transactions error:', error);
        const container = document.getElementById('allTransactionsList');
        if (container) {
            container.innerHTML = '<div class="error-message">Error loading transactions. Please try again.</div>';
        }
    }
}

// ====================
// ANALYTICS PAGE FUNCTIONS
// ====================

let spendingChartInstance = null;

async function loadAnalyticsPage() {
    try {
        const spendingChartCanvas = document.getElementById('spendingChart');
        if (!spendingChartCanvas) {
            console.log('Not on analytics page, skipping chart initialization');
            return;
        }
        
        const user = await apiCall('/api/user');
        const totalSentEl = document.getElementById('totalSent');
        const totalReceivedEl = document.getElementById('totalReceived');
        const cashbackEarnedEl = document.getElementById('cashbackEarned');
        
        if (cashbackEarnedEl) cashbackEarnedEl.textContent = formatCurrency(user.cashback_earned || 0);
        
        const spendingData = await apiCall('/api/analytics/monthly_spending');
        
        let totalSent = 0;
        let totalReceived = 0;
        
        if (spendingData.amounts) {
            totalSent = spendingData.amounts.reduce((sum, val) => sum + (val || 0), 0);
        }
        if (spendingData.received_amounts) {
            totalReceived = spendingData.received_amounts.reduce((sum, val) => sum + (val || 0), 0);
        }
        
        if (totalSentEl) totalSentEl.textContent = formatCurrency(totalSent);
        if (totalReceivedEl) totalReceivedEl.textContent = formatCurrency(totalReceived);
        
        if (spendingChartInstance) {
            spendingChartInstance.destroy();
            spendingChartInstance = null;
        }
        
        if (spendingChartCanvas.chart) {
            spendingChartCanvas.chart.destroy();
        }
        
        const ctx = spendingChartCanvas.getContext('2d');
        ctx.clearRect(0, 0, spendingChartCanvas.width, spendingChartCanvas.height);
        
        if (typeof Chart === 'undefined') {
            console.error('Chart.js is not loaded');
            const chartContainer = document.getElementById('spendingChartContainer');
            if (chartContainer) {
                chartContainer.innerHTML = '<div class="error-message">Chart library not loaded. Please refresh the page.</div>';
            }
            return;
        }
        
        spendingChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: spendingData.months || [],
                datasets: [
                    {
                        label: 'Amount Sent (₹)',
                        data: spendingData.amounts || [],
                        backgroundColor: 'rgba(220, 53, 69, 0.7)',
                        borderColor: '#dc3545',
                        borderWidth: 1,
                        borderRadius: 6
                    },
                    {
                        label: 'Amount Received (₹)',
                        data: spendingData.received_amounts || [],
                        backgroundColor: 'rgba(40, 167, 69, 0.7)',
                        borderColor: '#28a745',
                        borderWidth: 1,
                        borderRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { color: '#ffffff', font: { size: 12 } }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) { return `₹${context.raw.toFixed(2)}`; }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { color: '#888888', callback: function(value) { return '₹' + value; } },
                        grid: { color: '#222222' }
                    },
                    x: {
                        ticks: { color: '#888888' },
                        grid: { color: '#222222' }
                    }
                }
            }
        });
        
        spendingChartCanvas.chart = spendingChartInstance;
        
        const cashbacks = await apiCall('/api/cashback_history');
        const cashbackList = document.getElementById('cashbackList');
        
        if (cashbackList) {
            if (!cashbacks || cashbacks.length === 0) {
                cashbackList.innerHTML = '<div class="no-data"><i class="fas fa-gift"></i><p>No cashback earned yet</p><p class="hint">Send money to earn cashback!</p></div>';
            } else {
                cashbackList.innerHTML = cashbacks.map(cb => `
                    <div class="cashback-item">
                        <div class="cashback-info">
                            <span class="cashback-amount">+ ${formatCurrency(cb.amount)}</span>
                            <span class="cashback-percentage">${(cb.percentage || 0).toFixed(1)}% cashback</span>
                            <span class="cashback-txn">TXN: ${cb.transaction_id || 'N/A'}</span>
                        </div>
                        <div class="cashback-date">${new Date(cb.created_at).toLocaleDateString()}</div>
                    </div>
                `).join('');
            }
        }
    } catch (error) {
        console.error('Load analytics error:', error);
        const cashbackList = document.getElementById('cashbackList');
        if (cashbackList && cashbackList.innerHTML === '<div class="loading">Loading cashback history...</div>') {
            cashbackList.innerHTML = '<div class="no-data"><i class="fas fa-exclamation-triangle"></i><p>Unable to load analytics data</p><p class="hint">Please refresh the page</p></div>';
        }
    }
}

function cleanupAnalyticsChart() {
    if (spendingChartInstance) {
        spendingChartInstance.destroy();
        spendingChartInstance = null;
    }
}

// ====================
// SEND PAGE FUNCTIONS
// ====================

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

async function checkRecipient() {
    const identifier = document.getElementById('recipientIdentifier');
    if (!identifier) return;
    
    const identifierValue = identifier.value;
    const checkDiv = document.getElementById('recipientCheck');
    const sendBtn = document.getElementById('sendBtn');
    const transactionInfo = document.getElementById('transactionInfo');
    
    if (!identifierValue.trim()) {
        if (checkDiv) checkDiv.innerHTML = '';
        if (sendBtn) sendBtn.disabled = true;
        if (transactionInfo) transactionInfo.style.display = 'none';
        return;
    }
    
    if (checkDiv) checkDiv.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking...';
    
    try {
        const response = await fetch('/api/find_user', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier: identifierValue })
        });
        
        const data = await response.json();
        
        if (data.exists) {
            if (checkDiv) {
                checkDiv.innerHTML = '<i class="fas fa-check-circle"></i> User found!';
                checkDiv.className = 'recipient-check success';
            }
            if (sendBtn) sendBtn.disabled = false;
            
            const recipientName = document.getElementById('recipientName');
            const recipientUPI = document.getElementById('recipientUPI');
            if (recipientName) recipientName.textContent = data.name;
            if (recipientUPI) recipientUPI.textContent = data.upi_id;
            if (transactionInfo) transactionInfo.style.display = 'block';
        } else {
            if (checkDiv) {
                checkDiv.innerHTML = '<i class="fas fa-times-circle"></i> User not found. Please check the identifier.';
                checkDiv.className = 'recipient-check error';
            }
            if (sendBtn) sendBtn.disabled = true;
            if (transactionInfo) transactionInfo.style.display = 'none';
        }
    } catch (error) {
        if (checkDiv) {
            checkDiv.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error checking user';
            checkDiv.className = 'recipient-check error';
        }
        if (sendBtn) sendBtn.disabled = true;
    }
}

// ====================
// INITIALIZATION
// ====================

document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;
    console.log('Current path:', path);
    
    if (path === '/' || path === '/login') {
        console.log('On login page, initializing referral validation');
        initReferralValidation();
        
        window.onclick = function(event) {
            const modal = document.getElementById('referralModal');
            if (modal && event.target === modal) {
                skipReferral();
            }
        };
        
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                const modal = document.getElementById('referralModal');
                if (modal && modal.style.display === 'block') {
                    skipReferral();
                }
            }
        });
        
        return;
    }
    
    const verifyAuth = async () => {
        try {
            const response = await fetch('/api/user');
            
            if (response.status === 401) {
                console.log('User not authenticated, redirecting to login');
                sessionStorage.setItem('redirectAfterLogin', path);
                window.location.href = '/';
                return false;
            }
            
            const user = await response.json();
            window.currentUserId = user.id;
            return true;
            
        } catch (error) {
            console.error('Auth verification error:', error);
            window.location.href = '/';
            return false;
        }
    };
    
    verifyAuth().then(isAuthenticated => {
        if (!isAuthenticated) return;
        
        if (path === '/dashboard') {
            loadDashboard();
            
            const sendForm = document.getElementById('sendMoneyForm');
            if (sendForm) sendForm.addEventListener('submit', sendMoney);
            
            const requestForm = document.getElementById('requestMoneyForm');
            if (requestForm) requestForm.addEventListener('submit', requestMoney);
            
            window.onclick = function(event) {
                const addModal = document.getElementById('addContactModal');
                if (addModal && event.target === addModal) {
                    closeAddContactModal();
                }
                const editModal = document.getElementById('editContactModal');
                if (editModal && event.target === editModal) {
                    closeEditContactModal();
                }
            };
        }
        else if (path === '/profile') {
            loadProfile();
        }
        else if (path === '/settings') {
            loadSettings();
        }
        else if (path.includes('/receipt')) {
            loadReceipt();
        }
        else if (path.includes('/transaction-history')) {
            if (typeof initTransactionHistoryPage === 'function') {
                initTransactionHistoryPage();
            }
        }
        else if (path === '/contacts-page') {
            loadAllContacts();
            
            window.onclick = function(event) {
                const addModal = document.getElementById('addContactModal');
                if (addModal && event.target === addModal) {
                    closeAddContactModal();
                }
                const editModal = document.getElementById('editContactModal');
                if (editModal && event.target === editModal) {
                    closeEditContactModal();
                }
            };
        }
        else if (path === '/setup-pin') {
            const pinTypeBtns = document.querySelectorAll('.pin-type-btn');
            if (pinTypeBtns.length > 0) {
                pinTypeBtns.forEach(btn => {
                    btn.addEventListener('click', () => {
                        pinTypeBtns.forEach(b => b.classList.remove('active'));
                        btn.classList.add('active');
                        selectedPinType = btn.dataset.type;
                        currentPin = '';
                        updatePinDisplay();
                        const confirmBtn = document.getElementById('confirmPinBtn');
                        if (confirmBtn) confirmBtn.disabled = true;
                    });
                });
            }
            
            generateKeypad();
            updatePinDisplay();
        }
        else if (path === '/verify-pin') {
            const pinInputs = document.querySelectorAll('.pin-input');
            if (pinInputs.length > 0) {
                pinInputs.forEach((input, index) => {
                    input.addEventListener('input', function() {
                        if (this.value.length === this.maxLength) {
                            const nextInput = pinInputs[index + 1];
                            if (nextInput) {
                                nextInput.focus();
                            } else {
                                verifyPinAndCompleteTransaction();
                            }
                        }
                    });
                });
            }
        }
        else if (path === '/add-balance') {
            generateAddBalanceKeypad();
            updateAddBalancePinDisplay();
            
            const presetBtns = document.querySelectorAll('.preset-btn');
            presetBtns.forEach(btn => {
                btn.addEventListener('click', () => {
                    const amount = btn.getAttribute('data-amount');
                    if (amount) {
                        setPresetAmount(amount);
                    }
                });
            });
        }
        else if (path === '/all-transactions') {
            loadAllTransactionsPage();
        }
        else if (path === '/send') {
            const identifierInput = document.getElementById('recipientIdentifier');
            if (identifierInput) {
                identifierInput.addEventListener('input', debounce(checkRecipient, 500));
            }
            
            const sendForm = document.getElementById('sendMoneyForm');
            if (sendForm) sendForm.addEventListener('submit', sendMoney);
        }
        else if (path === '/analytics') {
            loadAnalyticsPage();
            
            window.addEventListener('beforeunload', cleanupAnalyticsChart);
        }
    });
});