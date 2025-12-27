// Project Tracker Dashboard JavaScript

let currentProjectId = null;
let currentProjectStatus = null;
let currentView = 'grid';

/**
 * Format date to mm/dd/yy
 */
function formatDate(dateStr) {
    if (!dateStr || dateStr === 'None' || dateStr === '') return '';

    let d;
    // Try parsing as ISO date (YYYY-MM-DD)
    if (dateStr.match(/^\d{4}-\d{2}-\d{2}/)) {
        const parts = dateStr.split('-');
        d = new Date(parts[0], parts[1] - 1, parts[2]);
    }
    // Try MM/DD/YYYY format
    else if (dateStr.includes('/')) {
        const parts = dateStr.split('/');
        if (parts.length === 3) {
            // Check if year is already 2 digits
            if (parts[2].length === 2) return dateStr.replace(/(\d{2})\/(\d{2})\/(\d{2})/, '$1/$2/$3');
            d = new Date(parts[2], parts[0] - 1, parts[1]);
        }
    } else {
        d = new Date(dateStr);
    }

    if (!d || isNaN(d.getTime())) return dateStr;

    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const year = String(d.getFullYear()).slice(-2);
    return `${month}/${day}/${year}`;
}

/**
 * Set view mode (grid or list)
 */
function setView(view) {
    currentView = view;
    const grid = document.getElementById('projectGrid');
    const gridBtn = document.getElementById('gridViewBtn');
    const listBtn = document.getElementById('listViewBtn');

    if (view === 'list') {
        grid.classList.add('list-view');
        grid.classList.remove('grid-view');
        gridBtn.classList.remove('active');
        listBtn.classList.add('active');
    } else {
        grid.classList.remove('list-view');
        grid.classList.add('grid-view');
        gridBtn.classList.add('active');
        listBtn.classList.remove('active');
    }

    // Save preference
    localStorage.setItem('projectView', view);
}

/**
 * Sort projects based on selected criteria
 */
function sortProjects() {
    const sortBy = document.getElementById('sortBy').value;
    const grid = document.getElementById('projectGrid');
    if (!grid) return;

    const cards = Array.from(grid.querySelectorAll('.project-card'));

    cards.sort((a, b) => {
        let valA, valB;

        switch (sortBy) {
            case 'bid_date_asc':
            case 'bid_date_desc':
                valA = parseDateValue(a.dataset.bidDate);
                valB = parseDateValue(b.dataset.bidDate);
                // Put empty dates at the end
                if (!valA && valB) return 1;
                if (valA && !valB) return -1;
                if (!valA && !valB) return 0;
                return sortBy === 'bid_date_asc' ? valA - valB : valB - valA;

            case 'updated_desc':
                valA = parseDateValue(a.dataset.dateUpdated) || parseDateValue(a.dataset.dateAdded) || 0;
                valB = parseDateValue(b.dataset.dateUpdated) || parseDateValue(b.dataset.dateAdded) || 0;
                return valB - valA;

            case 'added_desc':
                valA = parseDateValue(a.dataset.dateAdded) || 0;
                valB = parseDateValue(b.dataset.dateAdded) || 0;
                return valB - valA;

            case 'added_asc':
                valA = parseDateValue(a.dataset.dateAdded) || Infinity;
                valB = parseDateValue(b.dataset.dateAdded) || Infinity;
                return valA - valB;

            case 'title_asc':
                valA = (a.dataset.title || '').toLowerCase();
                valB = (b.dataset.title || '').toLowerCase();
                return valA.localeCompare(valB);

            case 'title_desc':
                valA = (a.dataset.title || '').toLowerCase();
                valB = (b.dataset.title || '').toLowerCase();
                return valB.localeCompare(valA);

            default:
                return 0;
        }
    });

    // Reorder cards in DOM
    cards.forEach(card => grid.appendChild(card));
}

/**
 * Parse various date formats into timestamp for sorting
 */
function parseDateValue(dateStr) {
    if (!dateStr || dateStr === 'None' || dateStr === '') return null;

    // Try parsing as ISO date or common formats
    const parsed = Date.parse(dateStr);
    if (!isNaN(parsed)) return parsed;

    // Try MM/DD/YYYY format
    const parts = dateStr.split('/');
    if (parts.length === 3) {
        const d = new Date(parts[2], parts[0] - 1, parts[1]);
        if (!isNaN(d.getTime())) return d.getTime();
    }

    // Try YYYY-MM-DD format
    const isoParts = dateStr.split('-');
    if (isoParts.length === 3) {
        const d = new Date(isoParts[0], isoParts[1] - 1, isoParts[2]);
        if (!isNaN(d.getTime())) return d.getTime();
    }

    return null;
}

/**
 * Filter projects based on current filter selections
 */
