/**
 * Glazing Takeoff Annotation Tool - Main Application
 *
 * Orchestrates PDF viewing, annotation canvas, and classification controls.
 */

// Import PDF.js
const pdfjsLib = await import('https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.min.mjs');

// Configure PDF.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.worker.min.mjs';

// ============================================================================
// STATE
// ============================================================================

const state = {
    // PDF state
    pdfDoc: null,
    currentPage: 1,
    totalPages: 0,
    scale: 1.0,
    currentPdfPath: null,

    // Fabric canvas
    fabricCanvas: null,

    // Current tool and settings
    currentTool: 'pan',
    currentCategory: 'window',
    currentTypeLabel: 'A',

    // Mode: 'tag' for standard annotations, 'zone' for zone drawing
    currentMode: 'tag',

    // Zone mode settings
    currentZoneType: 'elevation_zone',  // elevation_zone, floor_plan_zone, detail_zone, schedule_zone
    currentZoneDirection: 'north',       // north, south, east, west
    currentZoneLabel: '',
    currentDetailId: '',
    currentDetailTitle: '',
    currentDetailAppliesTo: [],

    // Polygon drawing state
    isDrawingPolygon: false,
    polygonPoints: [],
    tempPolygonLines: [],
    tempPolygonDots: [],

    // Annotations
    annotations: [],
    selectedAnnotation: null,

    // Undo stack
    undoStack: [],

    // Page dimensions in PDF coordinates
    pageWidth: 0,
    pageHeight: 0
};

// ============================================================================
// COLORS
// ============================================================================

const COLORS = window.APP_CONFIG?.colors || {
    window: { stroke: '#FF5722', fill: 'rgba(255,87,34,0.2)' },
    door: { stroke: '#9C27B0', fill: 'rgba(156,39,176,0.2)' },
    storefront: { stroke: '#4CAF50', fill: 'rgba(76,175,80,0.2)' },
    curtainwall: { stroke: '#2196F3', fill: 'rgba(33,150,243,0.2)' }
};

// Direction colors for elevation zones
const DIRECTION_COLORS = window.APP_CONFIG?.directionColors || {
    north: '#4CAF50',   // Green
    south: '#F44336',   // Red
    east: '#FF9800',    // Orange
    west: '#2196F3',    // Blue
    northeast: '#8BC34A',
    northwest: '#009688',
    southeast: '#FF5722',
    southwest: '#3F51B5'
};

// Zone type colors (for non-elevation zones)
const ZONE_COLORS = {
    elevation_zone: '#4CAF50',      // Uses direction colors
    floor_plan_zone: '#9C27B0',     // Purple
    detail_zone: '#FF9800',         // Orange
    schedule_zone: '#607D8B'        // Blue-grey
};

// ============================================================================
// INITIALIZATION
// ============================================================================

async function init() {
    console.log('Initializing annotation tool...');

    // Get elements
    const pdfCanvas = document.getElementById('pdf-canvas');
    const annotationCanvas = document.getElementById('annotation-canvas');

    // Initialize Fabric.js canvas
    state.fabricCanvas = new fabric.Canvas('annotation-canvas', {
        selection: false,
        preserveObjectStacking: true
    });

    // Set up event handlers
    setupToolbar();
    setupClassification();
    setupZoneMode();
    setupKeyboardShortcuts();
    setupCanvasEvents();
    setupPanZoom();
    setupDetection();

    // Load PDF list
    await loadPdfList();

    // Load initial PDF if specified
    if (window.APP_CONFIG?.initialPdf) {
        await loadPdf(window.APP_CONFIG.initialPdf);
    }

    updateStatus('Ready - Select a PDF to begin');
}

// ============================================================================
// PDF LOADING
// ============================================================================

async function loadPdfList() {
    try {
        const response = await fetch(`/api/project/${window.APP_CONFIG.projectId}/files`);
        const data = await response.json();

        const select = document.getElementById('pdf-select');
        select.innerHTML = '<option value="">Select a PDF...</option>';

        // Add drawings first
        if (data.drawings?.length > 0) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = 'Drawings';
            data.drawings.forEach(file => {
                const option = document.createElement('option');
                option.value = file.path;
                option.textContent = file.name;
                optgroup.appendChild(option);
            });
            select.appendChild(optgroup);
        }

        // Add specs
        if (data.specs?.length > 0) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = 'Specifications';
            data.specs.forEach(file => {
                const option = document.createElement('option');
                option.value = file.path;
                option.textContent = file.name;
                optgroup.appendChild(option);
            });
            select.appendChild(optgroup);
        }

        // Add other PDFs
        if (data.other?.length > 0) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = 'Other';
            data.other.forEach(file => {
                const option = document.createElement('option');
                option.value = file.path;
                option.textContent = file.name;
                optgroup.appendChild(option);
            });
            select.appendChild(optgroup);
        }

        // Handle selection
        select.addEventListener('change', async () => {
            if (select.value) {
                await loadPdf(select.value);
            }
        });

    } catch (error) {
        console.error('Failed to load PDF list:', error);
        updateStatus('Error loading PDF list');
    }
}

async function loadPdf(pdfPath) {
    showLoading(true);
    updateStatus(`Loading ${pdfPath}...`);

    try {
        // Build URL to fetch PDF
        const pdfUrl = `/api/project/${window.APP_CONFIG.projectId}/file/${encodeURIComponent(pdfPath)}`;

        // Load PDF document
        state.pdfDoc = await pdfjsLib.getDocument(pdfUrl).promise;
        state.totalPages = state.pdfDoc.numPages;
        state.currentPage = 1;
        state.currentPdfPath = pdfPath;

        // Update PDF select
        document.getElementById('pdf-select').value = pdfPath;

        // Render first page
        await renderPage(1);

        // Generate thumbnails
        await generateThumbnails();

        // Load annotations for this PDF
        await loadAnnotations();

        updateStatus(`Loaded: ${pdfPath} (${state.totalPages} pages)`);

    } catch (error) {
        console.error('Failed to load PDF:', error);
        updateStatus('Error loading PDF');
    } finally {
        showLoading(false);
    }
}

