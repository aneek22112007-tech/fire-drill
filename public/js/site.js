(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const landing = $('#landing-view');
  const dashboard = $('#dashboard-view');
  const state = { metrics: null, filter: 'all', visibleEvents: 12, replayFrame: null, replayValue: 0, replayPlaying: false };

  const escapeHTML = (value) => String(value).replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
  const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const format = (value) => Number.isInteger(number(value)) ? String(number(value)) : number(value).toFixed(1);
  const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;

  function readFallback() {
    try {
      const data = JSON.parse($('#metrics-fallback').textContent);
      return data && data.schema_version ? data : null;
    } catch (_) { return null; }
  }

  async function loadMetrics(showFeedback = false) {
    const refresh = $('[data-refresh]');
    refresh?.classList.add('spinning');
    try {
      const response = await fetch(`data/metrics.json?v=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`Report request returned ${response.status}`);
      const data = await response.json();
      if (data.schema_version !== 1 || !data.canaries || !Array.isArray(data.reviewers)) throw new Error('Unexpected report schema');
      state.metrics = data;
      renderDashboard();
      setConnection(true, 'JSON report connected');
      if (showFeedback) toast('Dashboard refreshed from the latest public export.');
    } catch (_) {
      if (!state.metrics) state.metrics = readFallback();
      if (state.metrics) {
        renderDashboard();
        setConnection(true, 'Embedded report loaded');
      } else {
        setConnection(false, 'Report unavailable');
      }
      if (showFeedback) toast(state.metrics ? 'Live fetch unavailable; using the embedded report.' : 'The report could not be loaded. Try again.');
    } finally {
      refresh?.classList.remove('spinning');
    }
  }

  function setConnection(connected, text) {
    const el = $('[data-connection]');
    if (!el) return;
    el.classList.toggle('error', !connected);
    $('span', el).textContent = text;
  }

  function setMetric(name, value) {
    $$(`[data-metric="${name}"]`).forEach(el => { el.textContent = value; });
  }

  function renderDashboard() {
    const m = state.metrics;
    if (!m) return;
    const canaries = number(m.canaries.injected);
    const caught = number(m.canaries.caught);
    const rate = number(m.canaries.catch_rate);
    const totalAdaptations = m.adaptations.length;
    const explainBacks = m.adaptations.filter(item => item.kind === 'flatness_explain_back');
    setMetric('catchRate', format(rate));
    setMetric('canaries', canaries);
    setMetric('caught', caught);
    setMetric('missed', number(m.canaries.missed, canaries - caught));
    setMetric('items', number(m.items.total));
    setMetric('canaryMedian', format(m.review_times.canary_seconds));
    setMetric('realMedian', format(m.review_times.real_seconds));
    setMetric('adaptations', totalAdaptations);
    setMetric('explainBacks', explainBacks.length);
    $$('[data-canaries-total]').forEach(el => { el.textContent = canaries; });
    $$('[data-items-total]').forEach(el => { el.textContent = number(m.items.total); });
    $('[data-recommendation]').textContent = m.recommendation;
    $('[data-limits]').textContent = m.limits;
    $('[data-updated]').textContent = m.source === 'recorded-offline-demo' ? 'Verified offline export' : 'Public report snapshot';
    $('[data-explain-count]').textContent = `${explainBacks.length} ACTIVE`;
    $('[data-signal-ring]').style.setProperty('--rate', rate);

    renderMast(m.mast_modes);
    renderReviewers(m.reviewers);
    renderAdaptationSummary(m.adaptation_counts);
    renderTimingChart(m.reviewers);
    renderExplainBacks(explainBacks);
    renderActivity();
    buildAdaptationDots(totalAdaptations);
  }

  function renderMast(modes) {
    $('[data-mast-list]').innerHTML = modes.map(mode => {
      const rate = Math.max(0, Math.min(100, number(mode.catch_rate)));
      return `<div class="mast-row" title="${escapeHTML(mode.name)}: ${format(rate)}% caught">
        <div class="mast-row-top"><span class="mast-code">${escapeHTML(mode.code)}</span><strong>${escapeHTML(mode.name)}</strong><span>${format(rate)}%</span></div>
        <div class="mast-bar" role="img" aria-label="${escapeHTML(mode.name)}: ${format(rate)} percent caught"><i class="caught" style="width:${rate}%"></i><i class="missed" style="width:${100 - rate}%"></i></div>
      </div>`;
    }).join('');
  }

  function reviewerRow(reviewer) {
    const rate = number(reviewer.catch_rate);
    const name = reviewer.name.toLowerCase();
    const initials = name.slice(0, 2).toUpperCase();
    const descriptor = reviewer.flat ? 'Fast + uniform decisions' : rate >= 75 ? 'Careful, consistent review' : 'Mixed review signal';
    return `<tr>
      <td><div class="reviewer-name"><span class="table-avatar ${escapeHTML(name)}">${initials}</span><div><strong>${escapeHTML(name)}</strong><small>${descriptor}</small></div></div></td>
      <td>${number(reviewer.decisions)}</td>
      <td><div class="catch-cell"><span>${format(rate)}%</span><div class="table-track"><i style="width:${rate}%;${rate === 0 ? 'background:var(--red)' : rate < 50 ? 'background:var(--amber)' : ''}"></i></div></div></td>
      <td>${format(reviewer.median_canary_seconds)}s</td><td>${format(reviewer.median_real_seconds)}s</td>
      <td><span class="${reviewer.flat ? 'flat-badge' : 'careful-badge'}">${reviewer.flat ? 'Explain-back' : rate >= 75 ? 'Careful' : 'Observed'}</span></td>
    </tr>`;
  }

  function renderReviewers(reviewers) {
    const html = reviewers.map(reviewerRow).join('');
    $('[data-reviewers-body]').innerHTML = html;
    $('[data-reviewers-body-detail]').innerHTML = html;
  }

  const adaptationLabels = {
    route_canary: ['Canary routing', 'Balanced across reviewers', 'canary'],
    route_high_risk: ['High-risk routing', 'Sent to the freshest reviewer', 'activity'],
    route_medium: ['Medium-risk routing', 'Round-robin distribution', 'arrow'],
    batch_low_risk: ['Low-risk batching', 'Reduced approval noise', 'grid'],
    flatness_explain_back: ['Explain-back', 'Required after a flat signal', 'eye']
  };

  function renderAdaptationSummary(counts) {
    $('[data-adaptation-summary]').innerHTML = counts.map(item => {
      const [title, subtitle, glyph] = adaptationLabels[item.kind] || [item.kind.replaceAll('_', ' '), 'Workflow adaptation', 'activity'];
      return `<div class="adaptation-summary-row"><span class="adaptation-summary-icon">${icon(glyph)}</span><div><strong>${title}</strong><small>${subtitle}</small></div><b>${number(item.count)}×</b></div>`;
    }).join('');
    $('[data-adaptation-count-grid]').innerHTML = counts.map(item => {
      const [title, , glyph] = adaptationLabels[item.kind] || [item.kind.replaceAll('_', ' '), '', 'activity'];
      return `<div class="adaptation-count-card">${icon(glyph)}<strong>${number(item.count)}</strong><span>${title}</span></div>`;
    }).join('');
  }

  function renderTimingChart(reviewers) {
    const max = Math.max(...reviewers.flatMap(r => [number(r.median_canary_seconds), number(r.median_real_seconds)]), 1);
    $('[data-timing-chart]').innerHTML = reviewers.map(reviewer => `<div class="timing-group"><div class="timing-bars">
      <div class="timing-bar" style="height:${number(reviewer.median_canary_seconds) / max * 100}%"><span>${format(reviewer.median_canary_seconds)}s</span></div>
      <div class="timing-bar real" style="height:${number(reviewer.median_real_seconds) / max * 100}%"><span>${format(reviewer.median_real_seconds)}s</span></div>
      </div><strong>${escapeHTML(reviewer.name)}</strong></div>`).join('');
  }

  function renderExplainBacks(explainBacks) {
    $('[data-explain-list]').innerHTML = explainBacks.length ? explainBacks.map(item => `<article class="explain-item"><div>${icon('eye')}<strong>${escapeHTML(item.reviewer)}</strong><span>EXPLAIN-BACK REQUIRED</span></div><p>${escapeHTML(item.description)}</p></article>`).join('') : '<div class="empty-state">No explain-back interventions fired in this drill.</div>';
  }

  function activityCategory(kind) {
    if (kind.startsWith('route')) return 'route';
    if (kind.startsWith('batch')) return 'batch';
    return 'explain';
  }

  function renderActivity() {
    if (!state.metrics) return;
    const filtered = state.metrics.adaptations.filter(item => state.filter === 'all' || activityCategory(item.kind) === state.filter);
    const visible = filtered.slice(0, state.visibleEvents);
    $('[data-activity-list]').innerHTML = visible.length ? visible.map((item, index) => {
      const category = activityCategory(item.kind);
      const glyph = category === 'route' ? 'arrow' : category === 'batch' ? 'grid' : 'eye';
      return `<article class="activity-item ${category}"><span class="activity-item-icon">${icon(glyph)}</span><div><strong>${String(index + 1).padStart(2, '0')} · ${escapeHTML(item.kind)}</strong><p>${escapeHTML(item.description)}</p></div><span>${escapeHTML(item.reviewer)}</span></article>`;
    }).join('') : '<div class="empty-state">No adaptations match this filter.</div>';
    const more = $('[data-load-more]');
    more.hidden = visible.length >= filtered.length;
    more.textContent = `Show more events (${filtered.length - visible.length} remaining)`;
  }

  function buildAdaptationDots(count) {
    const container = $('.adaptation-dots');
    if (container) container.innerHTML = Array.from({ length: Math.min(count, 45) }, () => '<i></i>').join('');
  }

  function routeFromHash() {
    const match = location.hash.match(/^#dashboard(?:\/(overview|reviewers|activity|method))?$/);
    if (match) showDashboard(match[1] || 'overview', false);
    else showLanding(false);
  }

  function showDashboard(tab = 'overview', updateURL = true) {
    landing.hidden = true;
    dashboard.hidden = false;
    document.title = 'Oversight Dashboard — Fire Drill';
    setDashboardTab(tab);
    if (updateURL && location.hash !== `#dashboard${tab === 'overview' ? '' : `/${tab}`}`) {
      history.pushState({ view: 'dashboard', tab }, '', `#dashboard${tab === 'overview' ? '' : `/${tab}`}`);
    }
    window.scrollTo({ top: 0, behavior: 'instant' });
    if (!state.metrics) loadMetrics();
  }

  function showLanding(updateURL = true) {
    closeReplay();
    dashboard.hidden = true;
    landing.hidden = false;
    document.title = 'Fire Drill — Chaos engineering for human oversight';
    if (updateURL) history.pushState({ view: 'landing' }, '', `${location.pathname}${location.search}#top`);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  function setDashboardTab(tab) {
    if (!['overview', 'reviewers', 'activity', 'method'].includes(tab)) tab = 'overview';
    $$('[data-panel]').forEach(panel => {
      const active = panel.dataset.panel === tab;
      panel.hidden = !active;
      panel.classList.toggle('active', active);
    });
    $$('.app-nav [data-dashboard-tab]').forEach(button => button.classList.toggle('active', button.dataset.dashboardTab === tab));
    $('[data-breadcrumb]').textContent = ({ overview: 'Overview', reviewers: 'Reviewers', activity: 'Activity', method: 'Method & safety' })[tab];
    $$('.app-nav.mobile').forEach(nav => nav.classList.remove('mobile'));
    if (location.hash.startsWith('#dashboard')) history.replaceState({ view: 'dashboard', tab }, '', `#dashboard${tab === 'overview' ? '' : `/${tab}`}`);
    window.scrollTo({ top: 0, behavior: reducedMotion.matches ? 'instant' : 'smooth' });
  }

  function toast(message) {
    const el = $('[data-toast]');
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove('show'), 3200);
  }

  const replayModal = $('[data-replay-modal]');
  function openReplay() {
    if (!replayModal.open) replayModal.showModal();
    document.body.classList.add('modal-open');
    state.replayValue = 0;
    state.replayPlaying = true;
    updateReplay();
    if (reducedMotion.matches) finishReplay();
    else {
      state.replayStarted = performance.now();
      state.replayFrame = requestAnimationFrame(tickReplay);
    }
  }

  function tickReplay(now) {
    if (!state.replayPlaying || !replayModal.open) return;
    const progress = Math.min((now - state.replayStarted) / 8000, 1);
    state.replayValue = progress;
    updateReplay();
    if (progress < 1) state.replayFrame = requestAnimationFrame(tickReplay);
    else { state.replayPlaying = false; updateReplay(); }
  }

  function updateReplay() {
    if (!state.metrics) return;
    const total = number(state.metrics.items.total);
    const canaryTotal = number(state.metrics.canaries.injected);
    const caughtTotal = number(state.metrics.canaries.caught);
    const progress = state.replayValue;
    const count = Math.min(total, Math.floor(progress * total));
    const canaries = Math.min(canaryTotal, Math.floor(progress * canaryTotal));
    const caught = Math.min(caughtTotal, Math.floor(progress * caughtTotal));
    $('[data-replay-count]').textContent = count;
    $('[data-replay-canaries]').textContent = `${canaries} / ${canaryTotal}`;
    $('[data-replay-caught]').textContent = `${caught} / ${caughtTotal}`;
    $('[data-replay-progress]').style.width = `${progress * 100}%`;
    const stage = progress < .38 ? 0 : progress < .75 ? 1 : 2;
    $$('.replay-events span').forEach((el, i) => el.classList.toggle('active', i === stage));
    $('[data-replay-label]').textContent = ['ITEMS REVIEWED', 'CANARIES REVEALED', 'ANALYSIS COMPLETE'][stage];
    const toggle = $('[data-replay-toggle]');
    toggle.innerHTML = state.replayPlaying ? `${icon('pause')}<span>Pause replay</span>` : progress >= 1 ? `${icon('check')}<span>Replay complete</span>` : `${icon('play')}<span>Resume replay</span>`;
  }

  function toggleReplay() {
    if (state.replayValue >= 1) { closeReplay(); showDashboard('overview'); return; }
    state.replayPlaying = !state.replayPlaying;
    if (state.replayPlaying) {
      state.replayStarted = performance.now() - state.replayValue * 8000;
      state.replayFrame = requestAnimationFrame(tickReplay);
    } else cancelAnimationFrame(state.replayFrame);
    updateReplay();
  }

  function finishReplay() {
    cancelAnimationFrame(state.replayFrame);
    state.replayValue = 1;
    state.replayPlaying = false;
    updateReplay();
  }

  function closeReplay() {
    if (!replayModal) return;
    cancelAnimationFrame(state.replayFrame);
    state.replayPlaying = false;
    if (replayModal.open) replayModal.close();
    document.body.classList.remove('modal-open');
  }

  function initLandingMotion() {
    const header = $('[data-header]');
    const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 20);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    const reveals = $$('.reveal');
    if ('IntersectionObserver' in window && !reducedMotion.matches) {
      const observer = new IntersectionObserver(entries => entries.forEach(entry => {
        if (entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target); }
      }), { threshold: .12, rootMargin: '0px 0px -35px' });
      reveals.forEach(el => observer.observe(el));
    } else reveals.forEach(el => el.classList.add('visible'));

    const captions = ['Real tasks enter the approval stream.', 'A believable flaw joins the same stream.', 'The Auditor measures every decision.', 'Explain-back and routing close the loop.'];
    const steps = $$('[data-story-step]');
    if ('IntersectionObserver' in window) {
      const storyObserver = new IntersectionObserver(entries => entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        const index = Number(entry.target.dataset.storyStep);
        steps.forEach((step, i) => step.classList.toggle('active', i === index));
        $('[data-story-stage]').dataset.storyStage = index;
        $('[data-stage-number]').textContent = index + 1;
        $('[data-stage-caption]').textContent = captions[index];
      }), { threshold: .6 });
      steps.forEach(step => storyObserver.observe(step));
    }

    initHeroDepth();
    initCanvas();
  }

  function initHeroDepth() {
    const hero = $('.hero');
    const visual = $('[data-hero-visual]');
    const consoleWrap = $('[data-tilt]');
    if (!hero || !visual || !consoleWrap) return;

    const capablePointer = matchMedia('(pointer: fine) and (min-width: 901px)');
    const layers = [
      { el: $('[data-depth="console"]'), x: 15, y: 10, z: 28, rx: -1.5, ry: 2 },
      { el: $('[data-depth="catch"]'), x: -26, y: -19, z: 105, rx: 3, ry: -4 },
      { el: $('[data-depth="flag"]'), x: 30, y: -23, z: 135, rx: -3, ry: 4 },
      { el: $('[data-depth="tag"]'), x: -18, y: 13, z: 76, rx: 2, ry: -3 },
      { el: $('[data-depth="glow"]'), x: 22, y: 14, z: -90, rx: -.5, ry: 1 },
      { el: $('[data-depth="orbit-one"]'), x: -12, y: 8, z: -70, rx: .5, ry: -.8 },
      { el: $('[data-depth="orbit-two"]'), x: 17, y: -11, z: -35, rx: -.6, ry: 1 }
    ].filter(layer => layer.el);
    const target = { x: 0, y: 0, scroll: 0 };
    const current = { ...target };
    let frame = null;

    const updateScroll = () => {
      target.scroll = Math.min(1, Math.max(0, window.scrollY / Math.max(hero.offsetHeight, 1)));
      requestTick();
    };
    const render = () => {
      frame = null;
      if (reducedMotion.matches || !capablePointer.matches || landing.hidden || document.hidden) return;
      let moving = false;
      ['x', 'y', 'scroll'].forEach(key => {
        const delta = target[key] - current[key];
        current[key] += delta * .085;
        if (Math.abs(delta) > .0005) moving = true;
        else current[key] = target[key];
      });
      consoleWrap.style.setProperty('--tilt-y', `${(current.x * 9).toFixed(3)}deg`);
      consoleWrap.style.setProperty('--tilt-x', `${(-current.y * 7).toFixed(3)}deg`);
      consoleWrap.style.setProperty('--scroll-y', `${(current.scroll * 24).toFixed(2)}px`);
      layers.forEach(({ el, x, y, z, rx, ry }) => {
        el.style.setProperty('--layer-x', `${(current.x * x).toFixed(2)}px`);
        el.style.setProperty('--layer-y', `${(current.y * y + current.scroll * z * .12).toFixed(2)}px`);
        el.style.setProperty('--layer-rotate-x', `${(current.y * rx).toFixed(3)}deg`);
        el.style.setProperty('--layer-rotate-y', `${(current.x * ry).toFixed(3)}deg`);
      });
      if (moving) requestTick();
    };
    function requestTick() {
      if (frame === null && !reducedMotion.matches && capablePointer.matches && !landing.hidden && !document.hidden) {
        frame = requestAnimationFrame(render);
      }
    }
    const reset = () => {
      target.x = 0;
      target.y = 0;
      requestTick();
    };
    const syncCapability = () => {
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
      if (reducedMotion.matches || !capablePointer.matches) {
        consoleWrap.style.removeProperty('--tilt-x');
        consoleWrap.style.removeProperty('--tilt-y');
        consoleWrap.style.removeProperty('--scroll-y');
        layers.forEach(({ el }) => ['--layer-x', '--layer-y', '--layer-rotate-x', '--layer-rotate-y'].forEach(name => el.style.removeProperty(name)));
        return;
      }
      updateScroll();
    };

    visual.addEventListener('pointermove', event => {
      if (!capablePointer.matches || reducedMotion.matches) return;
      const rect = visual.getBoundingClientRect();
      target.x = Math.min(.5, Math.max(-.5, (event.clientX - rect.left) / rect.width - .5)) * 2;
      target.y = Math.min(.5, Math.max(-.5, (event.clientY - rect.top) / rect.height - .5)) * 2;
      requestTick();
    }, { passive: true });
    visual.addEventListener('pointerleave', reset, { passive: true });
    window.addEventListener('scroll', updateScroll, { passive: true });
    document.addEventListener('visibilitychange', () => { if (!document.hidden) updateScroll(); });
    capablePointer.addEventListener('change', syncCapability);
    reducedMotion.addEventListener('change', syncCapability);
    syncCapability();
  }

  function initCanvas() {
    const canvas = $('#hero-canvas');
    if (!canvas || reducedMotion.matches) return;
    const context = canvas.getContext('2d', { alpha: true });
    let width = 0, height = 0, points = [], animationId, lastFrame = 0;
    const pointer = { x: .72, y: .35 };
    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(devicePixelRatio || 1, 1.5);
      width = rect.width; height = rect.height;
      canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.min(48, Math.max(20, Math.floor(width / 30)));
      points = Array.from({ length: count }, (_, i) => ({
        x: width * (.46 + Math.random() * .55), y: Math.random() * height,
        vx: (Math.random() - .5) * .055, vy: (Math.random() - .5) * .055,
        r: i % 9 === 0 ? 1.7 : .8
      }));
    }
    function draw(now) {
      animationId = requestAnimationFrame(draw);
      if (now - lastFrame < 32 || document.hidden || landing.hidden) return;
      lastFrame = now;
      context.clearRect(0, 0, width, height);
      points.forEach(point => {
        point.x += point.vx; point.y += point.vy;
        if (point.x < width * .42 || point.x > width) point.vx *= -1;
        if (point.y < 0 || point.y > height) point.vy *= -1;
      });
      for (let i = 0; i < points.length; i++) {
        const a = points[i];
        for (let j = i + 1; j < points.length; j++) {
          const b = points[j];
          const distance = Math.hypot(a.x - b.x, a.y - b.y);
          if (distance < 115) {
            context.strokeStyle = `rgba(255,177,112,${(1 - distance / 115) * .085})`;
            context.lineWidth = .6;
            context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
          }
        }
        const glow = Math.hypot(a.x - pointer.x * width, a.y - pointer.y * height) < 180;
        context.fillStyle = glow ? 'rgba(255,172,99,.36)' : 'rgba(177,196,181,.16)';
        context.beginPath(); context.arc(a.x, a.y, a.r, 0, Math.PI * 2); context.fill();
      }
    }
    canvas.addEventListener('pointermove', event => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = (event.clientX - rect.left) / width; pointer.y = (event.clientY - rect.top) / height;
    }, { passive: true });
    window.addEventListener('resize', resize, { passive: true });
    resize(); animationId = requestAnimationFrame(draw);
    reducedMotion.addEventListener('change', event => { if (event.matches) { cancelAnimationFrame(animationId); context.clearRect(0, 0, width, height); } });
  }

  function bindEvents() {
    $$('[data-open-dashboard]').forEach(button => button.addEventListener('click', () => showDashboard()));
    $$('[data-open-landing]').forEach(button => button.addEventListener('click', () => showLanding()));
    $$('[data-open-replay]').forEach(button => button.addEventListener('click', openReplay));
    $$('[data-close-replay]').forEach(button => button.addEventListener('click', closeReplay));
    $$('[data-dashboard-tab]').forEach(button => button.addEventListener('click', () => setDashboardTab(button.dataset.dashboardTab)));
    $('[data-refresh]').addEventListener('click', () => loadMetrics(true));
    $('[data-replay-toggle]').addEventListener('click', toggleReplay);
    $('[data-replay-restart]').addEventListener('click', () => { state.replayValue = 0; state.replayPlaying = true; state.replayStarted = performance.now(); cancelAnimationFrame(state.replayFrame); if (reducedMotion.matches) finishReplay(); else state.replayFrame = requestAnimationFrame(tickReplay); updateReplay(); });
    $('[data-replay-finish]').addEventListener('click', finishReplay);
    replayModal.addEventListener('cancel', () => { document.body.classList.remove('modal-open'); state.replayPlaying = false; });
    replayModal.addEventListener('click', event => { if (event.target === replayModal) closeReplay(); });

    $$('[data-activity-filter]').forEach(button => button.addEventListener('click', () => {
      state.filter = button.dataset.activityFilter;
      state.visibleEvents = 12;
      $$('[data-activity-filter]').forEach(el => el.classList.toggle('active', el === button));
      renderActivity();
    }));
    $('[data-load-more]').addEventListener('click', () => { state.visibleEvents += 12; renderActivity(); });

    const menuButton = $('[data-menu-toggle]');
    menuButton.addEventListener('click', () => {
      const open = $('[data-mobile-nav]').classList.toggle('open');
      menuButton.setAttribute('aria-expanded', String(open));
    });
    $$('[data-mobile-nav] a').forEach(link => link.addEventListener('click', () => {
      $('[data-mobile-nav]').classList.remove('open'); menuButton.setAttribute('aria-expanded', 'false');
    }));

    const appMenu = document.createElement('button');
    appMenu.className = 'icon-button app-sections-button';
    appMenu.setAttribute('aria-label', 'Open dashboard sections');
    appMenu.innerHTML = icon('grid');
    $('.app-top-actions').prepend(appMenu);
    const mobileAppNav = $('.app-nav').cloneNode(true);
    mobileAppNav.classList.remove('mobile');
    mobileAppNav.setAttribute('aria-label', 'Mobile dashboard sections');
    dashboard.append(mobileAppNav);
    appMenu.addEventListener('click', () => {
      const open = mobileAppNav.classList.toggle('mobile');
      appMenu.setAttribute('aria-expanded', String(open));
    });
    $$('[data-dashboard-tab]', mobileAppNav).forEach(button => button.addEventListener('click', () => setDashboardTab(button.dataset.dashboardTab)));
    document.addEventListener('click', event => {
      if (!mobileAppNav.contains(event.target) && !appMenu.contains(event.target)) mobileAppNav.classList.remove('mobile');
    });
    window.addEventListener('popstate', routeFromHash);
    window.addEventListener('hashchange', routeFromHash);
  }

  state.metrics = readFallback();
  bindEvents();
  initLandingMotion();
  if (state.metrics) renderDashboard();
  routeFromHash();
  if (!dashboard.hidden) loadMetrics();
})();