function filterProjects() {
    const sourceFilter = document.getElementById('sourceFilter').value;
    const typeFilter = document.getElementById('typeFilter').value;
    const searchFilter = document.getElementById('searchFilter').value.toLowerCase();
    const stateFilter = document.getElementById('stateFilter').value;
    const statusFilter = document.getElementById('statusFilter').value;
    const gcFilterEl = document.getElementById('gcFilter');
    const gcFilter = gcFilterEl ? gcFilterEl.value : 'all';
    const archivedFilterEl = document.getElementById('archivedFilter');
    const archivedFilter = archivedFilterEl ? archivedFilterEl.value : 'active';

    // Hide/show DCAM and RFQ sections based on source filter
    // These are ProjectDog-only sections, so hide them when filtering to other sources
    const dcamSection = document.getElementById('dcamGrid')?.closest('.section');
    const rfqSection = document.getElementById('rfqGrid')?.closest('.section');
    const upcomingSection = document.getElementById('upcomingGrid')?.closest('.section');

    if (sourceFilter && sourceFilter !== 'all' && sourceFilter !== 'projectdog') {
        // Hide DCAM/RFQ/Upcoming when filtering to non-projectdog source
        if (dcamSection) dcamSection.style.display = 'none';
        if (rfqSection) rfqSection.style.display = 'none';
        if (upcomingSection) upcomingSection.style.display = 'none';
    } else {
        // Show sections (let their original display handle visibility)
        if (dcamSection) dcamSection.style.display = '';
        if (rfqSection) rfqSection.style.display = '';
        if (upcomingSection) upcomingSection.style.display = '';
    }

    const cards = document.querySelectorAll('#projectGrid .project-card');
    let visibleCount = 0;

    cards.forEach(card => {
        const source = card.dataset.source || '';
        const type = card.dataset.type || '';
        const title = card.dataset.title || '';
        const state = card.dataset.state || '';
        const decision = card.dataset.decision || '';
        const hasEstimate = card.dataset.hasEstimate === 'true';
        const hasProposal = card.dataset.hasProposal === 'true';
        const isArchived = card.dataset.archived === 'true';
        const gc = card.dataset.gc || '';
        const isDirect = card.dataset.direct === 'true';

        let show = true;

        // Archived filter
        if (archivedFilter === 'active' && isArchived) show = false;
        else if (archivedFilter === 'archived' && !isArchived) show = false;

        // Source filter
        if (sourceFilter !== 'all') {
            if (sourceFilter === 'local' && (source === 'projectdog' || source === 'planhub')) show = false;
            else if (sourceFilter === 'projectdog' && source !== 'projectdog') show = false;
            else if (sourceFilter === 'planhub' && source !== 'planhub') show = false;
        }

        // Type filter
        if (show && typeFilter !== 'all') {
            if (type !== typeFilter) show = false;
        }

        // Search filter
        if (show && searchFilter && !title.includes(searchFilter)) {
            show = false;
        }

        // State filter
        if (show && stateFilter !== 'all' && state !== stateFilter) {
            show = false;
        }

        // Status filter
        if (show && statusFilter !== 'all') {
            if (statusFilter === 'bid' && decision !== 'bid') show = false;
            else if (statusFilter === 'no_bid' && decision !== 'no_bid') show = false;
            else if (statusFilter === 'pending' && decision && decision !== 'pending') show = false;
            else if (statusFilter === 'has_estimate' && !hasEstimate) show = false;
            else if (statusFilter === 'has_proposal' && !hasProposal) show = false;
        }

        // GC/Contractor filter
        if (show && gcFilter !== 'all') {
            if (gcFilter === 'direct') {
                // Show only direct email projects
                if (!isDirect) show = false;
            } else {
                // Filter by specific GC company (gc may contain comma-separated list)
                const gcList = gc.split(',').map(g => g.trim());
                if (!gcList.includes(gcFilter)) show = false;
            }
        }

        // Scope filter (CSI tags)
        const scopeFilterEl = document.getElementById('scopeFilter');
        const scopeFilter = scopeFilterEl ? scopeFilterEl.value : 'all';
        if (show && scopeFilter !== 'all') {
            const cardScope = card.dataset.scope || '';
            if (!cardScope.split(',').includes(scopeFilter)) {
                show = false;
            }
        }

        // Project Type filter (PlanHub tags like Sub Bidding, Commercial, etc.)
        const projectTypeFilterEl = document.getElementById('projectTypeFilter');
        const projectTypeFilter = projectTypeFilterEl ? projectTypeFilterEl.value : 'all';
        if (show && projectTypeFilter !== 'all') {
            const cardTags = card.dataset.tags || '';
            const tagList = cardTags.split(',').map(t => t.trim().toLowerCase());
            const filterTag = projectTypeFilter.replace(/-/g, ' ');  // Replace all hyphens
            if (!tagList.some(t => t.includes(filterTag))) {
                show = false;
            }
        }

        // Files filter (has local folder or not)
        const filesFilterEl = document.getElementById('filesFilter');
        const filesFilter = filesFilterEl ? filesFilterEl.value : 'all';
        if (show && filesFilter !== 'all') {
            const hasFolder = card.dataset.hasFolder === 'true';
            if (filesFilter === 'has_folder' && !hasFolder) {
                show = false;
            } else if (filesFilter === 'no_folder' && hasFolder) {
                show = false;
            }
        }

        card.classList.toggle('hidden', !show);
        if (show) visibleCount++;
    });

    // Update count display
    const countSpan = document.querySelector('.section-title .count');
    if (countSpan) {
        countSpan.textContent = `(${visibleCount})`;
    }

    // Also filter Won Projects section
    const wonCards = document.querySelectorAll('#wonGrid .project-card');
    let wonVisibleCount = 0;

    wonCards.forEach(card => {
        const source = card.dataset.source || '';
        const type = card.dataset.type || '';
        const title = card.dataset.title || '';
        const state = card.dataset.state || '';
        const gc = card.dataset.gc || '';
        const isDirect = card.dataset.direct === 'true';

        let show = true;

        // Source filter
        if (sourceFilter !== 'all') {
            if (sourceFilter === 'local' && (source === 'projectdog' || source === 'planhub')) show = false;
            else if (sourceFilter === 'projectdog' && source !== 'projectdog') show = false;
            else if (sourceFilter === 'planhub' && source !== 'planhub') show = false;
            else if (sourceFilter === 'email_monitor' && source !== 'email_monitor') show = false;
        }

        // Type filter
        if (show && typeFilter !== 'all' && type !== typeFilter) show = false;

        // Search filter
        if (show && searchFilter && !title.includes(searchFilter)) show = false;

        // State filter
        if (show && stateFilter !== 'all' && state !== stateFilter) show = false;

        // GC/Contractor filter
        if (show && gcFilter !== 'all') {
            if (gcFilter === 'direct') {
                if (!isDirect) show = false;
            } else {
                const gcList = gc.split(',').map(g => g.trim());
                if (!gcList.includes(gcFilter)) show = false;
            }
        }

        card.classList.toggle('hidden', !show);
        if (show) wonVisibleCount++;
    });

    // Hide Won section if no visible cards
    const wonSection = document.getElementById('wonSection');
    if (wonSection) {
        wonSection.style.display = wonVisibleCount > 0 ? '' : 'none';
    }
    const wonCount = document.getElementById('wonCount');
    if (wonCount) {
        wonCount.textContent = `(${wonVisibleCount})`;
    }
}