async function renderPage(pageNum) {
    if (!state.pdfDoc) return;

    const page = await state.pdfDoc.getPage(pageNum);

    // Store page dimensions (unscaled)
    const unscaledViewport = page.getViewport({ scale: 1.0 });
    state.pageWidth = unscaledViewport.width;
    state.pageHeight = unscaledViewport.height;

    // Calculate display dimensions based on scale
    const displayWidth = Math.floor(state.pageWidth * state.scale);
    const displayHeight = Math.floor(state.pageHeight * state.scale);

    // Hide the PDF canvas - we'll render PDF to Fabric background instead
    const pdfCanvas = document.getElementById('pdf-canvas');
    pdfCanvas.style.display = 'none';

    // Create an offscreen canvas for PDF rendering
    const offscreenCanvas = document.createElement('canvas');
    const offscreenContext = offscreenCanvas.getContext('2d');

    // Render at display scale for quality
    const viewport = page.getViewport({ scale: state.scale });
    offscreenCanvas.width = viewport.width;
    offscreenCanvas.height = viewport.height;

    // Render PDF to offscreen canvas
    await page.render({
        canvasContext: offscreenContext,
        viewport: viewport
    }).promise;

    // Convert to data URL
    const pdfDataUrl = offscreenCanvas.toDataURL('image/png');

    // Get the annotation canvas element and container
    const annotationCanvasEl = document.getElementById('annotation-canvas');
    const canvasContainer = document.getElementById('canvas-container');

    // Update container size to match display size
    canvasContainer.style.width = displayWidth + 'px';
    canvasContainer.style.height = displayHeight + 'px';

    // Check if this is a page change or initial load
    const isPageChange = state.currentPage !== pageNum;

    if (isPageChange || !state.fabricCanvas) {
        // Dispose old canvas
        if (state.fabricCanvas) {
            state.fabricCanvas.dispose();
        }

        // Create fresh Fabric canvas at display dimensions
        state.fabricCanvas = new fabric.Canvas('annotation-canvas', {
            selection: false,
            preserveObjectStacking: true,
            width: displayWidth,
            height: displayHeight
        });

        // Re-setup canvas events
        setupCanvasEventsInternal();
    } else {
        // Zoom change: just resize
        state.fabricCanvas.setDimensions({
            width: displayWidth,
            height: displayHeight
        });
    }

    // Set PDF as background image
    fabric.Image.fromURL(pdfDataUrl, (img) => {
        // Scale image to fit canvas (should be 1:1 since we rendered at correct size)
        state.fabricCanvas.setBackgroundImage(img, state.fabricCanvas.renderAll.bind(state.fabricCanvas), {
            scaleX: 1,
            scaleY: 1,
            originX: 'left',
            originY: 'top'
        });
    });

    // Update current page
    state.currentPage = pageNum;

    // Redraw annotations for this page
    redrawAnnotations();

    // Update UI
    document.getElementById('page-info').textContent = `Page ${pageNum} / ${state.totalPages}`;
    document.getElementById('zoom-display').textContent = `${Math.round(state.scale * 100)}%`;

    // Update thumbnail selection
    document.querySelectorAll('.page-thumb').forEach((thumb, idx) => {
        thumb.classList.toggle('active', idx + 1 === pageNum);
    });
}

async function generateThumbnails() {
    const container = document.getElementById('thumbnail-container');
    container.innerHTML = '';

    for (let i = 1; i <= Math.min(state.totalPages, 50); i++) {
        const page = await state.pdfDoc.getPage(i);
        const viewport = page.getViewport({ scale: 0.2 });

        const canvas = document.createElement('canvas');
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const context = canvas.getContext('2d');

        await page.render({
            canvasContext: context,
            viewport: viewport
        }).promise;

        const thumb = document.createElement('div');
        thumb.className = 'page-thumb' + (i === 1 ? ' active' : '');
        thumb.innerHTML = `
            <img src="${canvas.toDataURL()}" alt="Page ${i}">
            <div class="page-num">${i}</div>
        `;
        thumb.addEventListener('click', () => renderPage(i));

        container.appendChild(thumb);
    }
}

// ============================================================================
// ANNOTATIONS
// ============================================================================

async function loadAnnotations() {
    if (!state.currentPdfPath) return;

    try {
        const response = await fetch(
            `/api/project/${window.APP_CONFIG.projectId}/annotations?pdf=${encodeURIComponent(state.currentPdfPath)}`
        );
        const data = await response.json();
        state.annotations = data.annotations || [];

        redrawAnnotations();
        updateAnnotationList();
        updateTagSummary();

    } catch (error) {
        console.error('Failed to load annotations:', error);
    }
}

function redrawAnnotations() {
    // Clear canvas
    state.fabricCanvas.clear();

    // Get annotations for current page
    const pageAnnotations = state.annotations.filter(a => a.page_number === state.currentPage);

    // Draw each annotation
    pageAnnotations.forEach(ann => {
        drawAnnotation(ann);
    });

    state.fabricCanvas.renderAll();
}

