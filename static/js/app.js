document.addEventListener('DOMContentLoaded', function () {

  /* SIDEBAR TOGGLE — overlay mode, content non si sposta */
  const sidebarToggle = document.getElementById('sidebarToggle');
  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', function () {
      document.body.classList.toggle('sidebar-collapsed');
    });
  }
  const sidebarBackdrop = document.getElementById('sidebarBackdrop');
  if (sidebarBackdrop) {
    sidebarBackdrop.addEventListener('click', function () {
      document.body.classList.add('sidebar-collapsed');
    });
  }

  /* NOTIFICATION DROPDOWN */
  const notifBtn = document.getElementById('notifBtn');
  const notifPanel = document.getElementById('notifPanel');
  if (notifBtn && notifPanel) {
    notifBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      notifPanel.classList.toggle('open');
      document.getElementById('userPanel')?.classList.remove('open');
    });
    document.addEventListener('click', function () {
      notifPanel.classList.remove('open');
    });
    notifPanel.addEventListener('click', function (e) {
      e.stopPropagation();
    });
  }

  /* USER DROPDOWN */
  const userBtn = document.getElementById('userBtn');
  const userPanel = document.getElementById('userPanel');
  if (userBtn && userPanel) {
    userBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      userPanel.classList.toggle('open');
      document.getElementById('notifPanel')?.classList.remove('open');
    });
    document.addEventListener('click', function () {
      userPanel.classList.remove('open');
    });
    userPanel.addEventListener('click', function (e) {
      e.stopPropagation();
    });
  }

  /* GLOBAL SEARCH */
  const searchInput = document.getElementById('globalSearch');
  const searchResults = document.getElementById('searchResults');
  let searchTimeout = null;

  if (searchInput && searchResults) {
    searchInput.addEventListener('input', function () {
      const q = this.value.trim();
      if (searchTimeout) clearTimeout(searchTimeout);

      if (q.length < 2) {
        searchResults.classList.remove('open');
        return;
      }

      searchTimeout = setTimeout(function () {
        fetch('/api/search?q=' + encodeURIComponent(q))
          .then(function (r) { return r.json(); })
          .then(function (data) {
            searchResults.innerHTML = '';
            if (data.results.length === 0) {
              searchResults.innerHTML = '<div class="search-result-item" style="color:#94a3b8;cursor:default">Nessun risultato</div>';
            } else {
              data.results.forEach(function (item) {
                var typeClass = 'result-type-' + item.type.toLowerCase();
                var el = document.createElement('a');
                el.className = 'search-result-item';
                el.href = item.url;
                el.innerHTML = '<span class="search-result-type ' + typeClass + '">' + item.type + '</span>' +
                  '<span class="search-result-label">' + item.label + '</span>';
                searchResults.appendChild(el);
              });
            }
            searchResults.classList.add('open');
          })
          .catch(function () {
            searchResults.classList.remove('open');
          });
      }, 250);
    });

    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        searchResults.classList.remove('open');
        this.blur();
      }
      if (e.key === 'Enter') {
        var firstLink = searchResults.querySelector('a');
        if (firstLink) {
          window.location.href = firstLink.getAttribute('href');
        } else {
          var q = this.value.trim();
          if (q.length > 0) {
            window.location.href = '/search?q=' + encodeURIComponent(q);
          }
        }
      }
    });

    document.addEventListener('click', function (e) {
      if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.classList.remove('open');
      }
    });
  }

  /* TOAST NOTIFICATION SYSTEM */
  window.showToast = function (message, category) {
    category = category || 'info';
    var container = document.getElementById('toast-container');
    if (!container) return;
    var iconMap = {
      success: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" color="var(--success)" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
      error: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" color="var(--error)" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
      warning: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" color="var(--warning)" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
      info: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" color="var(--info)" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    };
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + category;
    toast.innerHTML =
      (iconMap[category] || '') +
      '<div class="toast-body">' + message + '</div>' +
      '<button class="toast-close">&times;</button>';
    container.appendChild(toast);

    var closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', function () {
      toast.classList.add('toast-exit');
      setTimeout(function () { toast.remove(); }, 200);
    });

    setTimeout(function () {
      toast.classList.add('toast-exit');
      setTimeout(function () { toast.remove(); }, 200);
    }, category === 'error' ? 8000 : 5000);
  };

  // Convert server-side flash data to toasts
  var flashData = document.getElementById('flash-data');
  if (flashData) {
    try {
      var messages = JSON.parse(flashData.getAttribute('data-messages'));
      messages.forEach(function (m) {
        // Flash messages are tuples: [category, message]
        window.showToast(m[1], m[0]);
      });
    } catch (e) {}
  }

  /* KEYBOARD SHORTCUTS */
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey && e.key === 'k') {
      e.preventDefault();
      if (searchInput) searchInput.focus();
    }
  });

  /* INLINE FORM VALIDATION — scroll to first error on page load */
  var firstError = document.querySelector('.form-error');
  if (firstError) {
    firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
    var errorInput = firstError.closest('.form-group')?.querySelector('.form-input');
    if (errorInput) {
      errorInput.classList.add('is-invalid');
      errorInput.focus();
    }
  }

  /* GLOBAL Ctrl+Enter to submit any form */
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      var form = e.target.closest('form');
      if (form) {
        e.preventDefault();
        var btn = form.querySelector('[type="submit"]');
        if (btn) btn.click();
      }
    }
  });

  /* SUBMIT BUTTON LOADING STATE — prevent double-clicks */
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (form.querySelector('.btn.loading')) return;
    var btns = form.querySelectorAll('[type="submit"]');
    btns.forEach(function (btn) {
      var originalText = btn.innerHTML;
      if (btn.classList.contains('loading')) return;
      btn.classList.add('loading');
      btn.disabled = true;
      var label = btn.querySelector('.btn-label');
      if (label) {
        label.textContent = 'Salvataggio...';
      } else {
        // Wrap existing text in span, add spinner
        var text = btn.textContent.trim() || 'Salvataggio...';
        btn.innerHTML = '<span class="btn-spinner"></span><span class="btn-label">' + text + '</span>';
      }
      // Re-enable after 10s timeout as safety (page should redirect by then)
      setTimeout(function () {
        btn.disabled = false;
        btn.classList.remove('loading');
      }, 10000);
    });
  });

  /* RESPONSIVE SIDEBAR ON MOBILE */
  function handleMobileSidebar() {
    if (window.innerWidth <= 768) {
      document.body.classList.add('sidebar-collapsed');
    }
  }
  handleMobileSidebar();
  window.addEventListener('resize', handleMobileSidebar);

  /* INLINE STATUS CHANGE */
  var STATUS_OPTIONS = {
    bolle: ['da_elaborare', 'in_lavorazione', 'completata'],
    ddt: ['bozza', 'pronto', 'spedito', 'annullato'],
    picking: ['aperto', 'in_corso', 'completato'],
  };
  var STATUS_LABELS = {
    da_elaborare: 'Da elaborare', in_lavorazione: 'In lavorazione', completata: 'Completata',
    bozza: 'Bozza', pronto: 'Pronto', spedito: 'Spedito', annullato: 'Annullato',
    aperto: 'Aperto', in_corso: 'In corso', completato: 'Completato',
  };

  document.addEventListener('click', function (e) {
    var badge = e.target.closest('.status-inline');
    // Close any open status dropdowns
    document.querySelectorAll('.status-dropdown').forEach(function (d) {
      if (!badge || !d.closest('.status-inline') || !d.closest('.status-inline').contains(badge)) {
        d.remove();
      }
    });
    if (!badge) return;
    e.stopPropagation();
    if (badge.querySelector('.status-dropdown')) return;

    var entity = badge.getAttribute('data-entity');
    var stati = STATUS_OPTIONS[entity];
    if (!stati) return;

    var dropdown = document.createElement('div');
    dropdown.className = 'status-dropdown';
    dropdown.style.cssText = 'position:absolute;top:100%;left:50%;transform:translateX(-50%);z-index:100;background:var(--surface);border:1px solid var(--border);border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.12);padding:4px;min-width:130px;margin-top:4px;';

    stati.forEach(function (s) {
      var opt = document.createElement('button');
      opt.type = 'button';
      opt.className = 'status-dropdown-opt';
      opt.setAttribute('data-stato', s);
      opt.textContent = STATUS_LABELS[s] || s;
      if (s === badge.getAttribute('data-stato')) {
        opt.style.fontWeight = '600';
        opt.style.background = 'var(--surface-hover)';
      }
      opt.addEventListener('click', function (ev) {
        ev.stopPropagation();
        changeStatus(badge, entity, s);
      });
      dropdown.appendChild(opt);
    });

    badge.style.position = 'relative';
    badge.appendChild(dropdown);
  });

  function changeStatus(badge, entity, nuovoStato) {
    var id = badge.getAttribute('data-id');
    var oldStato = badge.getAttribute('data-stato');
    if (nuovoStato === oldStato) return;

    badge.style.opacity = '0.5';
    var dropdown = badge.querySelector('.status-dropdown');
    if (dropdown) dropdown.remove();

    fetch('/api/v1/' + entity + '/' + id + '/stato', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stato: nuovoStato }),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.ok) {
        badge.setAttribute('data-stato', data.stato);
        badge.className = 'status-badge status-' + data.stato + ' status-inline';
        badge.textContent = data.stato_label;
        window.showToast('Stato aggiornato a "' + data.stato_label + '"', 'success');
      } else {
        window.showToast(data.error || 'Errore aggiornamento stato', 'error');
        badge.style.opacity = '1';
      }
    })
    .catch(function () {
      window.showToast('Errore di rete', 'error');
      badge.style.opacity = '1';
    });
  }
});