/**
 * Refresh local project data
 */
async function refreshProjects() {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = 'Refreshing...';

    try {
        const response = await fetch('/api/refresh', { method: 'POST' });
        const data = await response.json();

        if (data.status === 'ok') {
            location.reload();
        } else {
            alert('Refresh failed: ' + (data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Refresh error:', error);
        alert('Failed to refresh projects');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Refresh Local';
    }
}

/**
 * Trigger ProjectDog sync
 */
async function triggerSync() {
    const btn = event.target;
    btn.disabled = true;

    const indicator = document.getElementById('syncIndicator');

    // Create or show progress display
    let progressDiv = document.getElementById('syncProgressDisplay');
    if (!progressDiv) {
        progressDiv = document.createElement('div');
        progressDiv.id = 'syncProgressDisplay';
        progressDiv.className = 'sync-progress-display';
        progressDiv.innerHTML = `
            <div class="sync-progress-header">
                <strong>ProjectDog Sync</strong>
                <span id="syncStage">Starting...</span>
            </div>
            <div class="sync-progress-bar">
                <div id="syncProgressBar" class="sync-progress-fill" style="width: 0%"></div>
            </div>
            <div id="syncProgressMessage" class="sync-progress-message">Initializing...</div>
        `;
        // Insert after the header
        const header = document.querySelector('.header');
        if (header) {
            header.after(progressDiv);
        } else {
            document.body.prepend(progressDiv);
        }
    }
    progressDiv.style.display = 'block';

    try {
        const response = await fetch('/api/sync/trigger', { method: 'POST' });
        const data = await response.json();

        if (data.status === 'ok') {
            indicator.textContent = 'Syncing...';
            indicator.classList.add('syncing');
            pollSyncStatus();
        } else {
            alert('Sync failed: ' + (data.message || 'Unknown error'));
            progressDiv.style.display = 'none';
        }
    } catch (error) {
        console.error('Sync error:', error);
        alert('Failed to start sync');
        progressDiv.style.display = 'none';
    } finally {
        btn.disabled = false;
    }
}

/**
 * Poll sync status until complete
 */
async function pollSyncStatus() {
    const indicator = document.getElementById('syncIndicator');
    const progressDiv = document.getElementById('syncProgressDisplay');
    const stageEl = document.getElementById('syncStage');
    const barEl = document.getElementById('syncProgressBar');
    const msgEl = document.getElementById('syncProgressMessage');

    const stageNames = {
        'idle': 'Idle',
        'initializing': 'Starting...',
        'login': 'Logging in...',
        'searching': 'Searching...',
        'fetching_details': 'Fetching details...',
        'saving': 'Saving...',
        'refreshing': 'Refreshing...',
        'complete': 'Complete!',
        'error': 'Error'
    };

    const checkStatus = async () => {
        try {
            const response = await fetch('/api/sync/status');
            const status = await response.json();
            const progress = status.progress || {};

            // Update progress display
            if (stageEl) stageEl.textContent = stageNames[progress.stage] || progress.stage;
            if (msgEl) msgEl.textContent = progress.message || '';

            // Calculate progress percentage
            let percent = 0;
            switch (progress.stage) {
                case 'initializing': percent = 5; break;
                case 'login': percent = 10; break;
                case 'searching': percent = 20; break;
                case 'fetching_details':
                    if (progress.total_projects > 0) {
                        percent = 20 + (progress.current_project / progress.total_projects) * 60;
                    } else {
                        percent = 50;
                    }
                    break;
                case 'saving': percent = 85; break;
                case 'refreshing': percent = 95; break;
                case 'complete': percent = 100; break;
                case 'error': percent = 100; break;
            }
            if (barEl) barEl.style.width = percent + '%';

            // Update indicator text with project count
            if (progress.stage === 'fetching_details' && progress.current_project > 0) {
                indicator.textContent = `Syncing ${progress.current_project}/${progress.total_projects}...`;
            } else if (progress.stage === 'searching' && progress.projects_found > 0) {
                indicator.textContent = `Found ${progress.projects_found} projects...`;
            }

            // Check if sync is in progress
            if (status.sync_in_progress) {
                indicator.classList.add('syncing');
                setTimeout(checkStatus, 1000);  // Poll every second for better feedback
            } else {
                // Sync complete or error
                indicator.textContent = 'Idle';
                indicator.classList.remove('syncing');

                if (progress.stage === 'error') {
                    if (msgEl) msgEl.textContent = 'Error: ' + (progress.error || 'Unknown error');
                    if (barEl) barEl.style.background = '#dc3545';
                    setTimeout(() => {
                        if (progressDiv) progressDiv.style.display = 'none';
                    }, 5000);
                } else {
                    // Success - reload page
                    setTimeout(() => {
                        location.reload();
                    }, 1000);
                }
            }
        } catch (error) {
            console.error('Status check error:', error);
            setTimeout(checkStatus, 2000);
        }
    };

    checkStatus();
}

// ==================== STATUS MODAL ====================

/**
 * Show status modal for a project
 */
async function showStatusModal(projectId, projectTitle) {
    currentProjectId = projectId;
    document.getElementById('modalProjectId').value = projectId;
    document.getElementById('modalTitle').textContent = projectTitle || 'Project Status';

    // Reset form
    document.getElementById('bidDecision').value = '';
    document.getElementById('decisionReason').value = '';
    document.getElementById('proposalGenerated').checked = false;
    document.getElementById('proposalSubmitted').checked = false;
    document.getElementById('estimateTotal').value = '';
    document.getElementById('estimateConfidence').value = '';
    document.getElementById('currentTags').innerHTML = '';
    document.getElementById('newNote').value = '';

    // Try to load existing status
    try {
        const response = await fetch(`/api/status/${projectId}`);
        if (response.ok) {
            currentProjectStatus = await response.json();
            populateStatusForm(currentProjectStatus);
        } else {
            currentProjectStatus = null;
        }
    } catch (error) {
        console.error('Error loading status:', error);
        currentProjectStatus = null;
    }

    document.getElementById('statusModal').style.display = 'flex';
}

/**
 * Populate form with existing status
 */
function populateStatusForm(status) {
    if (status.bid_decision) {
        document.getElementById('bidDecision').value = status.bid_decision;
    }
    if (status.bid_decision_reason) {
        document.getElementById('decisionReason').value = status.bid_decision_reason;
    }

    const proposal = status.proposal || {};
    document.getElementById('proposalGenerated').checked = proposal.generated || false;
    document.getElementById('proposalSubmitted').checked = proposal.submitted || false;

    const estimate = status.estimate || {};
    if (estimate.total) {
        document.getElementById('estimateTotal').value = estimate.total;
    }
    if (estimate.confidence) {
        document.getElementById('estimateConfidence').value = estimate.confidence;
    }

    // Display tags
    const tags = status.tags || [];
    const tagsContainer = document.getElementById('currentTags');
    tagsContainer.innerHTML = tags.map(tag =>
        `<span class="status-tag custom">${tag} <button onclick="removeTag('${tag}')">&times;</button></span>`
    ).join('');
}

/**
 * Close modal
 */
function closeModal() {
    document.getElementById('statusModal').style.display = 'none';
    currentProjectId = null;
    currentProjectStatus = null;
}

/**
 * Save status changes
 */
async function saveStatus() {
    if (!currentProjectId) return;

    const decision = document.getElementById('bidDecision').value;
    const reason = document.getElementById('decisionReason').value;
    const errors = [];

    try {
        // Save bid decision
        if (decision) {
            const resp = await fetch(`/api/status/${currentProjectId}/decision`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ decision, reason })
            });
            if (!resp.ok) {
                const data = await resp.json().catch(() => ({}));
                errors.push(`Decision: ${data.error || 'Failed'}`);
            }
        }

        // Save proposal status
        const proposalGenerated = document.getElementById('proposalGenerated').checked;
        const proposalSubmitted = document.getElementById('proposalSubmitted').checked;
        const propResp = await fetch(`/api/status/${currentProjectId}/proposal`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                generated: proposalGenerated,
                submitted: proposalSubmitted
            })
        });
        if (!propResp.ok) {
            const data = await propResp.json().catch(() => ({}));
            errors.push(`Proposal: ${data.error || 'Failed'}`);
        }

        // Save estimate
        const estimateTotal = document.getElementById('estimateTotal').value;
        const estimateConfidence = document.getElementById('estimateConfidence').value;
        if (estimateTotal) {
            const estResp = await fetch(`/api/status/${currentProjectId}/estimate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    total: parseFloat(estimateTotal),
                    confidence: estimateConfidence || null
                })
            });
            if (!estResp.ok) {
                const data = await estResp.json().catch(() => ({}));
                errors.push(`Estimate: ${data.error || 'Failed'}`);
            }
        }

        // Check for errors before reloading
        if (errors.length > 0) {
            alert('Some updates failed:\n' + errors.join('\n'));
            return;
        }

        closeModal();
        // Refresh data before reloading to ensure cache is updated
        await fetch('/api/refresh', { method: 'POST' });
        location.reload();

    } catch (error) {
        console.error('Error saving status:', error);
        alert('Failed to save status: ' + error.message);
    }
}

/**
 * Add a tag
 */
async function addTag() {
    if (!currentProjectId) return;

    const tagInput = document.getElementById('newTag');
    const tag = tagInput.value.trim();

    if (!tag) return;

    try {
        const resp = await fetch(`/api/status/${currentProjectId}/tag`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tag })
        });

        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            alert('Failed to add tag: ' + (data.error || 'Unknown error'));
            return;
        }

        // Update display
        const tagsContainer = document.getElementById('currentTags');
        tagsContainer.innerHTML += `<span class="status-tag custom">${tag} <button onclick="removeTag('${tag}')">&times;</button></span>`;
        tagInput.value = '';

    } catch (error) {
        console.error('Error adding tag:', error);
        alert('Failed to add tag: ' + error.message);
    }
}

/**
 * Remove a tag
 */
async function removeTag(tag) {
    if (!currentProjectId) return;

    try {
        const resp = await fetch(`/api/status/${currentProjectId}/tag`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tag })
        });

        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            alert('Failed to remove tag: ' + (data.error || 'Unknown error'));
            return;
        }

        // Reload modal to update tags
        showStatusModal(currentProjectId, document.getElementById('modalTitle').textContent);

    } catch (error) {
        console.error('Error removing tag:', error);
        alert('Failed to remove tag: ' + error.message);
    }
}

/**
 * Add a note
 */
async function addNote() {
    if (!currentProjectId) return;

    const noteInput = document.getElementById('newNote');
    const note = noteInput.value.trim();

    if (!note) return;

    try {
        const resp = await fetch(`/api/status/${currentProjectId}/note`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note })
        });

        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            alert('Failed to add note: ' + (data.error || 'Unknown error'));
            return;
        }

        noteInput.value = '';
        // Refresh cache and reload to show new note
        await fetch('/api/refresh', { method: 'POST' });
        location.reload();

    } catch (error) {
        console.error('Error adding note:', error);
        alert('Failed to add note: ' + error.message);
    }
}

// ==================== PLANHUB LINK MODAL ====================

let currentLinkPlanhubId = null;
let localProjectsCache = null;

/**
 * Show link modal for a PlanHub project
 */
async function showLinkModal(planhubId, projectTitle) {
    currentLinkPlanhubId = planhubId;
    document.getElementById('linkPlanhubId').value = planhubId;
    document.getElementById('linkProjectName').textContent = `Linking: ${projectTitle}`;

    // Reset form
    document.getElementById('localProjectSelect').innerHTML = '<option value="">-- Loading... --</option>';
    document.getElementById('suggestionsList').innerHTML = '<p style="color: var(--text-muted);">Loading suggestions...</p>';
    document.getElementById('currentLinkSection').style.display = 'none';

    // Show modal
    document.getElementById('linkModal').style.display = 'flex';

    // Load local projects for dropdown
    if (!localProjectsCache) {
        try {
            const resp = await fetch('/api/projects/local');
            const data = await resp.json();
            localProjectsCache = data.projects || [];
        } catch (error) {
            console.error('Error loading local projects:', error);
            localProjectsCache = [];
        }
    }

    // Populate dropdown
    const select = document.getElementById('localProjectSelect');
    select.innerHTML = '<option value="">-- Choose a project --</option>';
    localProjectsCache.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.title || p.folder || p.id;
        select.appendChild(opt);
    });

    // Load suggestions
    try {
        const sugResp = await fetch(`/api/planhub/${planhubId}/suggestions`);
        const sugData = await sugResp.json();

        // Show current link if exists
        if (sugData.current_link) {
            document.getElementById('currentLinkSection').style.display = 'block';
            const linkedProject = localProjectsCache.find(p => p.id === sugData.current_link);
            document.getElementById('currentLinkDisplay').textContent = linkedProject ? (linkedProject.title || linkedProject.folder) : sugData.current_link;
            document.getElementById('localProjectSelect').value = sugData.current_link;
        }

        // Show suggestions
        const suggestionsList = document.getElementById('suggestionsList');
        if (sugData.suggestions && sugData.suggestions.length > 0) {
            suggestionsList.innerHTML = sugData.suggestions.map(s => `
                <div class="suggestion-item" onclick="selectSuggestion('${s.local_id}')">
                    <span class="suggestion-title">${s.local_title || s.local_folder}</span>
                    <span class="suggestion-confidence">${Math.round(s.confidence * 100)}% match</span>
                </div>
            `).join('');
        } else {
            suggestionsList.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">No automatic matches found. Select manually from the dropdown above.</p>';
        }
    } catch (error) {
        console.error('Error loading suggestions:', error);
        document.getElementById('suggestionsList').innerHTML = '<p style="color: var(--text-muted);">Could not load suggestions.</p>';
    }
}

/**
 * Select a suggestion
 */
function selectSuggestion(localId) {
    document.getElementById('localProjectSelect').value = localId;
}

/**
 * Close link modal
 */
function closeLinkModal() {
    document.getElementById('linkModal').style.display = 'none';
    currentLinkPlanhubId = null;
}

/**
 * Save link
 */
async function saveLink() {
    if (!currentLinkPlanhubId) return;

    const localId = document.getElementById('localProjectSelect').value;
    if (!localId) {
        alert('Please select a local project to link.');
        return;
    }

    try {
        const resp = await fetch(`/api/planhub/${currentLinkPlanhubId}/link`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ local_id: localId })
        });

        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            alert('Failed to link: ' + (data.error || 'Unknown error'));
            return;
        }

        closeLinkModal();
        alert('Project linked successfully!');

    } catch (error) {
        console.error('Error saving link:', error);
        alert('Failed to save link: ' + error.message);
    }
}

/**
 * Unlink project
 */
async function unlinkProject() {
    if (!currentLinkPlanhubId) return;

    if (!confirm('Are you sure you want to remove this link?')) return;

    try {
        const resp = await fetch(`/api/planhub/${currentLinkPlanhubId}/link`, {
            method: 'DELETE'
        });

        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            alert('Failed to unlink: ' + (data.error || 'Unknown error'));
            return;
        }

        document.getElementById('currentLinkSection').style.display = 'none';
        document.getElementById('localProjectSelect').value = '';
        alert('Link removed!');

    } catch (error) {
        console.error('Error unlinking:', error);
        alert('Failed to remove link: ' + error.message);
    }
}

// ==================== LAZY LOADING THUMBNAILS ====================

/**
 * Initialize lazy loading for thumbnails
 */
function initThumbnailLazyLoading() {
    const thumbnails = document.querySelectorAll('img[data-src]');

    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    loadThumbnail(img);
                    observer.unobserve(img);
                }
            });
        }, {
            rootMargin: '100px'  // Start loading 100px before visible
        });

        thumbnails.forEach(img => observer.observe(img));
    } else {
        // Fallback: load all thumbnails immediately
        thumbnails.forEach(loadThumbnail);
    }
}

/**
 * Load a single thumbnail
 */
function loadThumbnail(img) {
    const src = img.dataset.src;
    if (!src) return;

    img.classList.add('card-thumbnail-loading');

    // Create a test image to check if thumbnail exists
    const testImg = new Image();
    testImg.onload = () => {
        img.src = src;
        img.classList.remove('card-thumbnail-loading');
    };
    testImg.onerror = () => {
        // Hide the preview card if thumbnail not available
        const previewCard = img.closest('.preview-card');
        if (previewCard) {
            previewCard.style.display = 'none';
            // Also remove padding from card-stack
            const cardStack = previewCard.closest('.card-stack');
            if (cardStack) {
                cardStack.style.paddingTop = '0';
                cardStack.style.paddingLeft = '0';
            }
        } else {
            img.style.display = 'none';
        }
        img.classList.remove('card-thumbnail-loading');
    };
    testImg.src = src;
}

// ==================== CSI SCOPE FILTER ====================

// Tag category mapping (matches backend)
const TAG_CATEGORIES = {
    "Hollow Metal Doors": "doors", "Hollow Metal Frames": "doors",
    "Wood Doors": "doors", "Aluminum Doors": "doors", "FRP Doors": "doors",
    "Access Doors": "doors", "Sliding Glass Doors": "doors", "Coiling Doors": "doors",
    "Storefront": "storefront", "Entrances": "storefront",
    "All-Glass Entrances": "storefront", "Automatic Entrances": "storefront",
    "Curtain Wall": "curtainwall", "Window Wall": "curtainwall",
    "Aluminum Windows": "windows", "Wood Windows": "windows",
    "Vinyl Windows": "windows", "Composite Windows": "windows", "Steel Windows": "windows",
    "Skylights": "skylights", "Unit Skylights": "skylights",
    "Door Hardware": "hardware", "Access Control": "hardware", "Window Hardware": "hardware",
    "Glazing": "glazing", "Glass Glazing": "glazing", "Insulating Glass": "glazing",
    "Laminated Glass": "glazing", "Mirrors": "glazing", "Window Film": "glazing",
    "Blast-Resistant Windows": "specialty", "Bullet-Resistant Windows": "specialty",
    "Ballistic Glazing": "specialty", "Security Windows": "specialty",
    "Louvers": "louvers", "Vents": "louvers",
};

function getTagCategory(tagName) {
    return TAG_CATEGORIES[tagName] || 'other';
}

/**
 * Load scope filter options from API
 */
async function loadScopeFilterOptions() {
    try {
        const response = await fetch('/api/csi/tags/in-use');
        const data = await response.json();

        if (data.status !== 'ok') return;

        const select = document.getElementById('scopeFilter');
        if (!select) return;

        // Clear existing except "All"
        while (select.options.length > 1) {
            select.remove(1);
        }

        // Group by category
        const byCategory = {};
        for (const [tag, count] of Object.entries(data.tags)) {
            const cat = getTagCategory(tag);
            if (!byCategory[cat]) byCategory[cat] = [];
            byCategory[cat].push({ tag, count });
        }

        // Add in order
        const categoryOrder = ['storefront', 'curtainwall', 'windows', 'doors', 'skylights', 'hardware', 'glazing', 'specialty', 'louvers'];
        const categoryLabels = {
            'storefront': '── STOREFRONT ──',
            'curtainwall': '── CURTAIN WALL ──',
            'windows': '── WINDOWS ──',
            'doors': '── DOORS ──',
            'skylights': '── SKYLIGHTS ──',
            'hardware': '── HARDWARE ──',
            'glazing': '── GLAZING ──',
            'specialty': '── SPECIALTY ──',
            'louvers': '── LOUVERS ──',
        };

        for (const cat of categoryOrder) {
            const tags = byCategory[cat];
            if (!tags || tags.length === 0) continue;

            // Category header
            const header = document.createElement('option');
            header.disabled = true;
            header.textContent = categoryLabels[cat] || cat.toUpperCase();
            header.style.fontWeight = 'bold';
            select.appendChild(header);

            // Tags sorted by count descending
            for (const { tag, count } of tags.sort((a, b) => b.count - a.count)) {
                const opt = document.createElement('option');
                opt.value = tag;
                opt.textContent = `${tag} (${count})`;
                select.appendChild(opt);
            }
        }
    } catch (error) {
        console.error('Error loading scope filter:', error);
    }
}


/**
 * Load project type filter options from API
 */
async function loadProjectTypeFilterOptions() {
    try {
        const response = await fetch('/api/project-tags/in-use');
        const data = await response.json();

        if (data.status !== 'ok') return;

        const select = document.getElementById('projectTypeFilter');
        if (!select) return;

        // Clear existing except "All Types"
        while (select.options.length > 1) {
            select.remove(1);
        }

        // Add tags sorted by count (API already sorts)
        for (const [tag, count] of Object.entries(data.tags)) {
            const opt = document.createElement('option');
            opt.value = tag.toLowerCase().replace(/\s+/g, '-');
            opt.textContent = `${tag} (${count})`;
            select.appendChild(opt);
        }
    } catch (error) {
        console.error('Error loading project type filter:', error);
    }
}


// ==================== INITIALIZATION ====================

document.addEventListener('DOMContentLoaded', () => {
    // Initialize lazy loading for thumbnails
    initThumbnailLazyLoading();

    // Load CSI scope filter options
    loadScopeFilterOptions();

    // Load Project Type filter options
    loadProjectTypeFilterOptions();

    // Restore view preference
    const savedView = localStorage.getItem('projectView') || 'grid';
    setView(savedView);

    // Format all dates on page to mm/dd/yy
    document.querySelectorAll('.bid-date').forEach(el => {
        const text = el.textContent;
        const match = text.match(/Bid:\s*(.+)/);
        if (match) {
            el.textContent = 'Bid: ' + formatDate(match[1]);
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + K to focus search
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            document.getElementById('searchFilter').focus();
        }
        // Escape to close modal or clear search
        if (e.key === 'Escape') {
            const statusModal = document.getElementById('statusModal');
            const linkModal = document.getElementById('linkModal');
            if (statusModal.style.display === 'flex') {
                closeModal();
            } else if (linkModal && linkModal.style.display === 'flex') {
                closeLinkModal();
            } else {
                const searchInput = document.getElementById('searchFilter');
                if (document.activeElement === searchInput) {
                    searchInput.value = '';
                    filterProjects();
                    searchInput.blur();
                }
            }
        }
    });

    // Close modal on outside click
    document.getElementById('statusModal').addEventListener('click', (e) => {
        if (e.target.id === 'statusModal') {
            closeModal();
        }
    });

    // Close link modal on outside click
    const linkModal = document.getElementById('linkModal');
    if (linkModal) {
        linkModal.addEventListener('click', (e) => {
            if (e.target.id === 'linkModal') {
                closeLinkModal();
            }
        });
    }

    console.log('Project Tracker Dashboard initialized');
});

// ==================== PROJECTDOG DOCUMENT DOWNLOADS ====================

/**
 * Download documents for a ProjectDog project
 */
async function downloadDocs(projectCode) {
    const btn = event.target;
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Starting...';

    try {
        const response = await fetch(`/api/projectdog/${projectCode}/download`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (response.ok) {
            btn.textContent = 'Downloading...';
            btn.classList.add('downloading');

            // Show notification
            showNotification(`Download started for: ${data.title}`, 'success');

            // Poll for completion (simple approach - just wait and refresh)
            setTimeout(() => {
                location.reload();
            }, 10000);  // Refresh after 10 seconds
        } else {
            throw new Error(data.error || 'Download failed');
        }
    } catch (error) {
        console.error('Download error:', error);
        showNotification(`Download failed: ${error.message}`, 'error');
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

/**
 * Download all pending ProjectDog documents
 */
async function downloadAllDocs() {
    const maxProjects = prompt('How many projects to download? (max 10)', '5');
    if (!maxProjects) return;

    const btn = event.target;
    btn.disabled = true;
    btn.textContent = 'Starting batch...';

    try {
        const response = await fetch('/api/projectdog/download-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ max_projects: parseInt(maxProjects) || 5 })
        });

        const data = await response.json();

        if (response.ok) {
            showNotification(`Batch download started for ${data.projects_count} projects`, 'success');

            // Refresh after some time
            setTimeout(() => {
                location.reload();
            }, 30000);  // Refresh after 30 seconds
        } else {
            throw new Error(data.error || 'Batch download failed');
        }
    } catch (error) {
        console.error('Batch download error:', error);
        showNotification(`Batch download failed: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Download All';
    }
}