function drawAnnotation(annotation) {
    if (!annotation.geometry?.points) return;

    // Convert PDF coordinates to display coordinates
    // PDF origin is bottom-left, canvas origin is top-left
    const points = annotation.geometry.points.map(([x, y]) => ({
        x: x * state.scale,
        y: (state.pageHeight - y) * state.scale
    }));

    // Determine if this is a zone annotation
    const isZone = annotation.annotation_type?.endsWith('_zone') ||
                   annotation.classification?.category?.endsWith('_zone');

    // Get colors based on annotation type
    let strokeColor, fillColor;
    if (isZone) {
        strokeColor = getZoneColor(annotation);
        // Zones use 8% fill opacity
        fillColor = hexToRgba(strokeColor, 0.08);
    } else {
        const colors = COLORS[annotation.classification?.category] || COLORS.window;
        strokeColor = colors.stroke;
        fillColor = colors.fill;
    }

    const polygon = new fabric.Polygon(points, {
        fill: fillColor,
        stroke: strokeColor,
        strokeWidth: isZone ? 3 : 2,
        strokeDashArray: isZone ? [8, 4] : null,  // Dashed for zones
        selectable: true,
        hasControls: false,
        hasBorders: true,
        objectCaching: false,
        annotationId: annotation.id
    });

    // Determine label text
    let labelText = '';
    if (isZone) {
        labelText = getZoneLabel(annotation);
    } else if (annotation.classification?.typeLabel) {
        labelText = annotation.classification.typeLabel;
    }

    // Add label if exists
    if (labelText) {
        const center = polygon.getCenterPoint();
        const fontSize = isZone ? 16 : 14;
        const label = new fabric.Text(labelText, {
            left: center.x,
            top: center.y,
            fontSize: fontSize,
            fontWeight: 'bold',
            fill: strokeColor,
            originX: 'center',
            originY: 'center',
            selectable: false,
            evented: false
        });

        const group = new fabric.Group([polygon, label], {
            selectable: true,
            hasControls: false,
            annotationId: annotation.id
        });

        state.fabricCanvas.add(group);
    } else {
        state.fabricCanvas.add(polygon);
    }
}

/**
 * Get the appropriate color for a zone annotation
 */
function getZoneColor(annotation) {
    const classification = annotation.classification || {};
    const zoneType = classification.category || annotation.annotation_type;

    // Elevation zones use direction colors
    if (zoneType === 'elevation_zone' && classification.direction) {
        return DIRECTION_COLORS[classification.direction] || DIRECTION_COLORS.north;
    }

    // Floor plan zones with side specified use direction colors
    if (zoneType === 'floor_plan_zone' && classification.side) {
        return DIRECTION_COLORS[classification.side] || ZONE_COLORS.floor_plan_zone;
    }

    // Other zones use their type color
    return ZONE_COLORS[zoneType] || '#607D8B';
}

/**
 * Get the display label for a zone annotation
 */
function getZoneLabel(annotation) {
    const classification = annotation.classification || {};
    const zoneType = classification.category || annotation.annotation_type;

    switch (zoneType) {
        case 'elevation_zone':
            const dir = classification.direction || 'N';
            return dir.charAt(0).toUpperCase() + (classification.label || '');
        case 'floor_plan_zone':
            return classification.label || classification.side?.toUpperCase() || '';
        case 'detail_zone':
            return classification.detail_id || '';
        case 'schedule_zone':
            return classification.label || 'Schedule';
        default:
            return classification.label || '';
    }
}

/**
 * Convert hex color to rgba
 */
function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

async function saveAnnotation(annotation) {
    try {
        const method = annotation.id ? 'PUT' : 'POST';
        const url = annotation.id
            ? `/api/project/${window.APP_CONFIG.projectId}/annotations/${annotation.id}`
            : `/api/project/${window.APP_CONFIG.projectId}/annotations`;

        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(annotation)
        });

        if (!response.ok) {
            throw new Error('Failed to save annotation');
        }

        const saved = await response.json();

        // Update local state
        const idx = state.annotations.findIndex(a => a.id === saved.id);
        if (idx >= 0) {
            state.annotations[idx] = saved;
        } else {
            state.annotations.push(saved);
        }

        updateAnnotationList();
        updateTagSummary();

        return saved;

    } catch (error) {
        console.error('Failed to save annotation:', error);
        updateStatus('Error saving annotation');
        throw error;
    }
}

async function deleteAnnotation(annotationId) {
    try {
        const response = await fetch(
            `/api/project/${window.APP_CONFIG.projectId}/annotations/${annotationId}`,
            { method: 'DELETE' }
        );

        if (!response.ok) {
            throw new Error('Failed to delete annotation');
        }

        // Remove from local state
        state.annotations = state.annotations.filter(a => a.id !== annotationId);

        redrawAnnotations();
        updateAnnotationList();
        updateTagSummary();

    } catch (error) {
        console.error('Failed to delete annotation:', error);
        updateStatus('Error deleting annotation');
    }
}

// ============================================================================
// POLYGON DRAWING TOOL
// ============================================================================

