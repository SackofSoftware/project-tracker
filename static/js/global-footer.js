/**
 * Global Footer Controller
 *
 * Manages the persistent job status footer, connecting to SSE
 * for real-time updates and displaying job progress.
 */

class GlobalFooterController {
    constructor() {
        this.eventSource = null;
        this.logs = [];
        this.maxLogs = 100;
        this.isExpanded = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 2000;
    }

    /**
     * Initialize the footer controller.
     * Called on DOMContentLoaded.
     */
    init() {
        // Add body class for padding
        document.body.classList.add('has-global-footer');

        // Get initial status
        this.fetchInitialStatus();

        // Connect to SSE stream
        this.connectSSE();

        console.log('[GlobalFooter] Initialized');
    }

    /**
     * Fetch initial job status from API.
     */
    async fetchInitialStatus() {
        try {
            const response = await fetch('/api/jobs/status');
            if (response.ok) {
                const data = await response.json();
                this.updateFooter(data);
            }
        } catch (error) {
            console.warn('[GlobalFooter] Failed to fetch initial status:', error);
        }
    }

    /**
     * Connect to the SSE endpoint for real-time updates.
     */
    connectSSE() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        try {
            this.eventSource = new EventSource('/api/jobs/stream');

            this.eventSource.addEventListener('connected', (e) => {
                console.log('[GlobalFooter] SSE connected');
                this.reconnectAttempts = 0;
                try {
                    const data = JSON.parse(e.data);
                    this.updateFooter(data);
                } catch (err) {}
            });

            this.eventSource.addEventListener('job_update', (e) => {
                try {
                    const data = JSON.parse(e.data);
                    this.updateFooter(data);

                    // If there's a job update, also check for log messages
                    if (data.job && data.job.message) {
                        this.appendLog(data.job.message, 'info');
                    }
                } catch (err) {
                    console.error('[GlobalFooter] Error parsing job_update:', err);
                }
            });

            this.eventSource.addEventListener('job_log', (e) => {
                try {
                    const data = JSON.parse(e.data);
                    this.appendLog(data.message, data.level || 'info');
                } catch (err) {}
            });

            this.eventSource.addEventListener('heartbeat', (e) => {
                // Heartbeat received, connection is alive
            });

            this.eventSource.onerror = (e) => {
                console.warn('[GlobalFooter] SSE error, reconnecting...');
                this.eventSource.close();
                this.scheduleReconnect();
            };

        } catch (error) {
            console.error('[GlobalFooter] Failed to create EventSource:', error);
            this.scheduleReconnect();
        }
    }

    /**
     * Schedule a reconnection attempt.
     */
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[GlobalFooter] Max reconnect attempts reached');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.min(this.reconnectAttempts, 5);

        setTimeout(() => {
            console.log(`[GlobalFooter] Reconnect attempt ${this.reconnectAttempts}`);
            this.connectSSE();
        }, delay);
    }

    /**
     * Update the footer UI with new status data.
     */
    updateFooter(data) {
        const indicator = document.getElementById('footerIndicator');
        const task = document.getElementById('footerTask');
        const project = document.getElementById('footerProject');
        const progress = document.getElementById('footerProgress');
        const progressFill = document.getElementById('footerProgressFill');
        const progressText = document.getElementById('footerProgressText');
        const message = document.getElementById('footerMessage');
        const queueCount = document.getElementById('footerQueueCount');

        if (!indicator) return; // Footer not in DOM

        const activeJob = data.active_job;

        if (activeJob) {
            // Running state
            indicator.className = 'status-indicator running';
            task.textContent = this.formatTaskName(activeJob.task);
            project.textContent = activeJob.project_id || '';

            // Show progress
            progress.style.display = 'flex';
            const pct = Math.round((activeJob.progress || 0) * 100);
            progressFill.style.width = `${pct}%`;
            progressText.textContent = `${pct}%`;

            // Show message
            message.textContent = activeJob.message || activeJob.current_phase || '';

        } else {
            // Idle state
            indicator.className = 'status-indicator idle';
            task.textContent = 'No active jobs';
            project.textContent = '';
            progress.style.display = 'none';
            message.textContent = '';
        }

        // Update queue count
        queueCount.textContent = data.queue_depth || 0;
    }

    /**
     * Format task type to human-readable name.
     */
    formatTaskName(task) {
        const names = {
            'planhub_sync': 'PlanHub Sync',
            'projectdog_sync': 'ProjectDog Sync',
            'spec_decomposition': 'Spec Analysis',
            'drawing_analysis': 'Drawing Analysis',
            'ai_enrichment': 'AI Enrichment'
        };
        return names[task] || task;
    }

    /**
     * Append a log entry to the activity log.
     */
    appendLog(message, level = 'info') {
        if (!message) return;

        // Add to logs array
        const timestamp = new Date().toLocaleTimeString();
        this.logs.unshift({ time: timestamp, message, level });

        // Trim if too many
        if (this.logs.length > this.maxLogs) {
            this.logs.pop();
        }

        // Update UI
        this.renderLogs();
    }

    /**
     * Render log entries in the details panel.
     */
    renderLogs() {
        const logsContainer = document.getElementById('footerLogs');
        if (!logsContainer) return;

        logsContainer.innerHTML = this.logs.map(log => `
            <div class="log-entry ${log.level}">
                <span class="log-time">${log.time}</span>
                <span class="log-message">${this.escapeHtml(log.message)}</span>
            </div>
        `).join('');
    }

    /**
     * Clear all log entries.
     */
    clearLogs() {
        this.logs = [];
        this.renderLogs();
    }

    /**
     * Toggle expanded state of the footer.
     */
    toggleExpanded() {
        const footer = document.getElementById('globalStatusFooter');
        if (!footer) return;

        this.isExpanded = !this.isExpanded;
        footer.classList.toggle('expanded', this.isExpanded);
    }

    /**
     * Escape HTML to prevent XSS.
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Manually trigger a PlanHub sync job.
     */
    async triggerPlanHubSync() {
        try {
            const response = await fetch('/api/jobs/sync/planhub', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();

            if (response.ok) {
                this.appendLog(`PlanHub sync started: ${data.job_id}`, 'success');
            } else {
                this.appendLog(`Failed to start sync: ${data.error}`, 'error');
            }
        } catch (error) {
            this.appendLog(`Error triggering sync: ${error.message}`, 'error');
        }
    }

    /**
     * Clean up on page unload.
     */
    destroy() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
}

// Create global instance
window.globalFooter = new GlobalFooterController();

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.globalFooter.init();
});

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (window.globalFooter) {
        window.globalFooter.destroy();
    }
});
