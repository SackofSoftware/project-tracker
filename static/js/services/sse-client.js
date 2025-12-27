/**
 * SSE Client for Command Center
 * Handles Server-Sent Events connection and event dispatching
 */

class CommandCenterSSE {
    constructor(projectId) {
        this.projectId = projectId;
        this.eventSource = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;
        this.handlers = new Map();
        this.connected = false;
    }

    /**
     * Connect to SSE endpoint
     */
    connect() {
        if (this.eventSource) {
            this.disconnect();
        }

        const url = `/api/project/${this.projectId}/events`;
        this.eventSource = new EventSource(url);

        this.eventSource.onopen = () => {
            console.log('[SSE] Connected to', url);
            this.connected = true;
            this.reconnectAttempts = 0;
            this.dispatch('sse:connected', { projectId: this.projectId });
        };

        this.eventSource.onerror = (error) => {
            console.error('[SSE] Connection error:', error);
            this.connected = false;
            this.dispatch('sse:error', { error });
            this.handleReconnect();
        };

        // Register event listeners
        this.registerEventListeners();
    }

    /**
     * Disconnect from SSE
     */
    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
            this.connected = false;
            console.log('[SSE] Disconnected');
        }
    }

    /**
     * Register listeners for SSE event types
     */
    registerEventListeners() {
        const eventTypes = [
            'connected',
            'heartbeat',
            'pipeline_stage',
            'card_update',
            'activity',
            'chat_response'
        ];

        eventTypes.forEach(eventType => {
            this.eventSource.addEventListener(eventType, (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleEvent(eventType, data);
                } catch (e) {
                    console.error(`[SSE] Error parsing ${eventType} event:`, e);
                }
            });
        });
    }

    /**
     * Handle incoming SSE event
     */
    handleEvent(eventType, data) {
        console.log(`[SSE] Event: ${eventType}`, data);

        // Dispatch to registered handlers
        this.dispatch(eventType, data);

        // Also dispatch to specific handlers
        switch (eventType) {
            case 'pipeline_stage':
                this.dispatch('pipeline:stage', data);
                break;
            case 'card_update':
                this.dispatch('cards:update', data);
                break;
            case 'activity':
                this.dispatch('activity:new', data);
                break;
            case 'chat_response':
                this.dispatch('chat:response', data);
                break;
        }
    }

    /**
     * Handle reconnection logic
     */
    handleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[SSE] Max reconnect attempts reached');
            this.dispatch('sse:failed', {
                message: 'Connection failed after multiple attempts'
            });
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * this.reconnectAttempts;

        console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
        this.dispatch('sse:reconnecting', {
            attempt: this.reconnectAttempts,
            delay
        });

        setTimeout(() => {
            if (!this.connected) {
                this.connect();
            }
        }, delay);
    }

    /**
     * Register event handler
     */
    on(eventType, handler) {
        if (!this.handlers.has(eventType)) {
            this.handlers.set(eventType, []);
        }
        this.handlers.get(eventType).push(handler);
        return this; // Enable chaining
    }

    /**
     * Remove event handler
     */
    off(eventType, handler) {
        if (this.handlers.has(eventType)) {
            const handlers = this.handlers.get(eventType);
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
            }
        }
        return this;
    }

    /**
     * Dispatch event to handlers
     */
    dispatch(eventType, data) {
        if (this.handlers.has(eventType)) {
            this.handlers.get(eventType).forEach(handler => {
                try {
                    handler(data);
                } catch (e) {
                    console.error(`[SSE] Handler error for ${eventType}:`, e);
                }
            });
        }

        // Also dispatch to wildcard handlers
        if (this.handlers.has('*')) {
            this.handlers.get('*').forEach(handler => {
                try {
                    handler(eventType, data);
                } catch (e) {
                    console.error('[SSE] Wildcard handler error:', e);
                }
            });
        }
    }

    /**
     * Check if connected
     */
    isConnected() {
        return this.connected && this.eventSource?.readyState === EventSource.OPEN;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CommandCenterSSE;
}