function startPolygonDrawing(e) {
    if (state.currentTool !== 'polygon') return;

    const pointer = state.fabricCanvas.getPointer(e.e);

    // Get the drawing color based on mode
    const drawColor = getDrawingColor();

    if (!state.isDrawingPolygon) {
        // Start new polygon
        state.isDrawingPolygon = true;
        state.polygonPoints = [{ x: pointer.x, y: pointer.y }];

        // Add first dot
        const dot = new fabric.Circle({
            left: pointer.x - 4,
            top: pointer.y - 4,
            radius: 4,
            fill: drawColor,
            selectable: false,
            evented: false
        });
        state.tempPolygonDots.push(dot);
        state.fabricCanvas.add(dot);

        const modeText = state.currentMode === 'zone' ? 'zone' : 'tag';
        updateStatus(`Click to add points. Double-click to close ${modeText}.`);

    } else {
        // Add point to polygon
        state.polygonPoints.push({ x: pointer.x, y: pointer.y });

        // Add line from previous point
        const lastPoint = state.polygonPoints[state.polygonPoints.length - 2];
        const strokeDash = state.currentMode === 'zone' ? [6, 3] : null;
        const line = new fabric.Line(
            [lastPoint.x, lastPoint.y, pointer.x, pointer.y],
            {
                stroke: drawColor,
                strokeWidth: state.currentMode === 'zone' ? 3 : 2,
                strokeDashArray: strokeDash,
                selectable: false,
                evented: false
            }
        );
        state.tempPolygonLines.push(line);
        state.fabricCanvas.add(line);

        // Add dot
        const dot = new fabric.Circle({
            left: pointer.x - 4,
            top: pointer.y - 4,
            radius: 4,
            fill: drawColor,
            selectable: false,
            evented: false
        });
        state.tempPolygonDots.push(dot);
        state.fabricCanvas.add(dot);

        state.fabricCanvas.renderAll();
    }
}

/**
 * Get the color to use for drawing based on current mode
 */
function getDrawingColor() {
    if (state.currentMode === 'zone') {
        // Zone mode - use direction or zone type color
        if (state.currentZoneType === 'elevation_zone' || state.currentZoneType === 'floor_plan_zone') {
            return DIRECTION_COLORS[state.currentZoneDirection] || DIRECTION_COLORS.north;
        }
        return ZONE_COLORS[state.currentZoneType] || ZONE_COLORS.elevation_zone;
    } else {
        // Tag mode - use category color
        return COLORS[state.currentCategory]?.stroke || COLORS.window.stroke;
    }
}

async function finishPolygon() {
    if (!state.isDrawingPolygon || state.polygonPoints.length < 3) {
        cancelPolygon();
        return;
    }

    // Clear temp objects
    state.tempPolygonLines.forEach(obj => state.fabricCanvas.remove(obj));
    state.tempPolygonDots.forEach(obj => state.fabricCanvas.remove(obj));
    state.tempPolygonLines = [];
    state.tempPolygonDots = [];

    // Convert canvas coordinates to PDF coordinates
    const pdfPoints = state.polygonPoints.map(p => [
        p.x / state.scale,
        state.pageHeight - (p.y / state.scale)  // Flip Y back
    ]);

    // Create annotation object based on mode
    let annotation;

    if (state.currentMode === 'zone') {
        // Zone annotation
        annotation = {
            pdf_path: state.currentPdfPath,
            page_number: state.currentPage,
            annotation_type: state.currentZoneType,
            geometry: {
                type: 'polygon',
                points: pdfPoints
            },
            classification: buildZoneClassification()
        };
    } else {
        // Tag annotation (default)
        annotation = {
            pdf_path: state.currentPdfPath,
            page_number: state.currentPage,
            annotation_type: 'tag_marker',
            geometry: {
                type: 'polygon',
                points: pdfPoints
            },
            classification: {
                category: state.currentCategory,
                typeLabel: state.currentTypeLabel
            }
        };
    }

    // Save annotation
    try {
        await saveAnnotation(annotation);
        redrawAnnotations();

        if (state.currentMode === 'zone') {
            updateStatus(`Added ${state.currentZoneType}: ${getZoneSummary()}`);
        } else {
            updateStatus(`Added ${state.currentCategory} tag: ${state.currentTypeLabel}`);
        }
    } catch (error) {
        // Error handled in saveAnnotation
    }

    // Reset state
    state.isDrawingPolygon = false;
    state.polygonPoints = [];
}

/**
 * Build classification object for zone based on zone type
 */
function buildZoneClassification() {
    const classification = {
        category: state.currentZoneType,
        label: state.currentZoneLabel
    };

    switch (state.currentZoneType) {
        case 'elevation_zone':
            classification.direction = state.currentZoneDirection;
            break;
        case 'floor_plan_zone':
            classification.side = state.currentZoneDirection;
            classification.wing = state.currentZoneLabel;
            break;
        case 'detail_zone':
            classification.detail_id = state.currentDetailId;
            classification.detail_title = state.currentDetailTitle;
            classification.applies_to_types = state.currentDetailAppliesTo;
            break;
        case 'schedule_zone':
            classification.schedule_type = 'window';  // Default to window schedule
            break;
    }

    return classification;
}

/**
 * Get summary text for zone status message
 */
function getZoneSummary() {
    switch (state.currentZoneType) {
        case 'elevation_zone':
            return `${state.currentZoneDirection} elevation`;
        case 'floor_plan_zone':
            return `${state.currentZoneDirection} side`;
        case 'detail_zone':
            return state.currentDetailId || 'detail zone';
        case 'schedule_zone':
            return 'schedule zone';
        default:
            return 'zone';
    }
}

function cancelPolygon() {
    // Clear temp objects
    state.tempPolygonLines.forEach(obj => state.fabricCanvas.remove(obj));
    state.tempPolygonDots.forEach(obj => state.fabricCanvas.remove(obj));
    state.tempPolygonLines = [];
    state.tempPolygonDots = [];

    state.isDrawingPolygon = false;
    state.polygonPoints = [];

    state.fabricCanvas.renderAll();
    updateStatus('Polygon cancelled');
}

// ============================================================================
// CANVAS EVENTS
// ============================================================================

function setupCanvasEvents() {
    // Initial setup - will be called once during init
    setupCanvasEventsInternal();
}

