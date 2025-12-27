/**
 * Drawing Lightbox Component
 *
 * Full-screen PDF viewer with:
 * - Prev/Next navigation within category
 * - Zoom controls
 * - Jump to related drawings
 * - Keyboard navigation (arrow keys, escape)
 */

class DrawingLightbox {
    constructor() {
        this.currentPath = null;
        this.currentCategory = null;
        this.currentIndex = 0;
        this.drawings = [];
        this.zoomLevel = 100;
        this.isOpen = false;

        this._createDom();
        this._attachEventListeners();
    }

    _createDom() {
        // Create lightbox container
        this.container = document.createElement('div');
        this.container.className = 'drawing-lightbox';
        this.container.innerHTML = `
            <div class="lightbox-overlay" onclick="drawingLightbox.close()"></div>
            <div class="lightbox-content">
                <div class="lightbox-header">
                    <div class="lightbox-title">
                        <span class="lightbox-category"></span>
                        <span class="lightbox-filename"></span>
                    </div>
                    <div class="lightbox-controls">
                        <button class="lightbox-btn" onclick="drawingLightbox.zoomOut()" title="Zoom Out">-</button>
                        <span class="lightbox-zoom">100%</span>
                        <button class="lightbox-btn" onclick="drawingLightbox.zoomIn()" title="Zoom In">+</button>
                        <button class="lightbox-btn" onclick="drawingLightbox.resetZoom()" title="Reset Zoom">Reset</button>
                        <button class="lightbox-btn" onclick="drawingLightbox.openInNewTab()" title="Open in New Tab">Open</button>
                        <button class="lightbox-btn close" onclick="drawingLightbox.close()" title="Close">&times;</button>
                    </div>
                </div>
                <div class="lightbox-body">
                    <button class="lightbox-nav prev" onclick="drawingLightbox.prev()" title="Previous Drawing">
                        <span>&lsaquo;</span>
                    </button>
                    <div class="lightbox-viewer">
                        <iframe class="lightbox-iframe" src=""></iframe>
                    </div>
                    <button class="lightbox-nav next" onclick="drawingLightbox.next()" title="Next Drawing">
                        <span>&rsaquo;</span>
                    </button>
                </div>
                <div class="lightbox-footer">
                    <span class="lightbox-counter"></span>
                    <div class="lightbox-thumbnails"></div>
                </div>
            </div>
        `;

        document.body.appendChild(this.container);

        // Cache DOM references
        this.overlay = this.container.querySelector('.lightbox-overlay');
        this.iframe = this.container.querySelector('.lightbox-iframe');
        this.categoryEl = this.container.querySelector('.lightbox-category');
        this.filenameEl = this.container.querySelector('.lightbox-filename');
        this.zoomEl = this.container.querySelector('.lightbox-zoom');
        this.counterEl = this.container.querySelector('.lightbox-counter');
        this.thumbnailsEl = this.container.querySelector('.lightbox-thumbnails');
        this.prevBtn = this.container.querySelector('.lightbox-nav.prev');
        this.nextBtn = this.container.querySelector('.lightbox-nav.next');
    }

