/**
 * Unified Scope Manager
 *
 * Manages the 4-tab unified scope section in the Command Center:
 * - Tab 1: Overview (Scope Cards)
 * - Tab 2: Analysis Tools
 * - Tab 3: RAG Results
 * - Tab 4: Takeoff Workflow
 */

class UnifiedScopeManager {
    constructor(containerId, projectId, scopeCards) {
        this.container = document.getElementById(containerId);
        this.projectId = projectId;
        this.scopeCards = scopeCards || [];
        this.currentTab = 'overview';
        this.ragResults = null;
        this.takeoffData = null;

        this.init();
    }

    init() {
        if (!this.container) {
            console.error('Unified scope container not found');
            return;
        }

        this.render();
        this.loadRAGResults();
        this.loadTakeoffData();
    }

    render() {
        this.container.innerHTML = `
            <div class="unified-scope-card">
                <div class="unified-scope-header">
                    <h2>Division 8 Scope</h2>
                    <span class="unified-scope-subtitle">Multi-Source Analysis</span>
                </div>

                <div class="unified-scope-tabs">
                    <button class="unified-scope-tab ${this.currentTab === 'overview' ? 'active' : ''}"
                            data-tab="overview" onclick="unifiedScope.switchTab('overview')">
                        Overview
                    </button>
                    <button class="unified-scope-tab ${this.currentTab === 'analysis' ? 'active' : ''}"
                            data-tab="analysis" onclick="unifiedScope.switchTab('analysis')">
                        Analysis Tools
                    </button>
                    <button class="unified-scope-tab ${this.currentTab === 'rag' ? 'active' : ''}"
                            data-tab="rag" onclick="unifiedScope.switchTab('rag')">
                        RAG Results
                    </button>
                    <button class="unified-scope-tab ${this.currentTab === 'takeoff' ? 'active' : ''}"
                            data-tab="takeoff" onclick="unifiedScope.switchTab('takeoff')">
                        Takeoff Workflow
                    </button>
                </div>

                <div class="unified-scope-content">
                    ${this.renderTabContent()}
                </div>
            </div>
        `;
    }

    renderTabContent() {
        switch(this.currentTab) {
            case 'overview':
                return this.renderOverview();
            case 'analysis':
                return this.renderAnalysisTools();
            case 'rag':
                return this.renderRAGResults();
            case 'takeoff':
                return this.renderTakeoffWorkflow();
            default:
                return '<div class="tab-content">Invalid tab</div>';
        }
    }

    renderOverview() {
        // Only show cards that have actual analysis data
        // Filter out: wood-doors (always), and any card without real data
        const cardsWithData = (this.scopeCards || []).filter(card => {
            // Never show wood doors
            if (card.id === 'wood-doors') return false;

            // Only show if card has actual analysis results
            const hasData = (
                (card.status && card.status !== 'pending' && card.status !== 'unknown') ||
                (card.spec_sections && card.spec_sections.length > 0) ||
                (card.count !== undefined && card.count !== null) ||
                card.type ||
                card.quotes > 0 ||
                (card.sources && card.sources.length > 0)
            );

            return hasData;
        });

        // No cards with data = show empty state
        if (cardsWithData.length === 0) {
            return `
                <div class="tab-content" id="overviewTab">
                    <div class="empty-state" style="text-align: center; padding: 3rem;">
                        <div style="font-size: 3rem; margin-bottom: 1rem;">📋</div>
                        <h3 style="margin-bottom: 0.5rem;">No Analysis Yet</h3>
                        <p style="color: var(--text-muted); margin-bottom: 1.5rem;">
                            Run analysis to extract Division 8 scope from project documents.
                        </p>
                        <button class="analysis-btn primary" onclick="unifiedScope.switchTab('analysis')" style="padding: 0.75rem 1.5rem;">
                            Go to Analysis Tools
                        </button>
                    </div>
                </div>
            `;
        }

        const cardsHTML = cardsWithData.map(card => this.renderScopeCard(card)).join('');

        return `
            <div class="tab-content" id="overviewTab">
                <div class="scope-cards-grid">
                    ${cardsHTML}
                </div>
            </div>
        `;
    }