/**
 * Show a notification message
 */
function showNotification(message, type = 'info') {
    // Check if notification container exists
    let container = document.getElementById('notificationContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notificationContainer';
        container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10000;';
        document.body.appendChild(container);
    }

    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.style.cssText = `
        background: ${type === 'error' ? '#dc3545' : type === 'success' ? '#28a745' : '#17a2b8'};
        color: white;
        padding: 12px 20px;
        border-radius: 4px;
        margin-bottom: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        animation: slideIn 0.3s ease;
    `;
    notification.textContent = message;

    container.appendChild(notification);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

/**
 * Auto-archive projects with bid dates older than 30 days
 */
async function autoArchiveOld() {
    if (!confirm('This will archive all projects with bid dates older than 30 days. Continue?')) {
        return;
    }

    try {
        const response = await fetch('/api/archive/auto', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ days: 30 })
        });

        const data = await response.json();

        if (response.ok) {
            if (data.archived_count > 0) {
                showNotification(`Archived ${data.archived_count} old projects`, 'success');
                // Refresh after a short delay
                setTimeout(() => location.reload(), 1500);
            } else {
                showNotification('No projects to archive', 'info');
            }
        } else {
            throw new Error(data.error || 'Auto-archive failed');
        }
    } catch (error) {
        console.error('Auto-archive error:', error);
        showNotification(`Auto-archive failed: ${error.message}`, 'error');
    }
}

