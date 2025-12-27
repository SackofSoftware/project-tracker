/**
 * AI Superintendent Component
 * Chat interface and activity log for the Command Center
 */

class AISuperintendent {
    constructor(containerEl, projectId) {
        this.container = containerEl;
        this.projectId = projectId;
        this.activities = [];
        this.maxActivities = 100;
        this.pipelineStages = {};
        this.isRunning = false;
    }

    /**
     * Initialize the component
     */
    init() {
        this.render();
        this.bindEvents();
    }

    /**
     * Render the component
     */
    render() {
        this.container.innerHTML = `
            <div class="ai-superintendent-header">
                <h3>🤖 AI Superintendent</h3>
            </div>
            <div class="pipeline-stages-container" style="display: none;">
                ${this.renderPipelineStages()}
            </div>
            <div class="activity-log" id="activityLog">
                <div class="activity-placeholder">
                    Waiting for activity...
                </div>
            </div>
            <div class="chat-input-container">
                <div class="chat-input-wrapper">
                    <textarea
                        class="chat-input"
                        id="chatInput"
                        placeholder="Ask about scope or give commands..."
                        rows="1"
                    ></textarea>
                    <button class="chat-send-btn" id="chatSendBtn">Send</button>
                </div>
            </div>
        `;

        this.activityLog = this.container.querySelector('#activityLog');
        this.chatInput = this.container.querySelector('#chatInput');
        this.sendBtn = this.container.querySelector('#chatSendBtn');
        this.pipelineContainer = this.container.querySelector('.pipeline-stages-container');
    }