function setupCanvasEventsInternal() {
    // Called each time the fabric canvas is recreated
    const canvas = state.fabricCanvas;
    if (!canvas) return;

    // Mouse down
    canvas.on('mouse:down', (e) => {
        if (state.currentTool === 'polygon' && !e.target) {
            startPolygonDrawing(e);
        }
    });

    // Double-click to finish polygon
    canvas.on('mouse:dblclick', () => {
        if (state.isDrawingPolygon) {
            finishPolygon();
        }
    });

    // Mouse move for coordinates
    canvas.on('mouse:move', (e) => {
        const pointer = canvas.getPointer(e.e);
        const pdfX = (pointer.x / state.scale).toFixed(1);
        const pdfY = (state.pageHeight - pointer.y / state.scale).toFixed(1);
        document.getElementById('coords-info').textContent = `X: ${pdfX}, Y: ${pdfY}`;
    });

    // Object selection
    canvas.on('selection:created', (e) => {
        const obj = e.selected[0];
        if (obj.annotationId) {
            selectAnnotation(obj.annotationId);
        }
    });

    canvas.on('selection:cleared', () => {
        state.selectedAnnotation = null;
        document.querySelectorAll('.annotation-item').forEach(el => {
            el.classList.remove('selected');
        });
    });
}

function selectAnnotation(annotationId) {
    state.selectedAnnotation = annotationId;

    // Update list selection
    document.querySelectorAll('.annotation-item').forEach(el => {
        el.classList.toggle('selected', el.dataset.id === annotationId);
    });

    // Find annotation and update classification panel
    const ann = state.annotations.find(a => a.id === annotationId);
    if (ann?.classification) {
        setCategory(ann.classification.category);
        document.getElementById('type-label').value = ann.classification.typeLabel || '';
        state.currentTypeLabel = ann.classification.typeLabel || 'A';
    }
}

// ============================================================================
// PAN/ZOOM
// ============================================================================

function setupPanZoom() {
    const viewerArea = document.getElementById('viewer-area');

    // Zoom with scroll wheel
    viewerArea.addEventListener('wheel', (e) => {
        if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            const delta = e.deltaY > 0 ? -0.1 : 0.1;
            setZoom(state.scale + delta);
        }
    }, { passive: false });

    // Pan with space+drag
    let isPanning = false;
    let panStart = { x: 0, y: 0 };
    let scrollStart = { x: 0, y: 0 };

    document.addEventListener('keydown', (e) => {
        if (e.code === 'Space' && !e.repeat) {
            viewerArea.style.cursor = 'grab';
        }
    });

    document.addEventListener('keyup', (e) => {
        if (e.code === 'Space') {
            viewerArea.style.cursor = '';
            isPanning = false;
        }
    });

    viewerArea.addEventListener('mousedown', (e) => {
        if (e.buttons === 1 && (e.target === viewerArea || state.currentTool === 'pan')) {
            isPanning = true;
            panStart = { x: e.clientX, y: e.clientY };
            scrollStart = { x: viewerArea.scrollLeft, y: viewerArea.scrollTop };
            viewerArea.style.cursor = 'grabbing';
        }
    });

    document.addEventListener('mousemove', (e) => {
        if (isPanning) {
            viewerArea.scrollLeft = scrollStart.x - (e.clientX - panStart.x);
            viewerArea.scrollTop = scrollStart.y - (e.clientY - panStart.y);
        }
    });

    document.addEventListener('mouseup', () => {
        isPanning = false;
        viewerArea.style.cursor = '';
    });
}

function setZoom(newScale) {
    const oldScale = state.scale;
    state.scale = Math.max(0.25, Math.min(5.0, newScale));

    // Skip if no actual change
    if (state.scale === oldScale) return;

    // Re-render at new zoom level
    renderPage(state.currentPage);
}

// ============================================================================
// TOOLBAR
// ============================================================================

function setupToolbar() {
    // Zoom controls
    document.getElementById('zoom-in').addEventListener('click', () => setZoom(state.scale + 0.25));
    document.getElementById('zoom-out').addEventListener('click', () => setZoom(state.scale - 0.25));
    document.getElementById('zoom-fit').addEventListener('click', fitToWidth);

    // Tool selection
    document.getElementById('tool-pan').addEventListener('click', () => setTool('pan'));
    document.getElementById('tool-polygon').addEventListener('click', () => setTool('polygon'));

    // Actions
    document.getElementById('btn-undo').addEventListener('click', undo);
    document.getElementById('btn-save').addEventListener('click', () => updateStatus('All changes auto-saved'));
}

function setTool(tool) {
    state.currentTool = tool;

    // Update button states
    document.querySelectorAll('.toolbar-group .tool-btn').forEach(btn => {
        if (btn.id === `tool-${tool}`) {
            btn.classList.add('active');
        } else if (btn.id.startsWith('tool-')) {
            btn.classList.remove('active');
        }
    });

    // Cancel any in-progress drawing
    if (state.isDrawingPolygon && tool !== 'polygon') {
        cancelPolygon();
    }

    // Update canvas selection mode
    state.fabricCanvas.selection = (tool === 'pan');

    updateStatus(`Tool: ${tool.charAt(0).toUpperCase() + tool.slice(1)}`);
}

function fitToWidth() {
    const viewerArea = document.getElementById('viewer-area');
    const containerWidth = viewerArea.clientWidth - 40; // padding
    state.scale = containerWidth / state.pageWidth;
    renderPage(state.currentPage);
}

// ============================================================================
// CLASSIFICATION
// ============================================================================