/**
 * Archive a single project
 */
async function archiveProject(projectId, reason = 'manual') {
    try {
        const response = await fetch(`/api/status/${projectId}/archive`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason })
        });

        if (response.ok) {
            showNotification('Project archived', 'success');
            // Hide the card or reload
            const card = document.querySelector(`[data-id="${projectId}"]`);
            if (card) card.style.display = 'none';
        } else {
            const data = await response.json();
            throw new Error(data.error || 'Archive failed');
        }
    } catch (error) {
        console.error('Archive error:', error);
        showNotification(`Archive failed: ${error.message}`, 'error');
    }
}

/**
 * Unarchive a project
 */
async function unarchiveProject(projectId) {
    try {
        const response = await fetch(`/api/status/${projectId}/unarchive`, {
            method: 'POST'
        });

        if (response.ok) {
            showNotification('Project unarchived', 'success');
            location.reload();
        } else {
            const data = await response.json();
            throw new Error(data.error || 'Unarchive failed');
        }
    } catch (error) {
        console.error('Unarchive error:', error);
        showNotification(`Unarchive failed: ${error.message}`, 'error');
    }
}

// ==================== BATCH CSI SCANNING ====================

let batchScanJobId = null;
let batchScanPollInterval = null;

/**
 * Start batch CSI spec scanning
 */