    renderScopeCard(card) {
        const statusClass = card.status || 'pending';
        const statusText = this.getStatusText(statusClass);

        return `
            <div class="agg-scope-card" data-card-id="${card.id}" data-status="${statusClass}">
                <div class="agg-scope-header ${card.id}">
                    <span class="agg-scope-icon">${card.icon || '📋'}</span>
                    <span class="agg-scope-title">${card.title}</span>
                    <span class="agg-scope-status ${statusClass}">${statusText}</span>
                </div>

                <div class="agg-scope-body">
                    ${this.renderCardFields(card)}
                </div>

                <div class="agg-scope-footer">
                    <span class="spec-refs">${this.getSpecRefs(card)}</span>
                    ${card.has_docs ? `<button class="view-docs-btn" onclick="unifiedScope.viewDocs('${card.id}')">View Docs</button>` : ''}
                </div>
            </div>
        `;
    }

    renderCardFields(card) {
        let fieldsHTML = '';

        // Count field
        if (card.count !== undefined && card.count !== null) {
            fieldsHTML += `
                <div class="scope-field">
                    <label>Count</label>
                    <span class="value ${card.count === 0 ? 'empty' : ''}">${card.count || 'N/A'}</span>
                </div>
            `;
        }

        // Type field
        if (card.type) {
            fieldsHTML += `
                <div class="scope-field">
                    <label>Type</label>
                    <span class="value">${card.type}</span>
                </div>
            `;
        }

        // Quotes field
        if (card.quotes !== undefined) {
            fieldsHTML += `
                <div class="scope-field">
                    <label>Quotes</label>
                    <span class="value ${card.quotes === 0 ? 'empty' : ''}">${card.quotes} vendors</span>
                </div>
            `;
        }

        // Confidence field - only show if valid number
        if (card.confidence !== undefined && card.confidence !== null && !isNaN(card.confidence) && card.confidence > 0) {
            const confidencePercent = Math.round(card.confidence * 100);
            fieldsHTML += `
                <div class="scope-field">
                    <label>Confidence</label>
                    <span class="value">${confidencePercent}%</span>
                </div>
            `;
        }

        // Sources field
        if (card.sources && card.sources.length > 0) {
            fieldsHTML += `
                <div class="scope-field">
                    <label>Sources</label>
                    <div class="source-badges">
                        ${card.sources.map(s => `<span class="source-badge">${s}</span>`).join('')}
                    </div>
                </div>
            `;
        }

        // Conflicts field
        if (card.conflicts && card.conflicts.length > 0) {
            fieldsHTML += `
                <div class="scope-field conflict">
                    <label>Conflicts</label>
                    <span class="value conflict-text">${card.conflicts.join(', ')}</span>
                </div>
            `;
        }

        return fieldsHTML || '<div class="scope-field empty"><span>No data available</span></div>';
    }

    getStatusText(status) {
        const statusMap = {
            'specified': 'Specified',
            'not-specified': 'Not Specified',
            'by-others': 'By Others',
            'pending': 'Pending',
            'complete': 'Complete',
            'conflict': 'Conflict'
        };
        return statusMap[status] || 'Unknown';
    }

    getSpecRefs(card) {
        if (card.spec_sections && card.spec_sections.length > 0) {
            return card.spec_sections.join(', ');
        }
        return '';
    }