function setupClassification() {
    // Category buttons
    document.querySelectorAll('.class-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            setCategory(btn.dataset.category);
        });
    });

    // Type label input
    const typeLabelInput = document.getElementById('type-label');
    typeLabelInput.addEventListener('input', () => {
        state.currentTypeLabel = typeLabelInput.value.toUpperCase() || 'A';

        // Update selected annotation if any
        if (state.selectedAnnotation) {
            updateSelectedAnnotationClassification();
        }
    });
}

function setCategory(category) {
    state.currentCategory = category;

    // Update button states
    document.querySelectorAll('.class-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.category === category);
    });

    // Update selected annotation if any
    if (state.selectedAnnotation) {
        updateSelectedAnnotationClassification();
    }
}

async function updateSelectedAnnotationClassification() {
    if (!state.selectedAnnotation) return;

    const ann = state.annotations.find(a => a.id === state.selectedAnnotation);
    if (!ann) return;

    ann.classification = {
        category: state.currentCategory,
        typeLabel: state.currentTypeLabel
    };

    await saveAnnotation(ann);
    redrawAnnotations();
}

// ============================================================================
// ZONE MODE
// ============================================================================

function setupZoneMode() {
    // Mode toggle buttons (if they exist in the DOM)
    const modeTagBtn = document.getElementById('mode-tag');
    const modeZoneBtn = document.getElementById('mode-zone');

    if (modeTagBtn) {
        modeTagBtn.addEventListener('click', () => setMode('tag'));
    }
    if (modeZoneBtn) {
        modeZoneBtn.addEventListener('click', () => setMode('zone'));
    }

    // Zone type buttons
    document.querySelectorAll('.zone-type-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            setZoneType(btn.dataset.zoneType);
        });
    });

    // Direction buttons
    document.querySelectorAll('.direction-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            setZoneDirection(btn.dataset.direction);
        });
    });

    // Detail zone inputs
    const detailIdInput = document.getElementById('detail-id');
    const detailTitleInput = document.getElementById('detail-title');
    const detailAppliesToInput = document.getElementById('detail-applies-to');

    if (detailIdInput) {
        detailIdInput.addEventListener('input', () => {
            state.currentDetailId = detailIdInput.value.toUpperCase();
        });
    }
    if (detailTitleInput) {
        detailTitleInput.addEventListener('input', () => {
            state.currentDetailTitle = detailTitleInput.value;
        });
    }
    if (detailAppliesToInput) {
        detailAppliesToInput.addEventListener('input', () => {
            // Parse comma-separated types
            state.currentDetailAppliesTo = detailAppliesToInput.value
                .split(',')
                .map(s => s.trim().toUpperCase())
                .filter(s => s.length > 0);
        });
    }

    // Zone label input
    const zoneLabelInput = document.getElementById('zone-label');
    if (zoneLabelInput) {
        zoneLabelInput.addEventListener('input', () => {
            state.currentZoneLabel = zoneLabelInput.value;
        });
    }
}

function setMode(mode) {
    state.currentMode = mode;

    // Update mode toggle buttons
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.id === `mode-${mode}`);
    });

    // Show/hide the appropriate panels
    const tagPanel = document.getElementById('tag-panel');
    const zonePanel = document.getElementById('zone-panel');

    if (tagPanel) tagPanel.classList.toggle('hidden', mode !== 'tag');
    if (zonePanel) zonePanel.classList.toggle('hidden', mode !== 'zone');

    // Cancel any in-progress drawing
    if (state.isDrawingPolygon) {
        cancelPolygon();
    }

    updateStatus(`Mode: ${mode === 'zone' ? 'Zone' : 'Tag'}`);
}

function setZoneType(zoneType) {
    state.currentZoneType = zoneType;

    // Update zone type buttons
    document.querySelectorAll('.zone-type-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.zoneType === zoneType);
    });

    // Show/hide zone-specific options
    const elevationOptions = document.getElementById('elevation-options');
    const floorPlanOptions = document.getElementById('floor-plan-options');
    const detailOptions = document.getElementById('detail-options');
    const scheduleOptions = document.getElementById('schedule-options');

    if (elevationOptions) elevationOptions.classList.toggle('hidden', zoneType !== 'elevation_zone');
    if (floorPlanOptions) floorPlanOptions.classList.toggle('hidden', zoneType !== 'floor_plan_zone');
    if (detailOptions) detailOptions.classList.toggle('hidden', zoneType !== 'detail_zone');
    if (scheduleOptions) scheduleOptions.classList.toggle('hidden', zoneType !== 'schedule_zone');

    updateStatus(`Zone type: ${zoneType.replace('_', ' ')}`);
}

function setZoneDirection(direction) {
    state.currentZoneDirection = direction;

    // Update direction buttons
    document.querySelectorAll('.direction-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.direction === direction);
    });

    // Update the visual indicator
    updateDirectionIndicator();

    updateStatus(`Direction: ${direction}`);
}

function updateDirectionIndicator() {
    // Update the compass indicator if it exists
    const compassIndicator = document.getElementById('compass-indicator');
    if (compassIndicator) {
        const color = DIRECTION_COLORS[state.currentZoneDirection] || DIRECTION_COLORS.north;
        compassIndicator.style.borderColor = color;
    }
}

// Expose zone functions to global scope
window.setMode = setMode;
window.setZoneType = setZoneType;
window.setZoneDirection = setZoneDirection;