async function startBatchScan() {
    const force = confirm('Scan all projects?\n\nClick OK to scan ALL projects (including already scanned)\nClick Cancel to only scan projects without CSI tags');

    // Show progress display
    let progressDiv = document.getElementById('batchScanProgress');
    if (!progressDiv) {
        progressDiv = document.createElement('div');
        progressDiv.id = 'batchScanProgress';
        progressDiv.className = 'sync-progress-display';
        progressDiv.innerHTML = `
            <div class="sync-progress-header">
                <strong>Batch Spec Scan</strong>
                <span id="batchScanStage">Starting...</span>
                <button class="close-btn" onclick="closeBatchScanProgress()" style="float:right;background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:1.2rem;">&times;</button>
            </div>
            <div class="sync-progress-bar">
                <div id="batchScanProgressBar" class="sync-progress-fill" style="width: 0%"></div>
            </div>
            <div id="batchScanMessage" class="sync-progress-message">Initializing...</div>
        `;
        const header = document.querySelector('.header');
        if (header) {
            header.after(progressDiv);
        } else {
            document.body.prepend(progressDiv);
        }
    }
    progressDiv.style.display = 'block';
    document.getElementById('batchScanStage').textContent = 'Starting...';
    document.getElementById('batchScanProgressBar').style.width = '0%';
    document.getElementById('batchScanMessage').textContent = 'Initializing...';

    try {
        const response = await fetch('/api/csi/batch-scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force: force })
        });

        const data = await response.json();

        if (data.status === 'ok') {
            batchScanJobId = data.job_id;
            showNotification(`Batch scan started (${data.projects_to_scan} projects)`, 'success');
            pollBatchScanStatus();
        } else {
            throw new Error(data.error || 'Failed to start batch scan');
        }
    } catch (error) {
        console.error('Batch scan error:', error);
        showNotification(`Batch scan failed: ${error.message}`, 'error');
        progressDiv.style.display = 'none';
    }
}