    renderAnalysisTools() {
        return `
            <div class="tab-content" id="analysisTab">
                <div class="analysis-actions">
                    <button class="analysis-btn primary" onclick="unifiedScope.runAnalysis()">
                        <span class="btn-icon">🔍</span>
                        Run Analysis
                    </button>
                    <button class="analysis-btn" onclick="unifiedScope.scanDocuments()">
                        <span class="btn-icon">📄</span>
                        Scan Documents
                    </button>
                    <button class="analysis-btn" onclick="unifiedScope.extractCSI()">
                        <span class="btn-icon">📊</span>
                        Extract CSI Tags
                    </button>
                </div>

                <div id="csiTagsContainer" class="csi-tags-section">
                    <h3>CSI Scope Tags</h3>
                    <div class="csi-tags-grid" id="csiTagsGrid">
                        <p class="empty-state">Run analysis to see CSI tags</p>
                    </div>
                </div>

                <div id="scanProgressContainer" class="scan-progress-section" style="display: none;">
                    <h3>Scan Progress</h3>
                    <div class="progress-bar">
                        <div class="progress-fill" id="scanProgressBar" style="width: 0%"></div>
                    </div>
                    <div class="progress-details" id="scanProgressDetails"></div>
                </div>

                <div id="csiResultsContainer" class="csi-results-section">
                    <h3>CSI Masterformat Results</h3>
                    <div id="csiResultsGrid" class="csi-results-grid">
                        <p class="empty-state">No results yet</p>
                    </div>
                </div>
            </div>
        `;
    }

    renderRAGResults() {
        if (!this.ragResults) {
            return `
                <div class="tab-content" id="ragTab">
                    <div class="loading-state">
                        <div class="loading-spinner"></div>
                        <p>Loading AI-generated scope summary...</p>
                    </div>
                </div>
            `;
        }

        return `
            <div class="tab-content" id="ragTab">
                <div class="rag-summary">
                    <h3>AI-Generated Scope Summary</h3>
                    <div class="rag-content">
                        ${this.ragResults.summary || '<p>No summary available</p>'}
                    </div>
                </div>

                <div class="rag-categories">
                    ${this.renderRAGCategories()}
                </div>
            </div>
        `;
    }

    renderRAGCategories() {
        if (!this.ragResults || !this.ragResults.categories) {
            return '<p class="empty-state">No category data available</p>';
        }

        return this.ragResults.categories.map(cat => `
            <div class="rag-category-card">
                <div class="rag-category-header">
                    <span class="rag-category-icon">${cat.icon || '📋'}</span>
                    <span class="rag-category-title">${cat.title}</span>
                    <span class="rag-confidence-badge">${Math.round(cat.confidence * 100)}%</span>
                </div>
                <div class="rag-category-body">
                    ${cat.details || '<p>No details available</p>'}
                </div>
            </div>
        `).join('');
    }