// ============================================================================
// KEYBOARD SHORTCUTS
// ============================================================================

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Don't handle shortcuts when typing in inputs
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        const key = e.key.toLowerCase();

        // Zone mode toggle - Z key
        if (key === 'z' && !e.ctrlKey && !e.metaKey) {
            setMode(state.currentMode === 'zone' ? 'tag' : 'zone');
            return;
        }

        // Mode-specific shortcuts
        if (state.currentMode === 'zone') {
            // Direction shortcuts in zone mode
            switch (key) {
                case 'n':
                    setZoneDirection('north');
                    return;
                case 's':
                    setZoneDirection('south');
                    return;
                case 'e':
                    setZoneDirection('east');
                    return;
                case 'w':
                    setZoneDirection('west');
                    return;
            }
        } else {
            // Tag mode classification shortcuts
            switch (key) {
                case 'w':
                    setCategory('window');
                    return;
                case 'd':
                    setCategory('door');
                    return;
                case 's':
                    setCategory('storefront');
                    return;
                case 'c':
                    setCategory('curtainwall');
                    return;
            }
        }

        // Common shortcuts (work in both modes)
        switch (key) {
            case 'p':
                setTool('polygon');
                break;
            case 'escape':
                if (state.isDrawingPolygon) {
                    cancelPolygon();
                }
                break;
            case 'delete':
            case 'backspace':
                if (state.selectedAnnotation) {
                    deleteAnnotation(state.selectedAnnotation);
                }
                break;
        }

        // Type label shortcuts (1-9 = A-I) - only in tag mode
        if (state.currentMode === 'tag' && /^[1-9]$/.test(e.key)) {
            const label = String.fromCharCode(64 + parseInt(e.key)); // 1=A, 2=B, etc.
            document.getElementById('type-label').value = label;
            state.currentTypeLabel = label;
            if (state.selectedAnnotation) {
                updateSelectedAnnotationClassification();
            }
        }

        // Ctrl+Z for undo
        if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
            e.preventDefault();
            undo();
        }

        // Page navigation
        if (e.key === '[' || e.key === 'ArrowLeft') {
            if (state.currentPage > 1) {
                renderPage(state.currentPage - 1);
            }
        }
        if (e.key === ']' || e.key === 'ArrowRight') {
            if (state.currentPage < state.totalPages) {
                renderPage(state.currentPage + 1);
            }
        }
    });
}

// ============================================================================
// UI UPDATES
// ============================================================================

function updateAnnotationList() {
    const container = document.getElementById('annotation-list');
    const pageAnnotations = state.annotations.filter(a => a.page_number === state.currentPage);

    document.getElementById('annotation-count').textContent = state.annotations.length;

    if (pageAnnotations.length === 0) {
        container.innerHTML = '<div class="empty-state">No annotations on this page</div>';
        return;
    }

    container.innerHTML = pageAnnotations.map(ann => {
        const cat = ann.classification?.category || 'window';
        const label = ann.classification?.typeLabel || '?';
        const color = COLORS[cat]?.stroke || COLORS.window.stroke;

        return `
            <div class="annotation-item ${ann.id === state.selectedAnnotation ? 'selected' : ''}"
                 data-id="${ann.id}"
                 style="border-color: ${color}"
                 onclick="selectAnnotation('${ann.id}')">
                <div class="color-dot" style="background: ${color}"></div>
                <span class="label">${cat}: ${label}</span>
                <button class="delete-btn" onclick="event.stopPropagation(); deleteAnnotation('${ann.id}')" title="Delete">x</button>
            </div>
        `;
    }).join('');
}

function updateTagSummary() {
    const container = document.getElementById('tag-summary');

    // Count by category
    const counts = { window: 0, door: 0, storefront: 0, curtainwall: 0 };
    state.annotations.forEach(ann => {
        const cat = ann.classification?.category;
        if (cat && counts[cat] !== undefined) {
            counts[cat]++;
        }
    });

    container.innerHTML = Object.entries(counts)
        .filter(([_, count]) => count > 0)
        .map(([cat, count]) => `<span class="tag-chip ${cat}">${cat}: ${count}</span>`)
        .join('');
}

function updateStatus(message) {
    document.getElementById('status-text').textContent = message;
}

function showLoading(show) {
    document.getElementById('loading-overlay').classList.toggle('hidden', !show);
}

// ============================================================================
// UNDO
// ============================================================================

function undo() {
    // Simple undo - delete most recent annotation
    if (state.annotations.length > 0) {
        const lastAnn = state.annotations[state.annotations.length - 1];
        deleteAnnotation(lastAnn.id);
        updateStatus('Undo: Deleted last annotation');
    }
}

// ============================================================================
// AUTO-DETECT SHAPES
// ============================================================================

// Detected tags state
const detectState = {
    tags: [],
    selectedTags: new Set(),
    previewObjects: []
};

function setupDetection() {
    const detectBtn = document.getElementById('btn-detect');
    const addSelectedBtn = document.getElementById('btn-add-selected');
    const addAllBtn = document.getElementById('btn-add-all');
    const clearBtn = document.getElementById('btn-clear-detect');

    detectBtn.addEventListener('click', runDetection);
    addSelectedBtn.addEventListener('click', addSelectedTags);
    addAllBtn.addEventListener('click', addAllTags);
    clearBtn.addEventListener('click', clearDetection);
}

