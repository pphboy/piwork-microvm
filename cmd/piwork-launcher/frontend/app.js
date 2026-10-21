(() => {
  'use strict';

  const byId = (id) => document.getElementById(id);
  const all = (selector) => Array.from(document.querySelectorAll(selector));
  const phaseStep = {
    acceleration: 0, ports: 0, bundle: 0, extract: 0,
    storage: 1, disk: 1, vm: 1, guest: 1,
    web: 2, runtime: 2, shutdown: 1
  };

  const ui = {
    status: null,
    catalogs: null,
    language: "en",
    earlyStatus: null,
    logs: [],
    logEpoch: 0,
    logAvailability: { currentAvailable: false, allAvailable: false, historical: false },
    expanded: false,
    pending: false,
    toastTimer: null
  };

  function api(name) {
    try {
      return window.go && window.go.main && window.go.main.App ? window.go.main.App[name] : null;
    } catch {
      return null;
    }
  }

  async function call(name, ...args) {
    const fn = api(name);
    if (!fn) throw new Error(t('backend.unavailable'));
    return await fn(...args);
  }

  function t(key, params = {}) {
    let value = ui.catalogs && ((ui.catalogs[ui.language] || {})[key] || ui.catalogs.en[key]);
    value = value || ({"backend.unavailable": "Desktop backend is not ready.", "error.generic": "The operation failed. View logs for details."}[key]) || key;
    return value.replace(/\{(\w+)\}/g, (_, name) => params[name] ?? '');
  }

  function translateStatic() {
    document.documentElement.lang = ui.language;
    all('[data-i18n]').forEach((node) => { node.textContent = t(node.dataset.i18n); });
    for (const attr of ['title', 'aria-label']) {
      all(`[data-i18n-${attr}]`).forEach((node) => node.setAttribute(attr, t(node.getAttribute(`data-i18n-${attr}`))));
    }
    all('[data-language]').forEach((button) => button.setAttribute('aria-checked', String(button.dataset.language === ui.language)));
  }

  function causeText(raw, phase) {
    const text = String(raw || '');
    const port = text.match(/127\.0\.0\.1:(\d+)/);
    if (/port.*(occupied|unavailable|use)|address already in use/i.test(text)) return t('error.ports', {port: port ? port[1] : ''});
    if (/KVM|WHPX|hypervisor|virtualization/i.test(text)) return t('error.acceleration');
    if (/preferences|language.*sav/i.test(text)) return t('error.preferences');
    if (/shutdown|not.*clean|stop.*confirm/i.test(text)) return t('error.shutdown');
    if (/timed? out|timeout/i.test(text)) return t('error.timeout');
    if (/bundle|resource|checksum|manifest|trailer/i.test(text)) return t('error.bundle');
    if (/data directory|installation|disk|qcow2|permission|access.*denied/i.test(text)) return t('error.storage');
    if (/Guest|QEMU|MicroVM/i.test(text)) return t('error.guest');
    if (phase === 'ports') return t('error.ports', {port: port ? port[1] : ''});
    return t('error.generic');
  }

  function errorText(err) {
    const raw = err && err.message ? err.message : String(err);
    // Keep the real diagnostic in the existing log channel; the toast uses
    // application text in the selected language.
    if (api('ReportError')) call('ReportError', raw).then(refreshLogs).catch(() => {});
    return causeText(raw);
  }

  function showToast(message, isError) {
    const toast = byId('toast');
    byId('toastText').textContent = message;
    toast.classList.toggle('error', Boolean(isError));
    toast.classList.add('show');
    clearTimeout(ui.toastTimer);
    ui.toastTimer = setTimeout(() => toast.classList.remove('show'), 2200);
  }

  function setScreen(name) {
    all('.screen').forEach((screen) => {
      screen.classList.toggle('active', screen.dataset.screen === name);
    });
  }

  function renderSteps(phase, failed) {
    const index = phase === undefined ? 0 : (phaseStep[phase] ?? 0);
    all('[data-step]').forEach((step) => {
      const i = Number(step.dataset.step);
      step.classList.toggle('done', !failed && i < index);
      step.classList.toggle('current', !failed && i === index);
      const holder = step.querySelector('.step-icon');
      holder.innerHTML = (!failed && i < index)
        ? '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"/></svg>'
        : '<span class="point"></span>';
    });
  }

  function updateExportAvailability() {
    const current = Boolean(ui.logAvailability.currentAvailable);
    const all = Boolean(ui.logAvailability.allAvailable);
    byId('exportCurrent').disabled = !current;
    byId('exportAll').disabled = !all;
    byId('exportTrigger').disabled = !(current || all);
  }

  function renderLogs() {
    const body = byId('logBody');
    const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 24;
    if (ui.logs.length) {
      body.textContent = ui.logs.join('\n');
      byId('logCount').textContent = ui.logAvailability.currentAvailable
        ? '· ' + t('logs.lines', {n: ui.logs.length})
        : '· ' + (ui.logAvailability.historical ? t('logs.history.label') + ' ' : '') + t('logs.lines', {n: ui.logs.length});
    } else if (ui.logAvailability.allAvailable) {
      body.textContent = ui.logAvailability.historical
        ? t('logs.history')
        : t('logs.none');
      byId('logCount').textContent = ui.logAvailability.historical ? '· ' + t('logs.history.label') : '—';
    } else {
      body.textContent = t('logs.none');
      byId('logCount').textContent = '—';
    }
    if (atBottom) body.scrollTop = body.scrollHeight;
    updateExportAvailability();
  }

  function setExpanded(value) {
    ui.expanded = Boolean(value);
    byId('logsWrapper').classList.toggle('expanded', ui.expanded);
    byId('logToggle').setAttribute('aria-expanded', String(ui.expanded));
    if (ui.expanded) {
      refreshLogs();
      const body = byId('logBody');
      body.scrollTop = body.scrollHeight;
    }
  }

  function applyStatus(st) {
    if (!st) return false;
    if (ui.status && Number(st.revision) < Number(ui.status.revision)) return false;
    const previousScreen = ui.status ? ui.status.state : null;
    ui.status = st;
    const language = st.language === "zh-CN" ? "zh-CN" : "en";
    if (ui.language !== language) { ui.language = language; translateStatic(); renderLogs(); }
    setScreen(st.state || 'idle');

    const path = st.installationRoot || '';
    all('.storage-path').forEach((node) => {
      node.textContent = path || t('storage.fallback');
      node.title = path;
    });
    all('.storage-section').forEach((node) => {
      node.hidden = !(st.setupRequired && (st.state === 'idle' || st.state === 'error'));
    });
    const warning = st.preferenceError ? t('error.preferences') : '';
    all('.storage-warning').forEach((node) => {
      node.textContent = warning;
      node.hidden = !warning;
    });
    all('.choose-path').forEach((button) => {
      button.disabled = !st.canChooseDir || ui.pending;
    });

    byId('startButton').disabled = !st.canStart;
    byId('retryButton').disabled = !st.canRetry || ui.pending;
    byId('stopButton').disabled = !st.canStop || ui.pending;
    const webOpen = st.state === 'running' && st.webAvailable === true;
    byId('openButton').disabled = !webOpen;
    byId('copyWeb').disabled = !webOpen;
    byId('copyImage').disabled = !st.diskPath;

    if (st.state === 'starting') {
      byId('startupMessage').textContent = t('phase.' + (st.phase || 'acceleration'));
      renderSteps(st.phase, false);
    } else if (st.state === 'error') {
      byId('errorMessage').textContent = causeText(st.error || st.preferenceError, st.phase);
      renderSteps(st.phase, true);
    } else if (st.state === 'stopping') {
      byId('stoppingMessage').textContent = t('stopping.description');
    }

    byId('webUiValue').textContent = st.webURL || '';
    byId('webUiValue').title = st.webURL || '';
    byId('imageValue').textContent = st.diskPath || '';
    byId('imageValue').title = st.diskPath || '';
    byId('runtimeNote').hidden = !(st.state === 'running' && st.runtimeReady !== true);

    const banner = byId('banner');
    banner.hidden = !st.preferenceError;
    banner.textContent = st.preferenceError ? t('preferences') + ': ' + t('error.preferences') : '';

    byId('footerStatus').textContent = t('local') + ' · ' + t('state.' + (st.state || 'idle'));

    if (st.state !== previousScreen && st.state === 'starting') {
      setExpanded(false);
    }
    updateExportAvailability();
    return true;
  }

  async function refreshLogs() {
    if (!api('ReadLogs')) return;
    const epoch = ui.logEpoch;
    const session = ui.status && ui.status.session;
    const root = ui.status && ui.status.installationRoot;
    try {
      const view = await call('ReadLogs');
      if (!ui.status || ui.status.session !== session || ui.status.installationRoot !== root) return;
      ui.logAvailability = {
        currentAvailable: Boolean(view.currentAvailable),
        allAvailable: Boolean(view.allAvailable),
        historical: Boolean(view.historical)
      };
      if (ui.logEpoch === epoch) {
        ui.logs = view.text ? view.text.replace(/\n$/, '').split('\n') : [];
      }
      renderLogs();
    } catch {
      renderLogs();
    }
  }

  function onStatus(st) {
    if (!st) return;
    if (!ui.catalogs) {
      if (!ui.earlyStatus || st.revision >= ui.earlyStatus.revision) ui.earlyStatus = st;
      return;
    }
    const previousSession = ui.status ? ui.status.session : null;
    const previousLog = ui.status && ui.status.logPath;
    if (!applyStatus(st)) return;
    if (st.session !== previousSession) {
      ui.logs = [];
      ui.logEpoch += 1;
      ui.logAvailability = { currentAvailable: false, allAvailable: false, historical: false };
      renderLogs();
      refreshLogs();
    } else if (st.logPath !== previousLog || st.state === 'error') {
      refreshLogs();
    }
  }

  function onLog(line) {
    if (!line || !ui.status || line.session !== ui.status.session) return;
    ui.logs.push(line.text);
    if (ui.logs.length > 3000) ui.logs.splice(0, ui.logs.length - 3000);
    ui.logEpoch += 1;
    renderLogs();
  }

  function subscribe() {
    if (!window.runtime || typeof window.runtime.EventsOn !== 'function') return;
    window.runtime.EventsOn('launcher:status', onStatus);
    window.runtime.EventsOn('launcher:log', onLog);
  }

  async function boot() {
    bindUI();
    subscribe();
    try {
      ui.catalogs = await call('GetCatalogs');
      translateStatic();
      if (ui.earlyStatus) onStatus(ui.earlyStatus);
      onStatus(await call('GetStatus'));
    } catch (err) {
      byId('errorMessage').textContent = errorText(err);
      setScreen('error');
    }
    refreshLogs();
  }

  function closeMenus() {
    byId('moreMenu').classList.remove('open');
    byId('exportMenu').classList.remove('open');
    byId('moreTrigger').setAttribute('aria-expanded', 'false');
    byId('exportTrigger').setAttribute('aria-expanded', 'false');
  }

  function openModal(title, body) {
    byId('modalTitle').textContent = title;
    byId('modalBody').textContent = body;
    byId('modalScrim').classList.add('visible');
    byId('modalClose').focus();
  }

  function closeModal() {
    byId('modalScrim').classList.remove('visible');
  }

  async function withPending(fn) {
    if (ui.pending) return;
    ui.pending = true;
    applyStatus(ui.status);
    try {
      await fn();
    } finally {
      ui.pending = false;
      if (ui.status) applyStatus(ui.status);
    }
  }

  function bindUI() {
    byId('startButton').addEventListener('click', () => withPending(async () => {
      try {
        const st = await call('Start');
        if (st) onStatus(st);
      } catch (err) {
        showToast(errorText(err), true);
      }
    }));

    byId('retryButton').addEventListener('click', () => withPending(async () => {
      try {
        const st = await call('Start');
        if (st) onStatus(st);
      } catch (err) {
        showToast(errorText(err), true);
      }
    }));

    byId('stopButton').addEventListener('click', () => withPending(async () => {
      try {
        await call('RequestStop');
      } catch (err) {
        showToast(errorText(err), true);
      }
    }));

    all('.choose-path').forEach((button) => button.addEventListener('click', () => withPending(async () => {
      try {
        const st = await call('ChooseDataDir');
        if (st) onStatus(st);
      } catch (err) {
        showToast(errorText(err), true);
      }
    })));

    byId('openButton').addEventListener('click', async () => {
      try {
        await call('OpenPiwork');
      } catch (err) {
        showToast(errorText(err), true);
      }
    });

    byId('copyWeb').addEventListener('click', async () => {
      try {
        await call('CopyWebURL');
        showToast(t('copied.web'));
      } catch (err) {
        showToast(errorText(err), true);
      }
    });

    byId('copyImage').addEventListener('click', async () => {
      try {
        await call('CopyImagePath');
        showToast(t('copied.image'));
      } catch (err) {
        showToast(errorText(err), true);
      }
    });

    byId('seeLogButton').addEventListener('click', () => setExpanded(true));
    byId('logToggle').addEventListener('click', () => setExpanded(!ui.expanded));

    byId('exportTrigger').addEventListener('click', (event) => {
      event.stopPropagation();
      if (byId('exportTrigger').disabled) return;
      const open = !byId('exportMenu').classList.contains('open');
      closeMenus();
      byId('exportMenu').classList.toggle('open', open);
      byId('exportTrigger').setAttribute('aria-expanded', String(open));
    });

    byId('exportCurrent').addEventListener('click', async () => {
      closeMenus();
      if (byId('exportCurrent').disabled) return;
      try {
        const target = await call('ExportCurrent');
        if (target) showToast(t('logs.exported'));
      } catch (err) {
        showToast(errorText(err), true);
      }
    });

    byId('exportAll').addEventListener('click', async () => {
      closeMenus();
      if (byId('exportAll').disabled) return;
      try {
        const target = await call('ExportAll');
        if (target) showToast(t('logs.exported'));
      } catch (err) {
        showToast(errorText(err), true);
      }
    });

    byId('moreTrigger').addEventListener('click', (event) => {
      event.stopPropagation();
      const open = !byId('moreMenu').classList.contains('open');
      closeMenus();
      byId('moreMenu').classList.toggle('open', open);
      byId('moreTrigger').setAttribute('aria-expanded', String(open));
    });

    all('[data-external]').forEach((item) => item.addEventListener('click', async () => {
      closeMenus();
      try {
        await call('OpenExternal', item.dataset.external);
      } catch (err) {
        showToast(errorText(err), true);
      }
    }));

    all('[data-language]').forEach((button) => button.addEventListener('click', () => withPending(async () => {
      closeMenus();
      try { onStatus(await call('SetLanguage', button.dataset.language)); }
      catch (err) { errorText(err); showToast(t('error.language'), true); }
    })));

    byId('helpMenu').addEventListener('click', () => {
      closeMenus();
      openModal(t('help'), t('help.body'));
    });

    byId('aboutMenu').addEventListener('click', async () => {
      closeMenus();
      try {
        const about = await call('GetAbout');
        const v = about.version || {};
        openModal(t('about.title'), [
          `Piwork MicroVM ${v.version || ''}`.trim(),
          `${t('about.upstream')} ${v.upstreamVersion || t('unknown')} (${v.upstreamCommit || t('unknown')})`,
          `${t('about.manifest')} ${v.manifestVersion || t('unknown')}`,
          `${t('about.platform')} ${about.platform || t('unknown')}/${about.arch || t('unknown')}`,
          '',
          t('about.description')
        ].join('\n'));
      } catch (err) {
        openModal(t('about.title'), errorText(err));
      }
    });

    byId('minimizeWindow').addEventListener('click', async () => {
      try {
        await call('MinimizeWindow');
      } catch (err) {
        showToast(errorText(err), true);
      }
    });

    byId('closeWindow').addEventListener('click', async () => {
      try {
        const quit = await call('RequestClose');
        if (!quit) showToast(t('cancelled.close'));
      } catch (err) {
        showToast(errorText(err), true);
      }
    });

    byId('modalClose').addEventListener('click', closeModal);
    byId('modalScrim').addEventListener('click', (event) => {
      if (event.target === byId('modalScrim')) closeModal();
    });

    document.addEventListener('click', (event) => {
      if (!event.target.closest('.menu-anchor') && !event.target.closest('.log-export-wrap')) closeMenus();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        if (byId('modalScrim').classList.contains('visible')) closeModal();
        else closeMenus();
      }
    });
  }

  boot();
})();