/**
 * Poll batch scan status
 */
async function pollBatchScanStatus() {
    const stageEl = document.getElementById('batchScanStage');
    const barEl = document.getElementById('batchScanProgressBar');
    const msgEl = document.getElementById('batchScanMessage');
    const progressDiv = document.getElementById('batchScanProgress');

    const checkStatus = async () => {
        try {
            const response = await fetch('/api/csi/batch-scan/status');
            const data = await response.json();

            if (data.status !== 'ok') {
                throw new Error(data.error || 'Status check failed');
            }

            const job = data.job;

            // Update UI
            if (stageEl) stageEl.textContent = job.status === 'running' ? 'Scanning...' : job.status;
            if (msgEl) msgEl.textContent = job.current_project || `${job.completed}/${job.total} projects`;

            // Progress bar
            if (job.total > 0) {
                const percent = Math.round((job.current / job.total) * 100);
                if (barEl) barEl.style.width = percent + '%';
            }

            // Check if still running
            if (job.status === 'running') {
                setTimeout(checkStatus, 1000);
            } else if (job.status === 'complete') {
                if (stageEl) stageEl.textContent = 'Complete!';
                if (msgEl) msgEl.textContent = `Scanned ${job.completed} projects (${job.errors.length} errors)`;
                if (barEl) barEl.style.width = '100%';
                showNotification(`Batch scan complete: ${job.completed} projects scanned`, 'success');

                // Reload after short delay to show updated tags
                setTimeout(() => {
                    location.reload();
                }, 2000);
            } else if (job.status === 'error') {
                if (stageEl) stageEl.textContent = 'Error';
                if (barEl) barEl.style.background = '#dc3545';
                showNotification('Batch scan encountered errors', 'error');
            }
        } catch (error) {
            console.error('Status poll error:', error);
            setTimeout(checkStatus, 2000);
        }
    };

    checkStatus();
}

/**
 * Close batch scan progress display
 */
function closeBatchScanProgress() {
    const progressDiv = document.getElementById('batchScanProgress');
    if (progressDiv) {
        progressDiv.style.display = 'none';
    }
}