async function runDetection() {
    if (!state.currentPdfPath) {
        updateStatus('Load a PDF first');
        return;
    }

    const shapeType = document.getElementById('shape-select').value;
    const detectBtn = document.getElementById('btn-detect');

    detectBtn.disabled = true;
    detectBtn.textContent = 'Scanning...';
    updateStatus(`Detecting ${shapeType} shapes...`);

    try {
        const response = await fetch(`/api/project/${window.APP_CONFIG.projectId}/detect-shapes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pdf_path: state.currentPdfPath,
                page_number: state.currentPage,
                shape_type: shapeType,
                min_confidence: 0.5
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Detection failed');
        }

        detectState.tags = data.tags || [];
        detectState.selectedTags = new Set(detectState.tags.map((_, i) => i));

        displayDetectionResults();
        drawDetectionPreviews();

        updateStatus(`Found ${detectState.tags.length} ${shapeType} tags`);

    } catch (error) {
        console.error('Detection error:', error);
        updateStatus(`Detection failed: ${error.message}`);
    } finally {
        detectBtn.disabled = false;
        detectBtn.textContent = 'Scan Page';
    }
}

function displayDetectionResults() {
    const container = document.getElementById('detect-results');
    const actions = document.getElementById('detect-actions');

    if (detectState.tags.length === 0) {
        container.innerHTML = '<div class="empty-state">No tags found on this page</div>';
        actions.classList.add('hidden');
        return;
    }

    // Summary
    const labels = detectState.tags.map(t => t.label).filter(l => l);
    const uniqueLabels = [...new Set(labels)];

    container.innerHTML = `
        <div class="detect-summary">
            Found <strong>${detectState.tags.length}</strong> tags:
            ${uniqueLabels.length > 0 ? uniqueLabels.join(', ') : '(no labels)'}
        </div>
        ${detectState.tags.map((tag, idx) => `
            <div class="detect-item ${detectState.selectedTags.has(idx) ? 'selected' : ''}"
                 data-idx="${idx}"
                 onclick="toggleDetectedTag(${idx})">
                <input type="checkbox" ${detectState.selectedTags.has(idx) ? 'checked' : ''}
                       onclick="event.stopPropagation(); toggleDetectedTag(${idx})">
                <span class="label">${tag.label || '?'}</span>
                <span class="coords">(${Math.round(tag.pdf_x)}, ${Math.round(tag.pdf_y)})</span>
                <span class="confidence">${Math.round(tag.confidence * 100)}%</span>
            </div>
        `).join('')}
    `;

    actions.classList.remove('hidden');
}

function toggleDetectedTag(idx) {
    if (detectState.selectedTags.has(idx)) {
        detectState.selectedTags.delete(idx);
    } else {
        detectState.selectedTags.add(idx);
    }
    displayDetectionResults();
    drawDetectionPreviews();
}

function drawDetectionPreviews() {
    // Clear existing previews
    detectState.previewObjects.forEach(obj => state.fabricCanvas.remove(obj));
    detectState.previewObjects = [];

    // Draw preview rectangles for detected tags
    detectState.tags.forEach((tag, idx) => {
        const isSelected = detectState.selectedTags.has(idx);

        // Convert PDF coords to canvas coords
        const x = tag.pdf_x * state.scale;
        const y = tag.pdf_y * state.scale;
        const w = tag.width * state.scale;
        const h = tag.height * state.scale;

        const rect = new fabric.Rect({
            left: x,
            top: y,
            width: w,
            height: h,
            fill: isSelected ? 'rgba(233, 69, 96, 0.3)' : 'rgba(255, 255, 255, 0.2)',
            stroke: isSelected ? '#e94560' : '#888',
            strokeWidth: 2,
            strokeDashArray: [5, 5],
            selectable: false,
            evented: false
        });

        // Add label
        const label = new fabric.Text(tag.label || '?', {
            left: x + w / 2,
            top: y + h / 2,
            fontSize: 12,
            fontWeight: 'bold',
            fill: isSelected ? '#e94560' : '#888',
            originX: 'center',
            originY: 'center',
            selectable: false,
            evented: false
        });

        detectState.previewObjects.push(rect, label);
        state.fabricCanvas.add(rect, label);
    });

    state.fabricCanvas.renderAll();
}

async function addSelectedTags() {
    const selectedTags = detectState.tags.filter((_, idx) => detectState.selectedTags.has(idx));

    if (selectedTags.length === 0) {
        updateStatus('No tags selected');
        return;
    }

    await addTagsAsAnnotations(selectedTags);
}

async function addAllTags() {
    if (detectState.tags.length === 0) {
        updateStatus('No tags to add');
        return;
    }

    await addTagsAsAnnotations(detectState.tags);
}

async function addTagsAsAnnotations(tags) {
    updateStatus(`Adding ${tags.length} annotations...`);

    try {
        // Prepare tags with category from current selection
        const tagsWithCategory = tags.map(tag => ({
            ...tag,
            category: state.currentCategory
        }));

        const response = await fetch(`/api/project/${window.APP_CONFIG.projectId}/annotations/bulk`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pdf_path: state.currentPdfPath,
                page_number: state.currentPage,
                tags: tagsWithCategory
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to add annotations');
        }

        // Reload annotations
        await loadAnnotations();
        clearDetection();

        updateStatus(`Added ${data.created} annotations`);

    } catch (error) {
        console.error('Error adding annotations:', error);
        updateStatus(`Error: ${error.message}`);
    }
}

function clearDetection() {
    detectState.tags = [];
    detectState.selectedTags.clear();

    // Clear preview objects
    detectState.previewObjects.forEach(obj => state.fabricCanvas.remove(obj));
    detectState.previewObjects = [];
    state.fabricCanvas.renderAll();

    // Clear UI
    document.getElementById('detect-results').innerHTML = '';
    document.getElementById('detect-actions').classList.add('hidden');
}

// Expose to global scope
window.toggleDetectedTag = toggleDetectedTag;

// ============================================================================
// EXPOSE FUNCTIONS TO GLOBAL SCOPE
// ============================================================================

window.selectAnnotation = selectAnnotation;
window.deleteAnnotation = deleteAnnotation;

// ============================================================================
// START
// ============================================================================

init();