    _attachEventListeners() {
        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (!this.isOpen) return;

            switch (e.key) {
                case 'Escape':
                    this.close();
                    break;
                case 'ArrowLeft':
                    this.prev();
                    break;
                case 'ArrowRight':
                    this.next();
                    break;
                case '+':
                case '=':
                    this.zoomIn();
                    break;
                case '-':
                    this.zoomOut();
                    break;
            }
        });
    }

    open(path, category, drawingsData = null) {
        this.currentPath = path;
        this.currentCategory = category;
        this.isOpen = true;

        // Set drawings list from global data or provided data
        if (drawingsData && drawingsData.categories && drawingsData.categories[category]) {
            this.drawings = drawingsData.categories[category];
        } else if (window.drawingsData && window.drawingsData.categories && window.drawingsData.categories[category]) {
            this.drawings = window.drawingsData.categories[category];
        } else {
            this.drawings = [{ path: path, name: path.split('/').pop() }];
        }

        // Find current index
        this.currentIndex = this.drawings.findIndex(d => d.path === path);
        if (this.currentIndex === -1) this.currentIndex = 0;

        // Show container
        this.container.style.display = 'flex';
        document.body.style.overflow = 'hidden';

        // Load drawing
        this._loadDrawing();
        this._updateThumbnails();
    }

    close() {
        this.isOpen = false;
        this.container.style.display = 'none';
        document.body.style.overflow = '';
        this.iframe.src = '';
    }

    prev() {
        if (this.currentIndex > 0) {
            this.currentIndex--;
            this._loadDrawing();
        }
    }

    next() {
        if (this.currentIndex < this.drawings.length - 1) {
            this.currentIndex++;
            this._loadDrawing();
        }
    }

    goTo(index) {
        if (index >= 0 && index < this.drawings.length) {
            this.currentIndex = index;
            this._loadDrawing();
        }
    }

    zoomIn() {
        this.zoomLevel = Math.min(200, this.zoomLevel + 25);
        this._applyZoom();
    }

    zoomOut() {
        this.zoomLevel = Math.max(50, this.zoomLevel - 25);
        this._applyZoom();
    }

    resetZoom() {
        this.zoomLevel = 100;
        this._applyZoom();
    }

    _applyZoom() {
        this.iframe.style.transform = `scale(${this.zoomLevel / 100})`;
        this.zoomEl.textContent = `${this.zoomLevel}%`;
    }

    openInNewTab() {
        const drawing = this.drawings[this.currentIndex];
        if (drawing && drawing.path) {
            const encodedPath = encodeURIComponent(drawing.path);
            window.open(`/api/pdf/view?path=${encodedPath}`, '_blank');
        }
    }

    _loadDrawing() {
        const drawing = this.drawings[this.currentIndex];
        if (!drawing) return;

        // Load PDF in iframe
        const encodedPath = encodeURIComponent(drawing.path);
        this.iframe.src = `/api/pdf/view?path=${encodedPath}`;

        // Update UI
        this.filenameEl.textContent = drawing.name || drawing.path.split('/').pop();
        this.categoryEl.textContent = this._formatCategory(this.currentCategory);
        this.counterEl.textContent = `${this.currentIndex + 1} of ${this.drawings.length}`;

        // Update nav buttons
        this.prevBtn.style.visibility = this.currentIndex > 0 ? 'visible' : 'hidden';
        this.nextBtn.style.visibility = this.currentIndex < this.drawings.length - 1 ? 'visible' : 'hidden';

        // Update thumbnails active state
        const thumbs = this.thumbnailsEl.querySelectorAll('.lightbox-thumb');
        thumbs.forEach((thumb, i) => {
            thumb.classList.toggle('active', i === this.currentIndex);
        });
    }

    _updateThumbnails() {
        // Show mini-thumbnails for navigation
        let html = '';
        this.drawings.slice(0, 10).forEach((drawing, i) => {
            const activeClass = i === this.currentIndex ? 'active' : '';
            const sheet = drawing.sheet || drawing.name.substring(0, 6);
            html += `
                <div class="lightbox-thumb ${activeClass}" onclick="drawingLightbox.goTo(${i})" title="${drawing.name}">
                    ${sheet}
                </div>
            `;
        });

        if (this.drawings.length > 10) {
            html += `<div class="lightbox-thumb-more">+${this.drawings.length - 10}</div>`;
        }

        this.thumbnailsEl.innerHTML = html;
    }

    _formatCategory(category) {
        const names = {
            'elevations': 'Elevations',
            'floor_plans': 'Floor Plans',
            'schedules': 'Schedules',
            'sections': 'Sections',
            'other': 'Other'
        };
        return names[category] || category;
    }
}

// Create global instance
const drawingLightbox = new DrawingLightbox();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DrawingLightbox;
}