    /**
     * Render pipeline stage indicators
     */
    renderPipelineStages() {
        const stages = [
            { id: 'rename', icon: '📝', name: 'Rename' },
            { id: 'organize', icon: '📁', name: 'Organize' },
            { id: 'split_specs', icon: '📋', name: 'Split Specs' },
            { id: 'split_drawings', icon: '📐', name: 'Split Dwgs' },
            { id: 'ai_analysis', icon: '🤖', name: 'AI Analysis' },
            { id: 'schedule_parse', icon: '📊', name: 'Parse' },
            { id: 'highlight', icon: '🖍️', name: 'Highlight' },
            { id: 'quotes', icon: '💰', name: 'Quotes' }
        ];

        return `
            <div class="pipeline-stages">
                ${stages.map(s => `
                    <div class="pipeline-stage pending" data-stage="${s.id}">
                        <span class="pipeline-stage-icon">${s.icon}</span>
                        <span class="pipeline-stage-name">${s.name}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    /**
     * Bind event handlers
     */
    bindEvents() {
        // Chat send button
        this.sendBtn.addEventListener('click', () => this.sendChat());

        // Chat input enter key
        this.chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendChat();
            }
        });

        // Auto-resize textarea
        this.chatInput.addEventListener('input', () => {
            this.chatInput.style.height = 'auto';
            this.chatInput.style.height = Math.min(this.chatInput.scrollHeight, 120) + 'px';
        });
    }

    /**
     * Send chat message
     */
    async sendChat() {
        const message = this.chatInput.value.trim();
        if (!message) return;

        // Add user message to activity
        this.addActivity({
            type: 'chat_user',
            icon: '👤',
            message: message,
            detail: ''
        });

        // Clear input
        this.chatInput.value = '';
        this.chatInput.style.height = 'auto';
        this.sendBtn.disabled = true;

        try {
            const response = await fetch(`/api/project/${this.projectId}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });

            if (!response.ok) throw new Error('Chat request failed');

            const data = await response.json();
            this.handleChatResponse(data);
        } catch (error) {
            console.error('Chat error:', error);
            this.addActivity({
                type: 'error',
                icon: '❌',
                message: 'Failed to process message',
                detail: error.message
            });
        } finally {
            this.sendBtn.disabled = false;
        }
    }

    /**
     * Handle chat response from server
     */
    handleChatResponse(data) {
        if (data.type === 'tool_call') {
            this.addActivity({
                type: 'tool_call',
                icon: '⚡',
                message: `Executing: ${data.tool}`,
                detail: data.status
            });
        } else if (data.type === 'text') {
            this.addActivity({
                type: 'chat_response',
                icon: '🤖',
                message: data.content,
                detail: ''
            });
        } else if (data.type === 'error') {
            this.addActivity({
                type: 'error',
                icon: '❌',
                message: data.content,
                detail: ''
            });
        }
    }

    /**
     * Add activity entry to log
     */
    addActivity(activity) {
        // Remove placeholder if present
        const placeholder = this.activityLog.querySelector('.activity-placeholder');
        if (placeholder) placeholder.remove();

        // Create activity element
        const entry = document.createElement('div');
        entry.className = 'activity-entry';
        entry.innerHTML = `
            <span class="activity-icon">${activity.icon}</span>
            <div class="activity-content">
                <div class="activity-message">${activity.message}</div>
                ${activity.detail ? `<div class="activity-detail">${activity.detail}</div>` : ''}
                ${activity.progress !== undefined && activity.progress !== null ? `
                    <div class="activity-progress">
                        <div class="activity-progress-bar" style="width: ${activity.progress * 100}%"></div>
                    </div>
                ` : ''}
            </div>
            <span class="activity-time">${this.formatTime(new Date())}</span>
        `;

        // Add to log (at top)
        this.activityLog.insertBefore(entry, this.activityLog.firstChild);

        // Track activities
        this.activities.unshift(activity);
        if (this.activities.length > this.maxActivities) {
            this.activities.pop();
            // Remove oldest from DOM
            const entries = this.activityLog.querySelectorAll('.activity-entry');
            if (entries.length > this.maxActivities) {
                entries[entries.length - 1].remove();
            }
        }
    }

    /**
     * Handle pipeline stage update from SSE
     */
    handlePipelineStage(data) {
        // Show pipeline stages if running
        if (data.status === 'running' && !this.isRunning) {
            this.isRunning = true;
            this.pipelineContainer.style.display = 'block';
            this.resetPipelineStages();
        }

        // Update stage indicator
        const stageEl = this.container.querySelector(`[data-stage="${data.stage}"]`);
        if (stageEl) {
            stageEl.className = `pipeline-stage ${data.status}`;
        }

        // Add activity
        const icons = {
            'running': '🔄',
            'complete': '✅',
            'error': '❌',
            'pending': '⏳'
        };

        this.addActivity({
            type: 'pipeline',
            icon: icons[data.status] || '📋',
            message: data.message || `Stage: ${data.stage}`,
            detail: '',
            progress: data.progress
        });

        // Check if pipeline complete
        if (data.status === 'complete' && data.stage === 'quotes') {
            this.isRunning = false;
            setTimeout(() => {
                this.pipelineContainer.style.display = 'none';
            }, 3000);
        }
    }

    /**
     * Reset all pipeline stages to pending
     */
    resetPipelineStages() {
        this.container.querySelectorAll('.pipeline-stage').forEach(el => {
            el.className = 'pipeline-stage pending';
        });
    }

    /**
     * Handle activity event from SSE
     */
    handleActivity(data) {
        this.addActivity({
            type: data.type,
            icon: this.getActivityIcon(data.type, data.icon),
            message: data.message,
            detail: data.detail || '',
            progress: data.progress
        });
    }

    /**
     * Get icon for activity type
     */
    getActivityIcon(type, providedIcon) {
        if (providedIcon) {
            const iconMap = {
                'folder': '📁',
                'search': '🔍',
                'card': '🃏',
                'check': '✅',
                'error': '❌',
                'info': 'ℹ️'
            };
            return iconMap[providedIcon] || providedIcon;
        }

        const typeIcons = {
            'file_scan': '📁',
            'rag_query': '🔍',
            'card_update': '🃏',
            'stage_complete': '✅',
            'error': '❌'
        };
        return typeIcons[type] || 'ℹ️';
    }

    /**
     * Format timestamp
     */
    formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    /**
     * Clear activity log
     */
    clearActivities() {
        this.activities = [];
        this.activityLog.innerHTML = `
            <div class="activity-placeholder">
                Waiting for activity...
            </div>
        `;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AISuperintendent;
}
