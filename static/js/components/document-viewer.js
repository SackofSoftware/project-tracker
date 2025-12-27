/**
 * Document Viewer Component
 * Full-screen overlay for viewing project specs and drawings
 */

class DocumentViewer {
    constructor(projectId) {
        this.projectId = projectId;
        this.currentCardId = null;
        this.documents = { specs: [], drawings: [] };
        this.activeCategory = 'all';
        this.overlay = null;
        this.lightbox = null;
    }

    /**
     * Initialize the document viewer
     */
    init() {
        this.createOverlay();
        this.createLightbox();
    }

    /**
     * Create the overlay element
     */
    createOverlay() {
        this.overlay = document.createElement('div');
        this.overlay.className = 'document-viewer-overlay';
        this.overlay.innerHTML = `
            <div class="document-viewer">
                <div class="document-viewer-header">
                    <h2 class="document-viewer-title">Documents</h2>
                    <button class="document-viewer-close">✕ Close</button>
                </div>
                <div class="spec-sections-panel">
                    <div class="spec-sections-list"></div>
                </div>
                <div class="drawings-panel">
                    <div class="drawings-tabs">
                        <button class="drawings-tab active" data-category="all">All</button>
                        <button class="drawings-tab" data-category="floor_plan">Floor Plans</button>
                        <button class="drawings-tab" data-category="elevation">Elevations</button>
                        <button class="drawings-tab" data-category="schedule">Schedules</button>
                        <button class="drawings-tab" data-category="detail">Details</button>
                    </div>
                    <div class="thumbnail-grid"></div>
                </div>
            </div>
        `;

        document.body.appendChild(this.overlay);

        // Bind events
        this.overlay.querySelector('.document-viewer-close').addEventListener('click', () => this.close());
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) this.close();
        });

        // Tab switching
        this.overlay.querySelectorAll('.drawings-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                this.setActiveCategory(tab.dataset.category);
            });
        });

        // Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.overlay.classList.contains('active')) {
                this.close();
            }
        });
    }

    /**
     * Create lightbox for full PDF viewing
     */
    createLightbox() {
        this.lightbox = document.createElement('div');
        this.lightbox.className = 'lightbox-overlay';
        this.lightbox.innerHTML = `
            <div class="lightbox-content">
                <button class="lightbox-nav lightbox-prev">‹</button>
                <iframe class="lightbox-pdf" src=""></iframe>
                <button class="lightbox-nav lightbox-next">›</button>
                <button class="lightbox-close">✕ Close</button>
                <div class="lightbox-info"></div>
            </div>
        `;

        document.body.appendChild(this.lightbox);

        // Bind events
        this.lightbox.querySelector('.lightbox-close').addEventListener('click', () => this.closeLightbox());
        this.lightbox.querySelector('.lightbox-prev').addEventListener('click', () => this.navigateLightbox(-1));
        this.lightbox.querySelector('.lightbox-next').addEventListener('click', () => this.navigateLightbox(1));
        this.lightbox.addEventListener('click', (e) => {
            if (e.target === this.lightbox) this.closeLightbox();
        });

        document.addEventListener('keydown', (e) => {
            if (this.lightbox.classList.contains('active')) {
                if (e.key === 'Escape') this.closeLightbox();
                if (e.key === 'ArrowLeft') this.navigateLightbox(-1);
                if (e.key === 'ArrowRight') this.navigateLightbox(1);
            }
        });
    }

    /**
     * Open document viewer for a scope card
     */
    async open(cardId, cardData) {
        this.currentCardId = cardId;
        this.overlay.querySelector('.document-viewer-title').textContent =
            `Documents: ${cardData?.title || cardId}`;

        // Show overlay
        this.overlay.classList.add('active');

        // Load documents
        await this.loadDocuments(cardId);
    }

    /**
     * Close document viewer
     */
    close() {
        this.overlay.classList.remove('active');
        this.currentCardId = null;
    }

    /**
     * Load documents for a scope card
     */
    async loadDocuments(cardId) {
        try {
            const specsList = this.overlay.querySelector('.spec-sections-list');
            const thumbnailGrid = this.overlay.querySelector('.thumbnail-grid');

            specsList.innerHTML = '<div class="loading">Loading specs...</div>';
            thumbnailGrid.innerHTML = '<div class="loading">Loading drawings...</div>';

            const response = await fetch(`/api/project/${this.projectId}/documents/for-card/${cardId}`);
            if (!response.ok) throw new Error('Failed to load documents');

            const data = await response.json();
            this.documents = data;

            this.renderSpecs(data.specs);
            this.renderDrawings(data.drawings);

        } catch (error) {
            console.error('Error loading documents:', error);
            this.overlay.querySelector('.spec-sections-list').innerHTML =
                '<div class="error">Failed to load specs</div>';
            this.overlay.querySelector('.thumbnail-grid').innerHTML =
                '<div class="error">Failed to load drawings</div>';
        }
    }

    /**
     * Render spec sections list
     */
    renderSpecs(specs) {
        const container = this.overlay.querySelector('.spec-sections-list');

        if (!specs || specs.length === 0) {
            container.innerHTML = '<div class="empty-state">No specifications found</div>';
            return;
        }

        container.innerHTML = specs.map(spec => `
            <div class="spec-section-item" data-doc-id="${spec.id}">
                <div class="spec-section-number">${spec.subcategory || spec.category}</div>
                <div class="spec-section-title">${spec.filename}</div>
            </div>
        `).join('');

        // Click to open spec
        container.querySelectorAll('.spec-section-item').forEach(item => {
            item.addEventListener('click', () => {
                const docId = item.dataset.docId;
                const spec = specs.find(s => s.id === docId);
                if (spec) this.openInLightbox(spec, specs);
            });
        });
    }

    /**
     * Render drawing thumbnails
     */
    renderDrawings(drawings) {
        const container = this.overlay.querySelector('.thumbnail-grid');

        if (!drawings || drawings.length === 0) {
            container.innerHTML = '<div class="empty-state">No drawings found</div>';
            return;
        }

        // Filter by active category
        let filtered = drawings;
        if (this.activeCategory !== 'all') {
            filtered = drawings.filter(d => d.category === this.activeCategory);
        }

        if (filtered.length === 0) {
            container.innerHTML = `<div class="empty-state">No ${this.activeCategory.replace('_', ' ')} drawings found</div>`;
            return;
        }

        container.innerHTML = filtered.map(drawing => `
            <div class="thumbnail-item" data-doc-id="${drawing.id}">
                <div class="thumbnail-image">
                    <img src="/api/project/${this.projectId}/document/${drawing.id}/thumbnail"
                         alt="${drawing.sheet_number || drawing.filename}"
                         loading="lazy"
                         onerror="this.parentElement.innerHTML='<span>📄</span>'">
                </div>
                <div class="thumbnail-info">
                    <div class="thumbnail-sheet">${drawing.sheet_number || '-'}</div>
                    <div class="thumbnail-name">${drawing.filename}</div>
                </div>
            </div>
        `).join('');

        // Click to open in lightbox
        container.querySelectorAll('.thumbnail-item').forEach(item => {
            item.addEventListener('click', () => {
                const docId = item.dataset.docId;
                const drawing = filtered.find(d => d.id === docId);
                if (drawing) this.openInLightbox(drawing, filtered);
            });
        });
    }

    /**
     * Set active drawing category
     */
    setActiveCategory(category) {
        this.activeCategory = category;

        // Update tab states
        this.overlay.querySelectorAll('.drawings-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.category === category);
        });

        // Re-render drawings
        this.renderDrawings(this.documents.drawings);
    }

    /**
     * Open document in lightbox
     */
    openInLightbox(doc, collection) {
        this.currentLightboxDoc = doc;
        this.currentLightboxCollection = collection;

        const iframe = this.lightbox.querySelector('.lightbox-pdf');
        const info = this.lightbox.querySelector('.lightbox-info');

        iframe.src = `/api/project/${this.projectId}/document/${doc.id}/serve`;
        info.textContent = doc.sheet_number
            ? `${doc.sheet_number} - ${doc.filename}`
            : doc.filename;

        this.lightbox.classList.add('active');
        this.updateLightboxNav();
    }

    /**
     * Close lightbox
     */
    closeLightbox() {
        this.lightbox.classList.remove('active');
        this.lightbox.querySelector('.lightbox-pdf').src = '';
        this.currentLightboxDoc = null;
    }

    /**
     * Navigate lightbox to prev/next document
     */
    navigateLightbox(direction) {
        if (!this.currentLightboxDoc || !this.currentLightboxCollection) return;

        const currentIndex = this.currentLightboxCollection.findIndex(
            d => d.id === this.currentLightboxDoc.id
        );
        const newIndex = currentIndex + direction;

        if (newIndex >= 0 && newIndex < this.currentLightboxCollection.length) {
            this.openInLightbox(
                this.currentLightboxCollection[newIndex],
                this.currentLightboxCollection
            );
        }
    }

    /**
     * Update lightbox navigation button states
     */
    updateLightboxNav() {
        if (!this.currentLightboxDoc || !this.currentLightboxCollection) return;

        const currentIndex = this.currentLightboxCollection.findIndex(
            d => d.id === this.currentLightboxDoc.id
        );

        const prevBtn = this.lightbox.querySelector('.lightbox-prev');
        const nextBtn = this.lightbox.querySelector('.lightbox-next');

        prevBtn.style.visibility = currentIndex > 0 ? 'visible' : 'hidden';
        nextBtn.style.visibility = currentIndex < this.currentLightboxCollection.length - 1
            ? 'visible' : 'hidden';
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DocumentViewer;
}
