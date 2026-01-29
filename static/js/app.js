/**
 * Edibes Leltár - JavaScript funkciók
 */

// DOMContentLoaded esemény
document.addEventListener('DOMContentLoaded', function() {
    // Idő megjelenítése a láblécben
    updateTime();
    setInterval(updateTime, 1000);
    
    // Tooltipek inicializálása
    initTooltips();
    
    // Auto-dismiss alertek
    autoDismissAlerts();
});

/**
 * Aktuális idő frissítése
 */
function updateTime() {
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        const now = new Date();
        const options = { 
            year: 'numeric', 
            month: '2-digit', 
            day: '2-digit',
            hour: '2-digit', 
            minute: '2-digit',
            second: '2-digit'
        };
        timeElement.textContent = now.toLocaleString('hu-HU', options);
    }
}

/**
 * Bootstrap tooltipek inicializálása
 */
function initTooltips() {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach(function (tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

/**
 * Alertek automatikus eltüntetése
 * Csak a success típusú alertek tűnnek el automatikusan
 * Az info, warning és danger típusúak megmaradnak
 */
function autoDismissAlerts() {
    const alerts = document.querySelectorAll('.alert.alert-success');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
}

/**
 * Toast üzenet megjelenítése
 * @param {string} type - Az üzenet típusa (success, danger, warning, info)
 * @param {string} message - Az üzenet szövege
 */
function showToast(type, message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 80px; right: 20px; z-index: 9999; min-width: 250px; max-width: 400px;';
    
    let icon = 'info-circle';
    if (type === 'success') icon = 'check-circle';
    if (type === 'danger') icon = 'exclamation-triangle';
    if (type === 'warning') icon = 'exclamation-circle';
    
    alertDiv.innerHTML = `
        <i class="bi bi-${icon} me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // Automatikus eltűnés
    setTimeout(function() {
        alertDiv.remove();
    }, 4000);
}

/**
 * Megerősítő dialógus
 * @param {string} message - A megerősítő üzenet
 * @returns {boolean}
 */
function confirmAction(message) {
    return confirm(message || 'Biztosan folytatja?');
}

/**
 * Szám formázás
 * @param {number} num - A formázandó szám
 * @param {number} decimals - Tizedesjegyek száma
 * @returns {string}
 */
function formatNumber(num, decimals = 0) {
    return new Intl.NumberFormat('hu-HU', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(num);
}

/**
 * AJAX POST kérés
 * @param {string} url - A cél URL
 * @param {object} data - A küldendő adatok
 * @returns {Promise}
 */
async function postData(url, data = {}) {
    const formData = new URLSearchParams();
    for (const key in data) {
        formData.append(key, data[key]);
    }
    
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData
    });
    
    return response.json();
}

/**
 * Vonalkód keresés API
 * @param {string} barcode - A keresett vonalkód
 * @returns {Promise}
 */
async function searchByBarcode(barcode) {
    try {
        const response = await fetch(`/products/api/barcode/${barcode}`);
        return await response.json();
    } catch (error) {
        console.error('Vonalkód keresési hiba:', error);
        return { success: false, message: 'Hiba történt a keresés során' };
    }
}

/**
 * Debounce funkció
 * @param {Function} func - A futtatandó függvény
 * @param {number} wait - Várakozási idő milliszekundumban
 * @returns {Function}
 */
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

/**
 * Keresőmező automatikus szűrés
 */
function initAutoSearch() {
    const searchInput = document.querySelector('input[name="search"]');
    if (searchInput) {
        const debouncedSearch = debounce(function() {
            searchInput.form.submit();
        }, 500);
        
        searchInput.addEventListener('input', debouncedSearch);
    }
}

/**
 * Készlet színezés frissítése
 * @param {number} productId - Termék ID
 * @param {number} newQuantity - Új mennyiség
 * @param {number} minLevel - Minimum szint
 */
function updateStockColor(productId, newQuantity, minLevel) {
    const row = document.getElementById(`row-${productId}`);
    if (row) {
        row.classList.remove('table-warning', 'table-danger');
        if (newQuantity === 0) {
            row.classList.add('table-danger');
        } else if (newQuantity < minLevel) {
            row.classList.add('table-warning');
        }
    }
}

/**
 * Gyors készlet kivételezés
 * @param {number} productId - Termék ID
 * @param {number} quantity - Mennyiség (alapértelmezett: 1)
 */
function quickStockOut(productId, quantity = 1) {
    postData(`/inventory/quick-out/${productId}`, { quantity: quantity })
        .then(data => {
            if (data.success) {
                const qtyEl = document.getElementById(`qty-${productId}`);
                if (qtyEl) qtyEl.textContent = Math.round(data.new_quantity);
                showToast('success', data.message);
            } else {
                showToast('danger', data.message);
            }
        })
        .catch(err => showToast('danger', 'Hiba történt!'));
}

/**
 * Gyors készlet bevételezés
 * @param {number} productId - Termék ID
 * @param {number} quantity - Mennyiség (alapértelmezett: 1)
 */
function quickStockIn(productId, quantity = 1) {
    postData(`/inventory/quick-in/${productId}`, { quantity: quantity })
        .then(data => {
            if (data.success) {
                const qtyEl = document.getElementById(`qty-${productId}`);
                if (qtyEl) qtyEl.textContent = Math.round(data.new_quantity);
                showToast('success', data.message);
            } else {
                showToast('danger', data.message);
            }
        })
        .catch(err => showToast('danger', 'Hiba történt!'));
}

/**
 * Nyomtatás funkció
 */
function printPage() {
    window.print();
}

/**
 * Táblázat exportálás CSV formátumban
 * @param {string} tableId - A táblázat ID-ja
 * @param {string} filename - A fájlnév
 */
function exportTableToCSV(tableId, filename = 'export.csv') {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    let csv = [];
    const rows = table.querySelectorAll('tr');
    
    rows.forEach(function(row) {
        const cols = row.querySelectorAll('td, th');
        let rowData = [];
        cols.forEach(function(col) {
            let text = col.textContent.trim().replace(/"/g, '""');
            rowData.push(`"${text}"`);
        });
        csv.push(rowData.join(';'));
    });
    
    const csvContent = '\ufeff' + csv.join('\n'); // UTF-8 BOM
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
}

// Globális hibakezelés
window.onerror = function(message, source, lineno, colno, error) {
    console.error('JavaScript hiba:', message, 'at', source, lineno);
    return false;
};
