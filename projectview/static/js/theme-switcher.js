/**
 * Theme Switcher Module
 * Handles theme persistence, switching, and dark mode toggle
 *
 * Usage:
 *   - Automatic: Include this script, themes are applied on load
 *   - Manual: ThemeSwitcher.applyTheme('fruit')
 *   - Keyboard: Cmd/Ctrl + Shift + T to cycle themes
 */

const ThemeSwitcher = {
  // Configuration
  STORAGE_KEY: 'project-tracker-theme',
  MODE_KEY: 'project-tracker-mode',
  DEFAULT_THEME: 'brutalist',
  THEMES: ['brutalist', 'fruit', 'dialup', 'saas'],

  THEME_NAMES: {
    brutalist: 'Neo Brutalist',
    fruit: 'Fruit',
    dialup: 'Dial-Up',
    saas: 'Modern SaaS'
  },

  /**
   * Initialize theme on page load
   */
  init() {
    // Apply saved theme immediately (before DOM renders)
    const savedTheme = this.getSavedTheme();
    const savedMode = this.getSavedMode();
    this.applyTheme(savedTheme, savedMode, false); // false = don't save again

    // Setup listeners after DOM is ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        this.setupListeners();
        this.updateUI();
      });
    } else {
      this.setupListeners();
      this.updateUI();
    }
  },

  /**
   * Get saved theme from localStorage
   */
  getSavedTheme() {
    try {
      const localTheme = localStorage.getItem(this.STORAGE_KEY);
      if (localTheme && this.THEMES.includes(localTheme)) {
        return localTheme;
      }
    } catch (e) {
      console.warn('localStorage not available:', e);
    }
    return this.DEFAULT_THEME;
  },

  /**
   * Get saved mode (light/dark)
   */
  getSavedMode() {
    try {
      const savedMode = localStorage.getItem(this.MODE_KEY);
      if (savedMode === 'dark' || savedMode === 'light') {
        return savedMode;
      }
      // Check system preference
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark';
      }
    } catch (e) {
      console.warn('Could not get color mode:', e);
    }
    return 'light';
  },

  /**
   * Apply theme to document
   * @param {string} themeName - Theme identifier
   * @param {string} mode - 'light' or 'dark'
   * @param {boolean} save - Whether to persist the change
   */
  applyTheme(themeName, mode = 'light', save = true) {
    // Validate theme
    if (!this.THEMES.includes(themeName)) {
      console.warn(`Invalid theme "${themeName}", using default`);
      themeName = this.DEFAULT_THEME;
    }

    // Set data attributes on html element
    const html = document.documentElement;
    html.setAttribute('data-theme', themeName);
    html.setAttribute('data-mode', mode);

    // Add transition class for smooth switching
    html.classList.add('theme-transitioning');
    setTimeout(() => html.classList.remove('theme-transitioning'), 300);

    // Persist
    if (save) {
      try {
        localStorage.setItem(this.STORAGE_KEY, themeName);
        localStorage.setItem(this.MODE_KEY, mode);
      } catch (e) {
        console.warn('Could not save theme to localStorage:', e);
      }

      // Save to server (async, non-blocking)
      this.saveToServer(themeName, mode);
    }

    // Update UI elements
    this.updateUI();

    // Dispatch event for other components
    window.dispatchEvent(new CustomEvent('themechange', {
      detail: { theme: themeName, mode: mode, themeName: this.THEME_NAMES[themeName] }
    }));

    console.log(`Theme: ${this.THEME_NAMES[themeName]} (${mode} mode)`);
  },

  /**
   * Save theme preference to server
   */
  async saveToServer(themeName, mode) {
    try {
      const response = await fetch('/api/settings/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          theme: themeName,
          dark_mode: mode === 'dark'
        })
      });
      if (!response.ok) {
        console.warn('Server did not accept theme change');
      }
    } catch (e) {
      // Silently fail - localStorage is the primary storage
    }
  },

  /**
   * Setup event listeners
   */
  setupListeners() {
    // Theme selector buttons
    document.addEventListener('click', (e) => {
      // Theme selection
      const themeBtn = e.target.closest('[data-theme-select]');
      if (themeBtn) {
        e.preventDefault();
        const theme = themeBtn.dataset.themeSelect;
        this.applyTheme(theme, this.getSavedMode());
        return;
      }

      // Dark mode toggle
      const modeBtn = e.target.closest('[data-toggle-mode]');
      if (modeBtn) {
        e.preventDefault();
        this.toggleMode();
        return;
      }

      // Theme cycle button
      const cycleBtn = e.target.closest('[data-cycle-theme]');
      if (cycleBtn) {
        e.preventDefault();
        this.cycleTheme();
        return;
      }
    });

    // Keyboard shortcut: Cmd/Ctrl + Shift + T to cycle themes
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 't') {
        e.preventDefault();
        this.cycleTheme();
      }
    });

    // Listen for system dark mode changes
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        // Only auto-switch if user hasn't explicitly set a mode
        const explicitMode = localStorage.getItem(this.MODE_KEY);
        if (!explicitMode) {
          const mode = e.matches ? 'dark' : 'light';
          this.applyTheme(this.getCurrentTheme(), mode);
        }
      });
    }
  },

  /**
   * Update UI elements to reflect current theme
   */
  updateUI() {
    const currentTheme = this.getCurrentTheme();
    const currentMode = this.getCurrentMode();

    // Update theme option buttons
    document.querySelectorAll('[data-theme-select]').forEach(btn => {
      const isActive = btn.dataset.themeSelect === currentTheme;
      btn.setAttribute('data-active', isActive);
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-pressed', isActive);
    });

    // Update mode toggle buttons
    document.querySelectorAll('[data-toggle-mode]').forEach(btn => {
      btn.setAttribute('data-mode', currentMode);
      btn.setAttribute('aria-pressed', currentMode === 'dark');

      // Update icon if it has one
      const lightIcon = btn.querySelector('.icon-light');
      const darkIcon = btn.querySelector('.icon-dark');
      if (lightIcon) lightIcon.style.display = currentMode === 'dark' ? 'none' : 'block';
      if (darkIcon) darkIcon.style.display = currentMode === 'dark' ? 'block' : 'none';
    });

    // Update theme name displays
    document.querySelectorAll('[data-current-theme]').forEach(el => {
      el.textContent = this.THEME_NAMES[currentTheme];
    });

    // Update mode displays
    document.querySelectorAll('[data-current-mode]').forEach(el => {
      el.textContent = currentMode === 'dark' ? 'Dark' : 'Light';
    });
  },

  /**
   * Get current theme
   */
  getCurrentTheme() {
    return document.documentElement.getAttribute('data-theme') || this.DEFAULT_THEME;
  },

  /**
   * Get current mode
   */
  getCurrentMode() {
    return document.documentElement.getAttribute('data-mode') || 'light';
  },

  /**
   * Toggle between light and dark mode
   */
  toggleMode() {
    const currentMode = this.getCurrentMode();
    const newMode = currentMode === 'dark' ? 'light' : 'dark';
    this.applyTheme(this.getCurrentTheme(), newMode);
    this.showToast(`${newMode === 'dark' ? '🌙' : '☀️'} ${newMode} mode`);
  },

  /**
   * Cycle to next theme
   */
  cycleTheme() {
    const current = this.getCurrentTheme();
    const currentIndex = this.THEMES.indexOf(current);
    const nextIndex = (currentIndex + 1) % this.THEMES.length;
    const nextTheme = this.THEMES[nextIndex];

    this.applyTheme(nextTheme, this.getCurrentMode());
    this.showToast(this.THEME_NAMES[nextTheme]);
  },

  /**
   * Show toast notification
   */
  showToast(message) {
    // Remove existing toast
    const existing = document.querySelector('.theme-toast');
    if (existing) existing.remove();

    // Create toast
    const toast = document.createElement('div');
    toast.className = 'theme-toast';
    toast.textContent = message;
    toast.style.cssText = `
      position: fixed;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%);
      padding: 12px 24px;
      background: var(--text-primary, #333);
      color: var(--bg-primary, #fff);
      border-radius: var(--border-radius, 8px);
      font-family: var(--font-primary, sans-serif);
      font-size: 14px;
      font-weight: 500;
      z-index: 10000;
      animation: themeToastIn 0.3s ease forwards;
      box-shadow: var(--shadow-lg, 0 4px 12px rgba(0,0,0,0.15));
    `;

    document.body.appendChild(toast);

    // Remove after delay
    setTimeout(() => {
      toast.style.animation = 'themeToastOut 0.2s ease forwards';
      setTimeout(() => toast.remove(), 200);
    }, 1800);
  },

  /**
   * Get all available themes
   */
  getAvailableThemes() {
    return this.THEMES.map(id => ({
      id,
      name: this.THEME_NAMES[id],
      active: this.getCurrentTheme() === id
    }));
  }
};

// Add toast animations
const style = document.createElement('style');
style.textContent = `
  @keyframes themeToastIn {
    from {
      opacity: 0;
      transform: translateX(-50%) translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
  }
  @keyframes themeToastOut {
    from {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
    to {
      opacity: 0;
      transform: translateX(-50%) translateY(-10px);
    }
  }

  /* Smooth theme transitions */
  .theme-transitioning,
  .theme-transitioning * {
    transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease !important;
  }
`;
document.head.appendChild(style);

// Initialize immediately
ThemeSwitcher.init();

// Export for global access
window.ThemeSwitcher = ThemeSwitcher;
