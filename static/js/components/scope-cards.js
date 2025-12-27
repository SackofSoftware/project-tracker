/**
 * Scope Cards Component
 * Renders and manages the 7 Division 8 scope cards
 */

class ScopeCardsManager {
    constructor(containerEl, projectId) {
        this.container = containerEl;
        this.projectId = projectId;
        this.cards = new Map();
        this.onViewDocs = null; // Callback for view docs button
    }

    /**
     * Load and render scope cards from API
     */
    async load() {
        try {
            this.container.innerHTML = '<div class="loading-skeleton">Loading scope cards...</div>';

            const response = await fetch(`/api/project/${this.projectId}/scope-cards`);
            if (!response.ok) throw new Error('Failed to load scope cards');

            const data = await response.json();
            this.render(data.cards);
            return data;
        } catch (error) {
            console.error('Error loading scope cards:', error);
            this.container.innerHTML = `
                <div class="error-message">
                    Failed to load scope cards.
                    <button onclick="scopeCards.load()">Retry</button>
                </div>
            `;
            throw error;
        }
    }

    /**
     * Render all scope cards
     */
    render(cardsData) {
        this.container.innerHTML = '';
        this.cards.clear();

        const grid = document.createElement('div');
        grid.className = 'scope-cards-grid';

        // Sort by order
        const sortedCards = [...cardsData].sort((a, b) => a.order - b.order);

        sortedCards.forEach((cardData, index) => {
            const cardEl = this.createCardElement(cardData);
            cardEl.style.animationDelay = `${index * 0.1}s`;
            cardEl.classList.add('arriving');
            grid.appendChild(cardEl);
            this.cards.set(cardData.id, { element: cardEl, data: cardData });
        });

        this.container.appendChild(grid);
    }