    renderTakeoffWorkflow() {
        return `
            <div class="tab-content" id="takeoffTab">
                <div class="takeoff-workflow">
                    <h3>5-Step Takeoff Process</h3>

                    <div class="takeoff-step" data-step="1">
                        <div class="step-header">
                            <span class="step-number">1</span>
                            <span class="step-title">Documents Review</span>
                            <span class="step-status pending">Pending</span>
                        </div>
                        <div class="step-content">
                            <p>Review drawings and specifications for Division 8 scope</p>
                            <button class="step-btn" onclick="unifiedScope.openDocuments()">Open Documents</button>
                        </div>
                    </div>

                    <div class="takeoff-step" data-step="2">
                        <div class="step-header">
                            <span class="step-number">2</span>
                            <span class="step-title">Specifications</span>
                            <span class="step-status pending">Pending</span>
                        </div>
                        <div class="step-content">
                            <p>Extract Division 8 spec sections and requirements</p>
                            <button class="step-btn" onclick="unifiedScope.extractSpecs()">Extract Specs</button>
                        </div>
                    </div>

                    <div class="takeoff-step" data-step="3">
                        <div class="step-header">
                            <span class="step-number">3</span>
                            <span class="step-title">Door/Window Schedules</span>
                            <span class="step-status pending">Pending</span>
                        </div>
                        <div class="step-content">
                            <div class="takeoff-counts">
                                <div class="count-field">
                                    <label>Doors</label>
                                    <input type="number" id="doorCount" value="${this.takeoffData?.doors || 0}" onchange="unifiedScope.updateCount('doors', this.value)">
                                </div>
                                <div class="count-field">
                                    <label>Windows</label>
                                    <input type="number" id="windowCount" value="${this.takeoffData?.windows || 0}" onchange="unifiedScope.updateCount('windows', this.value)">
                                </div>
                            </div>
                            <button class="step-btn" onclick="unifiedScope.viewSchedules()">View Schedules</button>
                        </div>
                    </div>

                    <div class="takeoff-step" data-step="4">
                        <div class="step-header">
                            <span class="step-number">4</span>
                            <span class="step-title">Elevations</span>
                            <span class="step-status pending">Pending</span>
                        </div>
                        <div class="step-content">
                            <p>Review elevations for storefront, curtainwall, and glazing</p>
                            <button class="step-btn" onclick="unifiedScope.viewElevations()">View Elevations</button>
                        </div>
                    </div>

                    <div class="takeoff-step" data-step="5">
                        <div class="step-header">
                            <span class="step-number">5</span>
                            <span class="step-title">Verification</span>
                            <span class="step-status pending">Pending</span>
                        </div>
                        <div class="step-content">
                            <p>Verify counts and submit for pricing</p>
                            <button class="step-btn primary" onclick="unifiedScope.completeTakeoff()">Complete Takeoff</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    switchTab(tabName) {
        this.currentTab = tabName;
        this.render();
    }

    updateScopeCards(cards) {
        this.scopeCards = cards;
        if (this.currentTab === 'overview') {
            this.render();
        }
    }

    async loadRAGResults() {
        try {
            const response = await fetch(`/api/project/${this.projectId}/rag-scope`);
            if (response.ok) {
                this.ragResults = await response.json();
                if (this.currentTab === 'rag') {
                    this.render();
                }
            }
        } catch (error) {
            console.error('Failed to load RAG results:', error);
            this.ragResults = { error: 'Failed to load' };
        }
    }

    async loadTakeoffData() {
        try {
            const response = await fetch(`/api/project/${this.projectId}/takeoff`);
            if (response.ok) {
                this.takeoffData = await response.json();
                if (this.currentTab === 'takeoff') {
                    this.render();
                }
            }
        } catch (error) {
            console.error('Failed to load takeoff data:', error);
            this.takeoffData = {};
        }
    }

    // Action methods
    async runAnalysis() {
        console.log('Running analysis...');
        const btn = event.target.closest('.analysis-btn');
        btn.disabled = true;
        btn.innerHTML = '<span class="btn-icon">⏳</span> Running...';

        try {
            const response = await fetch(`/api/project/${this.projectId}/pipeline/run`, {
                method: 'POST'
            });

            if (response.ok) {
                setTimeout(() => {
                    btn.disabled = false;
                    btn.innerHTML = '<span class="btn-icon">✅</span> Analysis Complete';
                }, 2000);
            }
        } catch (error) {
            console.error('Analysis failed:', error);
            btn.disabled = false;
            btn.innerHTML = '<span class="btn-icon">❌</span> Failed';
        }
    }

    scanDocuments() {
        console.log('Scanning documents...');
        const progressContainer = document.getElementById('scanProgressContainer');
        if (progressContainer) {
            progressContainer.style.display = 'block';
        }
    }

    extractCSI() {
        console.log('Extracting CSI tags...');
    }

    viewDocs(cardId) {
        console.log('Viewing docs for card:', cardId);
        if (typeof documentViewer !== 'undefined') {
            const card = this.scopeCards.find(c => c.id === cardId);
            documentViewer.open(cardId, card);
        }
    }

    openDocuments() {
        console.log('Opening documents...');
    }

    extractSpecs() {
        console.log('Extracting specs...');
    }

    viewSchedules() {
        console.log('Viewing schedules...');
    }

    viewElevations() {
        console.log('Viewing elevations...');
    }

    updateCount(type, value) {
        if (!this.takeoffData) {
            this.takeoffData = {};
        }
        this.takeoffData[type] = parseInt(value) || 0;
        console.log(`Updated ${type} count to ${value}`);
    }

    completeTakeoff() {
        console.log('Completing takeoff...');
        alert('Takeoff verification complete! Ready for pricing.');
    }
}

// Global instance (will be initialized in template)
let unifiedScope = null;
