/**
 * Division 8 Analysis Page JavaScript
 * Handles tab switching, analysis refresh, and PDF export
 */

// =============================================================================
// TAB SWITCHING
// =============================================================================

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tabId = btn.dataset.tab;

        // Update active tab button
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Show corresponding panel
        document.querySelectorAll('.tab-panel').forEach(panel => {
            panel.classList.remove('active');
        });
        const targetPanel = document.getElementById(`tab-${tabId}`);
        if (targetPanel) {
            targetPanel.classList.add('active');
        }
    });
});

// =============================================================================
// LOADING OVERLAY
// =============================================================================

function showLoading(message = 'Running analysis...') {
    const overlay = document.getElementById('loadingOverlay');
    const messageEl = document.getElementById('loadingMessage');
    if (overlay) {
        overlay.classList.add('active');
    }
    if (messageEl) {
        messageEl.textContent = message;
    }
}

function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.classList.remove('active');
    }
}

function updateLoadingMessage(message) {
    const messageEl = document.getElementById('loadingMessage');
    if (messageEl) {
        messageEl.textContent = message;
    }
}

// =============================================================================
// REFRESH ANALYSIS
// =============================================================================

async function refreshAnalysis() {
    const statusEl = document.getElementById('analysisStatus');
    const refreshBtn = document.getElementById('refreshBtn');

    // Disable button during refresh
    if (refreshBtn) {
        refreshBtn.disabled = true;
    }

    // Show loading overlay
    showLoading('Starting analysis...');

    // Update status
    if (statusEl) {
        statusEl.innerHTML = '<div class="status-badge running">Running analysis... This may take 1-2 minutes.</div>';
    }

    try {
        updateLoadingMessage('Indexing documents...');

        const response = await fetch(`/api/project/${projectId}/analysis/run`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok && data.status === 'ok') {
            updateLoadingMessage('Analysis complete! Reloading...');
            // Success - reload page to show new results
            setTimeout(() => {
                window.location.reload();
            }, 500);
        } else {
            // Error
            hideLoading();
            const errorMsg = data.error || data.message || 'Unknown error';
            if (statusEl) {
                statusEl.innerHTML = `<div class="status-badge error">Error: ${errorMsg}</div>`;
            }
            alert(`Analysis failed: ${errorMsg}`);
        }
    } catch (error) {
        hideLoading();
        console.error('Analysis error:', error);
        if (statusEl) {
            statusEl.innerHTML = `<div class="status-badge error">Error: ${error.message}</div>`;
        }
        alert(`Analysis failed: ${error.message}`);
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
        }
    }
}

// =============================================================================
// EXPORT PDF
// =============================================================================

function exportPDF() {
    // Open PDF download in new tab
    window.open(`/api/project/${projectId}/analysis/export/pdf`, '_blank');
}

// =============================================================================
// COPY JSON
// =============================================================================

function copyJSON() {
    const jsonContent = document.getElementById('jsonContent');
    if (!jsonContent) return;

    const text = jsonContent.textContent;

    // Try modern clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            showCopyFeedback();
        }).catch(err => {
            console.error('Clipboard write failed:', err);
            fallbackCopy(text);
        });
    } else {
        fallbackCopy(text);
    }
}

function fallbackCopy(text) {
    // Fallback for older browsers
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
        document.execCommand('copy');
        showCopyFeedback();
    } catch (err) {
        console.error('Fallback copy failed:', err);
        alert('Failed to copy to clipboard');
    }
    document.body.removeChild(textarea);
}

function showCopyFeedback() {
    const copyBtn = document.querySelector('.copy-btn');
    if (copyBtn) {
        const originalText = copyBtn.textContent;
        copyBtn.textContent = 'Copied!';
        copyBtn.style.background = 'var(--accent-green, #22c55e)';
        setTimeout(() => {
            copyBtn.textContent = originalText;
            copyBtn.style.background = '';
        }, 1500);
    }
}

// =============================================================================
// KEYBOARD SHORTCUTS
// =============================================================================

document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + R = Refresh analysis
    if ((e.ctrlKey || e.metaKey) && e.key === 'r' && e.shiftKey) {
        e.preventDefault();
        refreshAnalysis();
    }

    // Ctrl/Cmd + E = Export PDF
    if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
        e.preventDefault();
        exportPDF();
    }

    // Number keys 1-7 = Switch tabs
    if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        const tabIndex = parseInt(e.key) - 1;
        if (tabIndex >= 0 && tabIndex <= 6) {
            const tabs = document.querySelectorAll('.tab-btn');
            if (tabs[tabIndex]) {
                tabs[tabIndex].click();
            }
        }
    }
});

// =============================================================================
// INIT
// =============================================================================

console.log('[Analysis] Page loaded for project:', projectId);