    /**
     * Create a single scope card element
     */
    createCardElement(cardData) {
        const card = document.createElement('div');
        card.className = 'scope-card';
        card.dataset.category = cardData.id;
        card.dataset.status = cardData.status;

        const icon = this.getCardIcon(cardData.icon);
        const statusClass = cardData.status.replace('_', '-');
        const statusLabel = this.getStatusLabel(cardData.status);

        card.innerHTML = `
            <div class="scope-card-header">
                <span class="scope-card-icon">${icon}</span>
                <h3 class="scope-card-title">${cardData.title}</h3>
                <span class="scope-card-status ${statusClass}">${statusLabel}</span>
            </div>
            <div class="scope-card-body">
                ${this.renderCardFields(cardData)}
            </div>
            <div class="scope-card-footer">
                <span class="spec-refs">${cardData.spec_references?.join(', ') || ''}</span>
                <button class="view-docs-btn" data-card-id="${cardData.id}">View Docs</button>
                <button class="move-btn" data-card-id="${cardData.id}" title="Move to different category">↔</button>
            </div>
        `;

        // Event listeners
        card.querySelector('.view-docs-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            if (this.onViewDocs) {
                this.onViewDocs(cardData.id, cardData);
            }
        });

        card.querySelector('.move-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this.showMoveMenu(cardData.id, e.target);
        });

        return card;
    }

    /**
     * Render card body fields
     */
    renderCardFields(cardData) {
        const data = cardData.data || {};

        // Don't show fields for non-specified cards
        if (cardData.status === 'not_specified') {
            return `
                <div class="scope-field empty">
                    <span>Not specified in project documents</span>
                </div>
            `;
        }

        if (cardData.status === 'by_others') {
            return `
                <div class="scope-field empty">
                    <span>Excluded from Division 8 scope</span>
                </div>
                ${cardData.notes?.length ? `
                    <div class="scope-field">
                        <label>Note</label>
                        <span>${cardData.notes[0]}</span>
                    </div>
                ` : ''}
            `;
        }

        let html = '';

        // Basis of Design
        if (data.basis_of_design) {
            html += `
                <div class="scope-field">
                    <label>Basis of Design</label>
                    <span>${data.basis_of_design}</span>
                </div>
            `;
        }

        // Material
        if (data.material) {
            html += `
                <div class="scope-field">
                    <label>Material</label>
                    <span>${data.material}</span>
                </div>
            `;
        }

        // Finish
        if (data.finish) {
            html += `
                <div class="scope-field">
                    <label>Finish</label>
                    <span>${data.finish}</span>
                </div>
            `;
        }

        // Count
        if (data.count) {
            html += `
                <div class="scope-field">
                    <label>Quantity</label>
                    <span>${data.count}</span>
                </div>
            `;
        }

        // Performance specs
        if (data.performance && Object.keys(data.performance).length > 0) {
            html += `
                <div class="scope-field">
                    <label>Performance</label>
                    <div class="performance-specs">
                        ${this.renderPerformanceSpecs(data.performance)}
                    </div>
                </div>
            `;
        }

        // If no fields, show placeholder
        if (!html) {
            html = `
                <div class="scope-field empty">
                    <span>Analysis pending</span>
                </div>
            `;
        }

        return html;
    }

    /**
     * Render performance specifications
     */
    renderPerformanceSpecs(perf) {
        const specs = [];
        if (perf.u_factor) specs.push(`U: ${perf.u_factor}`);
        if (perf.shgc) specs.push(`SHGC: ${perf.shgc}`);
        if (perf.vlt) specs.push(`VLT: ${perf.vlt}%`);
        if (perf.stc) specs.push(`STC: ${perf.stc}`);
        return specs.map(s => `<span>${s}</span>`).join('');
    }

    /**
     * Get icon for card type
     */
    getCardIcon(iconType) {
        const icons = {
            'glass': '🪟',
            'storefront': '🏪',
            'window': '⬜',
            'door-metal': '🚪',
            'door-wood': '🚪',
            'hardware': '🔑',
            'specialty': '✨'
        };
        return icons[iconType] || '📦';
    }

    /**
     * Get human-readable status label
     */
    getStatusLabel(status) {
        const labels = {
            'specified': 'Specified',
            'not_specified': 'Not Specified',
            'by_others': 'By Others',
            'pending': 'Pending'
        };
        return labels[status] || status;
    }

    /**
     * Update a single card with new data
     */
    updateCard(cardId, newData) {
        const cardInfo = this.cards.get(cardId);
        if (!cardInfo) return;

        // Update data
        cardInfo.data = { ...cardInfo.data, ...newData };

        // Re-render card
        const newCardEl = this.createCardElement(cardInfo.data);
        newCardEl.classList.add('updating');
        cardInfo.element.replaceWith(newCardEl);
        cardInfo.element = newCardEl;
        this.cards.set(cardId, cardInfo);

        // Remove animation class after animation completes
        setTimeout(() => {
            newCardEl.classList.remove('updating');
        }, 500);
    }

    /**
     * Show move menu for reclassifying scope items
     */
    showMoveMenu(cardId, anchorEl) {
        // Remove existing menu
        document.querySelectorAll('.move-menu').forEach(el => el.remove());

        const menu = document.createElement('div');
        menu.className = 'move-menu';
        menu.style.cssText = `
            position: absolute;
            background: var(--card-bg);
            border: 2px solid var(--border);
            box-shadow: 4px 4px 0 var(--border);
            z-index: 100;
            padding: 0.5rem 0;
        `;

        const cardTypes = [
            { id: 'glass-glazing', label: 'Glass & Glazing' },
            { id: 'storefront-curtainwall', label: 'Storefront & Curtain Wall' },
            { id: 'commercial-windows', label: 'Commercial Windows' },
            { id: 'metal-doors', label: 'Metal Doors & Frames' },
            { id: 'wood-doors', label: 'Wood Doors' },
            { id: 'door-hardware', label: 'Door Hardware' },
            { id: 'specialties', label: 'Specialties' }
        ];

        cardTypes.forEach(type => {
            if (type.id !== cardId) {
                const item = document.createElement('button');
                item.textContent = `Move to ${type.label}`;
                item.style.cssText = `
                    display: block;
                    width: 100%;
                    padding: 0.5rem 1rem;
                    text-align: left;
                    border: none;
                    background: none;
                    font-size: 0.75rem;
                    cursor: pointer;
                `;
                item.onmouseover = () => item.style.background = 'var(--bg)';
                item.onmouseout = () => item.style.background = 'none';
                item.onclick = () => {
                    this.moveToCard(cardId, type.id);
                    menu.remove();
                };
                menu.appendChild(item);
            }
        });

        // Position menu
        const rect = anchorEl.getBoundingClientRect();
        menu.style.top = `${rect.bottom + window.scrollY}px`;
        menu.style.left = `${rect.left + window.scrollX}px`;

        document.body.appendChild(menu);

        // Close on click outside
        const closeMenu = (e) => {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        };
        setTimeout(() => document.addEventListener('click', closeMenu), 0);
    }

    /**
     * Move scope item to different card
     */
    async moveToCard(fromCardId, toCardId) {
        try {
            const response = await fetch(`/api/project/${this.projectId}/scope-cards/${fromCardId}/move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_card: toCardId })
            });

            if (!response.ok) throw new Error('Failed to move item');

            // Reload cards to reflect change
            await this.load();
        } catch (error) {
            console.error('Error moving scope item:', error);
            alert('Failed to move scope item');
        }
    }

    /**
     * Set callback for View Docs button
     */
    setOnViewDocs(callback) {
        this.onViewDocs = callback;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ScopeCardsManager;
}
