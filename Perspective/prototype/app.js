(function () {
  'use strict';

  var MONTHS_S = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var MONTHS_L = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  var LEVEL = { quiet: 0, context: 1, lead: 2 };
  var LEVELS = ['quiet', 'context', 'lead'];
  var IMP = { low: 0, medium: 1, high: 2 };
  var REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var SPEED = 125;      // px per second while the circle walks
  var DWELL = 1400;     // ms the circle rests on a milestone
  var Z_DWELL = 1900;   // ms the circle rests on an event in a zoomed story

  var TYPE_LABEL = {
    vital: 'Vital sign', lab: 'Lab', medication: 'Medicine', procedure: 'Procedure',
    note: 'Note', allergy: 'Allergy', diagnosis: 'Diagnosis', admission: 'Admission'
  };
  var FILTER_LABEL = {
    vital: 'Vitals', lab: 'Labs', medication: 'Medicines', procedure: 'Procedures',
    note: 'Notes', allergy: 'Allergies', diagnosis: 'Diagnoses', admission: 'Admissions'
  };
  var ICONS = {
    diagnosis: '<path d="M9 3h6v4H9zM6 5H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1M8 12h8M8 16h5"/>',
    medication: '<path d="m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z"/><path d="m8.5 8.5 7 7"/>',
    admission: '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/>',
    procedure: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    lab: '<path d="M10 2v7.5L4.5 19a2 2 0 0 0 1.8 3h11.4a2 2 0 0 0 1.8-3L14 9.5V2M8.5 2h7M7 16h10"/>',
    allergy: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
    note: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h6"/>',
    vital: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    flag: '<path d="M4 22V4M4 4h13l-2 4 2 4H4"/>'
  };

  var DATA = null;
  var MS = [];
  var state = {
    role: 'physician',
    objective: 'morning-round',
    start: '2020-01-01',
    types: {},
    startIdx: 0,
    lastFocus: null,
    zoomIdx: -1,
    resumeMain: false
  };
  var stage = null, mainStage = null, zoomStage = null;

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var rail, track, tip, wrap, zoom;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function icon(type, cls) {
    return '<svg viewBox="0 0 24 24" aria-hidden="true"' + (cls ? ' class="' + cls + '"' : '') + '>' + (ICONS[type] || '') + '</svg>';
  }
  function parts(s) { var a = s.split('-'); return { y: +a[0], m: +a[1], d: +a[2] }; }
  function longDate(s) { var p = parts(s); return p.d + ' ' + MONTHS_L[p.m - 1] + ' ' + p.y; }
  function gapLabel(a, b) {
    var A = parts(a), B = parts(b);
    var days = Math.round((Date.UTC(B.y, B.m - 1, B.d) - Date.UTC(A.y, A.m - 1, A.d)) / 86400000);
    if (days <= 60) return '+' + days + (days === 1 ? ' day' : ' days');
    var months = (B.y - A.y) * 12 + (B.m - A.m) - (B.d < A.d ? 1 : 0);
    var y = Math.floor(months / 12), m = months % 12;
    if (y === 0) return '+' + m + ' mo';
    return '+' + y + ' y' + (m ? ' ' + m + ' mo' : '');
  }
  function say(msg) { $('#live').textContent = msg; }

  /* ---------- Data ---------- */
  function loadData() {
    var fromScript = function () {
      if (window.PERSPECTIVE_DATA) return window.PERSPECTIVE_DATA;
      throw new Error('Patient data not found');
    };
    if (!window.fetch || location.protocol === 'file:') return Promise.resolve(fromScript());
    return fetch('data/patient.json')
      .then(function (r) { if (!r.ok) throw new Error('bad'); return r.json(); })
      .catch(fromScript);
  }

  function buildMilestones() {
    var by = {}, order = [];
    DATA.events.forEach(function (ev, i) {
      ev._n = i + 1;
      if (!by[ev.date]) { by[ev.date] = { date: ev.date, events: [] }; order.push(ev.date); }
      by[ev.date].events.push(ev);
    });
    order.sort();
    MS = order.map(function (d) { return by[d]; });
  }

  /* ---------- Ranking (the only thing the role changes) ---------- */
  function salienceOf(ev, role, obj) {
    var s = null;
    ev.tags.forEach(function (t) {
      var v = role.salience[t];
      if (v !== undefined && (s === null || LEVEL[v] > LEVEL[s])) s = v;
    });
    if (s === null) s = 'context';
    var boosted = ev.tags.some(function (t) { return obj.boosts.indexOf(t) >= 0; });
    if (boosted && s !== 'lead') s = LEVELS[LEVEL[s] + 1];
    return s;
  }
  function rankOf(ev, role) {
    var r = 99;
    ev.tags.forEach(function (t) { var i = role.priority.indexOf(t); if (i >= 0 && i < r) r = i; });
    return r;
  }
  function whyOf(ev, role) {
    var order = role.priority.concat(Object.keys(role.why));
    for (var i = 0; i < order.length; i++) {
      if (ev.tags.indexOf(order[i]) >= 0 && role.why[order[i]]) return role.why[order[i]];
    }
    return null;
  }
  function better(a, b) {
    if (LEVEL[a._sal] !== LEVEL[b._sal]) return LEVEL[a._sal] > LEVEL[b._sal];
    if (a._rank !== b._rank) return a._rank < b._rank;
    return IMP[a.importance] > IMP[b.importance];
  }
  function evaluate() {
    var role = DATA.roles[state.role], obj = DATA.objectives[state.objective];
    DATA.events.forEach(function (ev) {
      ev._sal = salienceOf(ev, role, obj);
      ev._rank = rankOf(ev, role);
      ev._why = whyOf(ev, role);
    });
    MS.forEach(function (m) {
      var best = m.events[0];
      m.events.forEach(function (ev) { if (better(ev, best)) best = ev; });
      m.lead = best;
      m.sal = best._sal;
      m.flag = m.events.some(function (e) { return e.flag === 'high' && e._sal === 'lead'; }) ? 'high' : '';
    });
  }
  function leadEvents() {
    return DATA.events.filter(function (e) { return e._sal === 'lead'; })
      .sort(function (a, b) { return a._rank - b._rank || (a.date < b.date ? -1 : 1); });
  }

  /* ---------- Static blocks ---------- */
  function renderPatient() {
    var p = DATA.patient;
    $('#patient').innerHTML =
      '<span class="avatar" aria-hidden="true">' + esc(p.initials) + '</span>' +
      '<div><b>' + esc(p.name) + '</b><span>' + p.age + ' · ' + esc(p.sex.charAt(0).toUpperCase() + p.sex.slice(1)) +
      ' · ID ' + esc(p.id) + ' · Ward ' + (p.ward ? esc(p.ward) : 'not documented') + '</span></div>';
  }

  function renderControls() {
    var roles = $('#roles');
    roles.innerHTML = Object.keys(DATA.roles).map(function (k) {
      return '<button type="button" data-role="' + k + '" aria-pressed="false">' + esc(DATA.roles[k].label) + '</button>';
    }).join('');
    roles.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-role]');
      if (b) setRole(b.getAttribute('data-role'), true);
    });
    var sel = $('#objective');
    sel.innerHTML = Object.keys(DATA.objectives).map(function (k) {
      return '<option value="' + k + '">' + esc(DATA.objectives[k].label) + '</option>';
    }).join('');
    sel.addEventListener('change', function () { state.objective = sel.value; refresh(true); });

    $('#periods').innerHTML = DATA.periods.map(function (p) {
      return '<button type="button" class="chip" data-date="' + p.date + '" aria-pressed="false">' + esc(p.label) + '</button>';
    }).join('');
    $('#periods').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-date]');
      if (b) setStart(b.getAttribute('data-date'));
    });
    $('#start').addEventListener('change', function (e) { if (e.target.value) setStart(e.target.value); });

    var f = $('#filters');
    Object.keys(FILTER_LABEL).forEach(function (t) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'chip'; b.setAttribute('aria-pressed', 'false');
      b.setAttribute('data-type', t); b.textContent = FILTER_LABEL[t];
      f.appendChild(b);
    });
    f.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-type]');
      if (!b) return;
      var t = b.getAttribute('data-type');
      if (state.types[t]) delete state.types[t]; else state.types[t] = true;
      b.setAttribute('aria-pressed', state.types[t] ? 'true' : 'false');
      applyFilter();
    });
  }

  function renderSummary() {
    var byId = {};
    DATA.events.forEach(function (e) { byId[e.id] = e; });
    $('#summary').innerHTML = DATA.summary.map(function (s) {
      var cites = s.cites.map(function (id) {
        var ev = byId[id];
        return '<button type="button" class="cite" data-ev="' + id + '" aria-label="Zoom in on source: ' + esc(ev.source.document) + ', ' + ev.source.recorded + '">' + ev._n + '</button>';
      }).join('');
      return '<span class="s">' + esc(s.text) + cites + '</span>';
    }).join(' ');
    $('#summary-note').textContent = DATA.summaryNote;
    $('#summary').addEventListener('click', function (e) {
      var b = e.target.closest('.cite');
      if (!b) return;
      var id = b.getAttribute('data-ev');
      state.lastFocus = b;
      openZoom(indexOfEvent(id), id);
    });
  }

  function indexOfEvent(id) {
    for (var i = 0; i < MS.length; i++) {
      for (var j = 0; j < MS[i].events.length; j++) if (MS[i].events[j].id === id) return i;
    }
    return 0;
  }

  function renderMeasures() {
    $('#trends').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-ev]');
      if (!b) return;
      state.lastFocus = b;
      openZoom(indexOfEvent(b.getAttribute('data-ev')), b.getAttribute('data-ev'));
    });
  }

  function renderSideCards() {
    var role = DATA.roles[state.role];
    var flagged = DATA.events.filter(function (e) { return e.flag; });
    $('#look-body').innerHTML = flagged.map(function (e) {
      return '<button type="button" data-ev="' + e.id + '"><p>' + esc(e.title) + '</p><small>Flagged ' + esc(e.flag) + ' · ' + e.date + '. One result; a second value is not documented.</small></button>';
    }).join('');
    var allergy = DATA.events.filter(function (e) { return e.type === 'allergy'; })[0];
    $('#allergy-body').innerHTML = '<button type="button" data-ev="' + allergy.id + '"><p>' + esc(allergy.details[0][1]) + '</p><small>' + esc(role.allergyNote) + '</small></button>';
    $('#missing-body').innerHTML = role.notDocumented.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('');
    markTrendLeads();
  }

  function bindSideCards() {
    ['#look-body', '#allergy-body'].forEach(function (sel) {
      $(sel).addEventListener('click', function (e) {
        var b = e.target.closest('button[data-ev]');
        if (!b) return;
        state.lastFocus = b;
        openZoom(indexOfEvent(b.getAttribute('data-ev')), b.getAttribute('data-ev'));
      });
    });
  }

  function renderLeads() {
    var role = DATA.roles[state.role], obj = DATA.objectives[state.objective];
    var list = leadEvents();
    $('#leads').innerHTML = '<span class="lbl">Leads for <b>' + esc(role.label) + '</b> · ' + esc(obj.label) + '</span>' +
      list.map(function (e, i) {
        return '<button type="button" class="lead-chip" style="animation-delay:' + (i * 60) + 'ms" data-ev="' + e.id + '"><i>' + (i + 1) + '</i>' + esc(e.short) + '</button>';
      }).join('');
    var n = { lead: 0, context: 0, quiet: 0 };
    DATA.events.forEach(function (e) { n[e._sal]++; });
    $('#counts').innerHTML = '<b>' + n.lead + '</b> lead · <b>' + n.context + '</b> context · <b>' + n.quiet + '</b> quiet · ' + DATA.events.length + ' events shown';
    say('Highlights updated for ' + role.label + ', ' + obj.label + '. ' + n.lead + ' lead events.');
  }

  /* ---------- Timeline ---------- */
  function startIndex() {
    for (var i = 0; i < MS.length; i++) if (MS[i].date >= state.start) return i;
    return MS.length;
  }

  function cardInner(m) {
    var ev = m.lead;
    var more = m.events.length - 1;
    var icons = m.events.map(function (e) { return '<span title="' + esc(TYPE_LABEL[e.type]) + '">' + icon(e.type) + '</span>'; }).join('');
    var p = parts(m.date);
    return '<div class="card-main"><div class="swap">' +
      '<h3 class="ttl">' + esc(ev.title) + (ev.flag ? '<span class="flag">' + esc(ev.flag) + '</span>' : '') + '</h3>' +
      '<div class="sub-row"><p class="sub">' + esc(more > 0 ? ev.subtitle + ' · +' + more + ' more' : ev.subtitle) + '</p>' +
      '<div class="ico">' + icons + '</div></div>' +
      '<p class="why"><b>Why it matters for you</b>' + esc(ev._why || '') + '</p></div></div>' +
      '<div class="date-block"><span class="m">' + MONTHS_S[p.m - 1] + '</span><span class="d">' + (p.d < 10 ? '0' : '') + p.d + '</span><span class="y">' + p.y + '</span></div>';
  }

  function nodeLabel(m) {
    var role = DATA.roles[state.role];
    var extra = m.events.length > 1 ? ', and ' + (m.events.length - 1) + ' more event' + (m.events.length > 2 ? 's' : '') : '';
    return longDate(m.date) + ': ' + m.lead.title + extra + '. ' +
      (m.sal === 'lead' ? 'Lead for ' + role.label + '. ' : m.sal === 'quiet' ? 'Background for ' + role.label + '. ' : '') + 'Press to zoom in on this date.';
  }

  function render(initial) {
    closeZoom(true);
    stopStage(mainStage);
    state.startIdx = startIndex();
    var html = '<span class="axis-before"></span><span class="axis-main"></span><span class="axis-done" id="axis-done"></span><span class="walker" id="walker"></span>';
    MS.forEach(function (m, i) {
      if (i === state.startIdx) html += startMarker();
      html += '<div class="ms' + (i < state.startIdx ? ' before shown' : '') + '" data-idx="' + i + '" data-pos="' + (i % 2 === 0 ? 'up' : 'down') + '">' +
        (i > 0 && i !== state.startIdx ? '<span class="gap">' + gapLabel(MS[i - 1].date, m.date) + '</span>' : '') +
        '<span class="stem"></span>' +
        '<article class="card-ms" data-open="' + i + '">' + cardInner(m) + '</article>' +
        '<button type="button" class="node" data-open="' + i + '"><span class="dot"></span></button>' +
        '</div>';
    });
    if (state.startIdx >= MS.length) html += startMarker();
    track.innerHTML = html;

    var mk = track.querySelector('.start');
    var startX = mk ? mk.offsetLeft + mk.offsetWidth / 2 : 0;
    track.style.setProperty('--start-x', startX + 'px');
    updateSalienceDom(false);
    applyFilter();
    updateChips();
    buildTrends();

    var home = mk ? Math.max(0, mk.offsetLeft - 40) : 0;
    rail.scrollTo({ left: home, behavior: (REDUCED || initial) ? 'auto' : 'smooth' });

    var stops = [];
    for (var i = state.startIdx; i < MS.length; i++) {
      var el = track.querySelector('.ms[data-idx="' + i + '"]');
      stops.push({ x: el.offsetLeft + el.offsetWidth / 2, el: el, t: dnum(MS[i].date) });
    }
    mainStage = newStage({
      scroller: rail, walker: $('#walker'), done: $('#axis-done'), startX: startX, home: home,
      stops: stops, dwellMs: DWELL,
      onReach: function (k) {
        stops[k].el.classList.add('active');
        var m = MS[state.startIdx + k];
        say(longDate(m.date) + ': ' + m.lead.title);
      },
      onLeave: function (k) { stops[k].el.classList.remove('active'); }
    });
    stage = mainStage;
    setProgress(mainStage);
    updateCharts(mainDate(mainStage));
    if (REDUCED) revealAll(mainStage);
    else if (!mainStage.finished) { mainStage.hold = 900; mainStage.playing = true; startLoop(); }
    setPlayUi();
  }

  function startMarker() {
    var n = 0;
    for (var i = 0; i < state.startIdx && i < MS.length; i++) n += MS[i].events.length;
    var line = state.startIdx >= MS.length ? 'No events from this date' :
      (n > 0 ? n + ' earlier event' + (n > 1 ? 's' : '') + ' to the left' : 'The story begins here');
    return '<div class="start"><span class="diamond">' + icon('flag') + '</span><div class="label"><small>Requested start</small><b>' + longDate(state.start) + '</b><span>' + line + '</span></div></div>';
  }

  function updateSalienceDom(animate) {
    var els = track.querySelectorAll('.ms');
    for (var i = 0; i < els.length; i++) {
      var idx = +els[i].getAttribute('data-idx');
      var m = MS[idx];
      els[i].setAttribute('data-sal', m.sal);
      if (m.flag) els[i].setAttribute('data-flag', m.flag); else els[i].removeAttribute('data-flag');
      els[i].querySelector('.node').setAttribute('aria-label', nodeLabel(m));
      if (animate) {
        var card = els[i].querySelector('.card-ms');
        card.innerHTML = cardInner(m);
      }
    }
  }

  function applyFilter() {
    var keys = Object.keys(state.types);
    var els = track.querySelectorAll('.ms');
    for (var i = 0; i < els.length; i++) {
      var m = MS[+els[i].getAttribute('data-idx')];
      var hit = keys.length === 0 || m.events.some(function (e) { return state.types[e.type]; });
      els[i].classList.toggle('dim', !hit);
    }
  }

  function updateChips() {
    var chips = document.querySelectorAll('#periods .chip');
    for (var i = 0; i < chips.length; i++) {
      chips[i].setAttribute('aria-pressed', chips[i].getAttribute('data-date') === state.start ? 'true' : 'false');
    }
    $('#start').value = state.start;
  }

  function refresh(animate) {
    evaluate();
    renderSideCards();
    renderLeads();
    updateSalienceDom(animate);
    updateZoomDom();
    renderOverview();
  }

  function setRole(r, resetObjective) {
    state.role = r;
    if (resetObjective) {
      state.objective = DATA.roles[r].defaultObjective;
      $('#objective').value = state.objective;
    }
    var b = document.querySelectorAll('#roles button');
    for (var i = 0; i < b.length; i++) b[i].setAttribute('aria-pressed', b[i].getAttribute('data-role') === r ? 'true' : 'false');
    refresh(true);
  }

  function setStart(date) {
    state.start = date;
    render(false);
  }

  /* ---------- Walker engine (the main story and every zoomed story use it) ---------- */
  function newStage(cfg) {
    var s = {
      scroller: cfg.scroller, walker: cfg.walker, done: cfg.done, startX: cfg.startX, home: cfg.home || 0,
      stops: cfg.stops, dwellMs: cfg.dwellMs, onReach: cfg.onReach, onLeave: cfg.onLeave,
      k: 0, x: cfg.startX, phase: 'move', hold: 0, dwell: 0,
      playing: false, finished: cfg.stops.length === 0, follow: true
    };
    paint(s);
    return s;
  }

  function setProgress(s) {
    var last = s.stops.length ? s.stops[s.stops.length - 1].x : s.startX;
    var span = Math.max(1, last - s.startX);
    $('#progress').style.width = Math.max(0, Math.min(100, ((s.x - s.startX) / span) * 100)) + '%';
  }

  function paint(s) {
    s.walker.style.transform = 'translateX(' + s.x + 'px)';
    s.done.style.width = Math.max(0, s.x - s.startX) + 'px';
    if (stage === s) setProgress(s);
    if (s === mainStage && state.zoomIdx < 0) updateCharts(mainDate(s));
  }

  function followWalker(s) {
    var sc = s.scroller, w = sc.clientWidth, rel = s.x - sc.scrollLeft, want;
    if (rel > w * 0.62) want = s.x - w * 0.62;
    else if (rel < 70) want = Math.max(0, s.x - 70);
    else return;
    var delta = want - sc.scrollLeft;
    sc.scrollLeft = REDUCED || Math.abs(delta) < 1 ? want : sc.scrollLeft + delta * 0.15;
  }

  function advance(s, dt) {
    if (s.hold > 0) { s.hold -= dt * 1000; return; }
    if (s.phase === 'move') {
      var stop = s.stops[s.k];
      var step = REDUCED ? Infinity : SPEED * dt;
      s.walker.classList.remove('at');
      if (s.x + step >= stop.x) {
        s.x = stop.x;
        stop.el.classList.add('shown');
        s.walker.classList.add('at');
        s.phase = 'dwell';
        s.dwell = s.dwellMs;
        if (s.onReach) s.onReach(s.k);
      } else {
        s.x += step;
      }
      paint(s);
      if (s.follow) followWalker(s);
    } else {
      s.dwell -= dt * 1000;
      if (s.dwell > 0) return;
      if (s.onLeave) s.onLeave(s.k);
      s.k++;
      if (s.k >= s.stops.length) {
        s.playing = false;
        s.finished = true;
        setPlayUi();
      } else {
        s.phase = 'move';
      }
    }
  }

  var raf = 0, lastTs = 0;
  function loop(ts) {
    raf = 0;
    var s = stage;
    if (!s || !s.playing) return;
    var dt = Math.max(0, Math.min(0.05, (ts - lastTs) / 1000));
    lastTs = ts;
    advance(s, dt);
    if (stage && stage.playing) raf = requestAnimationFrame(loop);
  }
  function startLoop() {
    if (raf) return;
    lastTs = performance.now();
    raf = requestAnimationFrame(loop);
  }

  function stopStage(s) { if (s) s.playing = false; }

  function resumeStage(s) {
    s.follow = true;
    s.playing = true;
    startLoop();
    setPlayUi();
  }

  function restartStage(s) {
    s.stops.forEach(function (st) { st.el.classList.remove('shown', 'active'); });
    s.k = 0; s.x = s.startX; s.phase = 'move'; s.hold = 400; s.dwell = 0; s.finished = false;
    s.walker.classList.remove('at');
    s.scroller.scrollTo({ left: s.home, behavior: REDUCED ? 'auto' : 'smooth' });
    paint(s);
    resumeStage(s);
  }

  function revealAll(s) {
    s.stops.forEach(function (st) { st.el.classList.add('shown'); st.el.classList.remove('active'); });
    if (s.stops.length) s.x = s.stops[s.stops.length - 1].x;
    s.k = s.stops.length; s.finished = true; s.playing = false;
    s.walker.classList.toggle('at', s.stops.length > 0);
    paint(s);
  }

  function jumpTo(s, k) {
    s.stops.forEach(function (st, j) {
      st.el.classList.remove('active');
      if (j <= k) st.el.classList.add('shown');
    });
    s.x = s.stops[k].x;
    s.k = k + 1; s.phase = 'move'; s.dwell = 0;
    s.finished = s.k >= s.stops.length;
    if (s.finished) s.playing = false;
    s.walker.classList.add('at');
    paint(s);
  }

  function setPlayUi() {
    var s = stage, on = !!(s && s.playing);
    $('#play').setAttribute('aria-pressed', on ? 'true' : 'false');
    $('#play-label').textContent = on ? 'Pause' :
      (!s ? 'Play story' : s.finished ? 'Replay story' : (s.x > s.startX ? 'Resume story' : 'Play story'));
  }

  function togglePlay() {
    var s = stage;
    if (!s || !s.stops.length) return;
    if (s.playing) { s.playing = false; setPlayUi(); }
    else if (s.finished) restartStage(s);
    else resumeStage(s);
  }

  /* ---------- Rail interaction ---------- */
  function enableDrag(el, onUser) {
    var drag = null, moved = false;
    el.addEventListener('wheel', function (e) {
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) { onUser(); return; }
      var max = el.scrollWidth - el.clientWidth;
      if ((e.deltaY > 0 && el.scrollLeft < max) || (e.deltaY < 0 && el.scrollLeft > 0)) {
        el.scrollLeft = Math.max(0, Math.min(max, el.scrollLeft + e.deltaY));
        e.preventDefault();
        onUser();
      }
    }, { passive: false });
    el.addEventListener('pointerdown', function (e) {
      if (e.pointerType !== 'mouse' || e.button !== 0) return;
      drag = { x: e.clientX, left: el.scrollLeft };
      moved = false;
    });
    window.addEventListener('pointermove', function (e) {
      if (!drag) return;
      var dx = e.clientX - drag.x;
      if (Math.abs(dx) > 4) { if (!moved) onUser(); moved = true; el.classList.add('dragging'); }
      if (moved) el.scrollLeft = drag.left - dx;
    });
    window.addEventListener('pointerup', function () {
      if (drag && moved) setTimeout(function () { moved = false; }, 0);
      drag = null;
      el.classList.remove('dragging');
    });
    return function () { return moved; };
  }

  function scrollToIdx(idx) {
    var el = msEl(idx);
    if (!el) return;
    var left = el.offsetLeft + el.offsetWidth / 2 - rail.clientWidth / 2;
    rail.scrollTo({ left: Math.max(0, left), behavior: REDUCED ? 'auto' : 'smooth' });
  }

  function bindRail() {
    var userMoved = function () { if (mainStage) mainStage.follow = false; };
    var wasDragged = enableDrag(rail, userMoved);
    $('#prev').addEventListener('click', function () { userMoved(); rail.scrollBy({ left: -rail.clientWidth * 0.7, behavior: REDUCED ? 'auto' : 'smooth' }); });
    $('#next').addEventListener('click', function () { userMoved(); rail.scrollBy({ left: rail.clientWidth * 0.7, behavior: REDUCED ? 'auto' : 'smooth' }); });

    rail.addEventListener('click', function (e) {
      if (wasDragged()) { e.stopPropagation(); e.preventDefault(); return; }
      var t = e.target.closest('[data-open]');
      if (!t) return;
      var idx = +t.getAttribute('data-open');
      state.lastFocus = track.querySelector('.ms[data-idx="' + idx + '"] .node');
      openZoom(idx, null);
    }, true);

    track.addEventListener('keydown', function (e) {
      var node = e.target.closest('.node');
      if (!node) return;
      var idx = +node.getAttribute('data-open');
      var to = null;
      if (e.key === 'ArrowRight') to = idx + 1;
      else if (e.key === 'ArrowLeft') to = idx - 1;
      else if (e.key === 'Home') to = 0;
      else if (e.key === 'End') to = MS.length - 1;
      if (to === null || to < 0 || to >= MS.length) return;
      e.preventDefault();
      var target = msEl(to);
      if (target && target.classList.contains('shown')) {
        target.querySelector('.node').focus();
        scrollToIdx(to);
      }
    });

    track.addEventListener('mouseover', function (e) { showTip(e.target.closest('.node')); });
    track.addEventListener('mouseout', function (e) { if (e.target.closest('.node')) hideTip(); });
    track.addEventListener('focusin', function (e) { showTip(e.target.closest('.node')); });
    track.addEventListener('focusout', hideTip);
  }

  function showTip(node) {
    if (!node) return;
    var m = MS[+node.getAttribute('data-open')];
    var role = DATA.roles[state.role];
    tip.innerHTML = '<b>' + esc(longDate(m.date)) + '</b>' + esc(m.lead.title) +
      (m.events.length > 1 ? ' · +' + (m.events.length - 1) + ' more' : '') +
      '<small>' + (m.sal === 'lead' ? 'Lead for ' + esc(role.label) + ' · ' : '') + 'Press to zoom in</small>';
    tip.hidden = false;
    var r = node.getBoundingClientRect();
    var w = tip.offsetWidth;
    var left = Math.min(window.innerWidth - w - 12, Math.max(12, r.left + r.width / 2 - w / 2));
    var top = r.top - tip.offsetHeight - 10;
    if (top < 8) top = r.bottom + 10;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }
  function hideTip() { tip.hidden = true; }

  /* ---------- Zoom: a new story line for one date ---------- */
  function msEl(idx) { return track.querySelector('.ms[data-idx="' + idx + '"]'); }

  function ensureShown(idx) {
    if (!mainStage || idx < state.startIdx) return;
    var k = idx - state.startIdx;
    if (!mainStage.stops[k].el.classList.contains('shown')) jumpTo(mainStage, k);
  }

  // Centres the circle in the rail and tells the CSS where the zoom grows from.
  function setOrigin(idx) {
    var el = msEl(idx);
    if (!el) return;
    var max = rail.scrollWidth - rail.clientWidth;
    var left = Math.max(0, Math.min(max, el.offsetLeft + el.offsetWidth / 2 - rail.clientWidth / 2));
    rail.scrollLeft = left;
    wrap.style.setProperty('--ox', (el.offsetLeft + el.offsetWidth / 2 - left) + 'px');
    wrap.style.setProperty('--oy', (rail.clientHeight / 2) + 'px');
  }

  function zcardInner(e) {
    var role = DATA.roles[state.role];
    var why = (e._sal === 'lead' && e._why) ?
      '<p class="whyline"><strong>Why it matters for ' + esc(role.label) + '</strong>' + esc(e._why) + '</p>' : '';
    var details = e.details.length ?
      '<dl>' + e.details.map(function (d) {
        var nd = /^not documented$/i.test(d[1]);
        return '<dt>' + esc(d[0]) + '</dt><dd' + (nd ? ' class="nd"' : '') + '>' + esc(d[1]) + '</dd>';
      }).join('') + '</dl>' :
      '<p class="empty">No further detail in the record.</p>';
    return '<div class="dev-top"><span class="type">' + icon(e.type) + esc(TYPE_LABEL[e.type]) + '</span>' +
      '<span class="sal ' + e._sal + '">' + (e._sal === 'lead' ? 'Lead for ' + esc(role.label) : e._sal === 'quiet' ? 'Background' : 'Context') + '</span></div>' +
      '<h3>' + esc(e.title) + (e.flag ? '<span class="flag">' + esc(e.flag) + '</span>' : '') + '</h3>' +
      '<p class="desc">' + esc(e.description) + '</p>' + why + details +
      '<p class="src"><strong>Source</strong> · ' + esc(e.source.document) + ' · recorded ' + e.source.recorded +
      ' · author ' + (e.source.author ? esc(e.source.author) : 'not documented') + '</p>';
  }

  function fillZoomHead(idx) {
    var m = MS[idx], role = DATA.roles[state.role];
    $('#zoom-kicker').textContent = 'Zoomed in · milestone ' + (idx + 1) + ' of ' + MS.length;
    $('#zoom-title').textContent = longDate(m.date);
    $('#zoom-sub').textContent = m.events.length + (m.events.length === 1 ? ' event' : ' events') +
      ' recorded · time of day not documented · shown for ' + role.label + ' · ' + DATA.objectives[state.objective].label;
    $('#zoom-prev').disabled = idx <= 0;
    $('#zoom-next').disabled = idx >= MS.length - 1;
  }

  function buildZoom(idx, focusId) {
    var m = MS[idx];
    var html = '<span class="z-axis"></span><span class="axis-done"></span><span class="walker"></span>' +
      '<div class="zstart"><span class="diamond">' + icon('flag') + '</span><div class="label"><small>This date</small><b>' + longDate(m.date) +
      '</b><span>' + (m.events.length > 1 ? 'The detail story begins' : 'The detail story') + '</span></div></div>';
    m.events.forEach(function (e, i) {
      html += '<div class="zs" data-i="' + i + '" data-sal="' + e._sal + '"' + (e.flag ? ' data-flag="' + e.flag + '"' : '') +
        (e.id === focusId ? ' data-pick="1"' : '') + '>' +
        '<span class="zstem"></span><span class="znode" aria-hidden="true">' + icon(e.type) + '</span>' +
        '<article class="zcard">' + zcardInner(e) + '</article></div>';
    });
    var zr = $('#zrail');
    var zt = document.createElement('div');
    zt.className = 'ztrack';
    zt.innerHTML = html;
    zr.innerHTML = '';
    zr.appendChild(zt);
    zr.scrollLeft = 0;

    var start = zt.querySelector('.zstart');
    var startX = start.offsetLeft + start.offsetWidth / 2;
    zt.querySelector('.axis-done').style.left = startX + 'px';
    var els = zt.querySelectorAll('.zs');
    var stops = [];
    for (var i = 0; i < els.length; i++) stops.push({ x: els[i].offsetLeft + els[i].offsetWidth / 2, el: els[i] });

    stopStage(zoomStage);
    zoomStage = newStage({
      scroller: zr, walker: zt.querySelector('.walker'), done: zt.querySelector('.axis-done'), startX: startX, home: 0,
      stops: stops, dwellMs: Z_DWELL,
      onReach: function (k) { stops[k].el.classList.add('active'); say(m.events[k].title + '. ' + longDate(m.date)); },
      onLeave: function (k) { stops[k].el.classList.remove('active'); }
    });
    fillZoomHead(idx);
  }

  function updateZoomDom() {
    if (state.zoomIdx < 0) return;
    var m = MS[state.zoomIdx];
    var els = $('#zrail').querySelectorAll('.zs');
    for (var i = 0; i < els.length; i++) {
      var e = m.events[i];
      els[i].setAttribute('data-sal', e._sal);
      els[i].querySelector('.zcard').innerHTML = zcardInner(e);
    }
    fillZoomHead(state.zoomIdx);
  }

  function openZoom(idx, focusId) {
    if (!mainStage) return;
    hideTip();
    var swapping = state.zoomIdx >= 0;
    ensureShown(idx);
    if (!swapping) { state.resumeMain = mainStage.playing; stopStage(mainStage); }
    state.zoomIdx = idx;
    tweenCharts(dnum(MS[idx].date), 600);
    setOrigin(idx);
    buildZoom(idx, focusId);
    stage = zoomStage;
    setProgress(zoomStage);
    zoomStage.hold = swapping ? 450 : 1000;
    if (REDUCED) revealAll(zoomStage);
    else if (!zoomStage.finished) { zoomStage.playing = true; startLoop(); }
    setPlayUi();
    $('#prev').disabled = true;
    $('#next').disabled = true;
    zoom.setAttribute('aria-hidden', 'false');
    wrap.classList.add('zoomed');
    say('Zoomed in on ' + longDate(MS[idx].date) + '. ' + MS[idx].events.length + (MS[idx].events.length === 1 ? ' event.' : ' events.'));
    setTimeout(function () { if (state.zoomIdx >= 0) $('#zoom-back').focus({ preventScroll: true }); }, 140);
  }

  function closeZoom(immediate) {
    if (state.zoomIdx < 0) return;
    var idx = state.zoomIdx;
    state.zoomIdx = -1;
    stopStage(zoomStage);
    zoomStage = null;
    if (!immediate) setOrigin(idx);
    if (!immediate && mainStage) tweenCharts(mainDate(mainStage), 600);
    wrap.classList.remove('zoomed');
    zoom.setAttribute('aria-hidden', 'true');
    $('#prev').disabled = false;
    $('#next').disabled = false;
    stage = mainStage;
    if (mainStage && !immediate) {
      setProgress(mainStage);
      if (state.resumeMain && !mainStage.finished) {
        mainStage.hold = Math.max(mainStage.hold, 800);
        resumeStage(mainStage);
      }
    }
    setPlayUi();
    if (!immediate && state.lastFocus && document.body.contains(state.lastFocus)) state.lastFocus.focus({ preventScroll: true });
  }

  function bindZoom() {
    $('#zoom-back').addEventListener('click', function () { closeZoom(false); });
    $('#zoom-prev').addEventListener('click', function () { if (state.zoomIdx > 0) openZoom(state.zoomIdx - 1, null); });
    $('#zoom-next').addEventListener('click', function () { if (state.zoomIdx < MS.length - 1) openZoom(state.zoomIdx + 1, null); });
    enableDrag($('#zrail'), function () { if (zoomStage) zoomStage.follow = false; });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && state.zoomIdx >= 0) closeZoom(false);
    });
    $('#leads').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-ev]');
      if (!b) return;
      var id = b.getAttribute('data-ev');
      state.lastFocus = b;
      openZoom(indexOfEvent(id), id);
    });
  }

  /* ---------- Trend charts: they draw while the circle walks ---------- */
  var CL = 34, CR = 254, CTOP = 12, CBOT = 44, CAX = 54, CHH = 76, CHW = 260;
  var chart = { t0: 0, t1: 1, T: 0, items: [], tw: 0 };

  function dnum(s) { var p = parts(s); return Date.UTC(p.y, p.m - 1, p.d); }
  function chartX(t) {
    var f = (t - chart.t0) / (chart.t1 - chart.t0);
    return CL + Math.max(0, Math.min(1, f)) * (CR - CL);
  }
  function n1(n) { return (Math.round(n * 10) / 10).toString(); }

  function trendSvg(m, i, rd) {
    var h = '';
    var vals = [];
    rd.forEach(function (r) { r.values.forEach(function (v) { vals.push(v); }); });
    var has = vals.length > 0;
    var vmin = has ? Math.min.apply(null, vals) : 0, vmax = has ? Math.max.apply(null, vals) : 1;
    var lo = vmin, hi = vmax;
    if (hi === lo) { var pad = Math.max(1, Math.abs(hi) * 0.1); lo -= pad; hi += pad; }
    var yy = function (v) { return CBOT - ((v - lo) / (hi - lo)) * (CBOT - CTOP); };

    // grid lines sit on recorded values only
    if (has) {
      var seen = {};
      [vmax, vmin].forEach(function (v) {
        if (seen[v]) return; seen[v] = 1;
        h += '<line class="grid" x1="' + CL + '" x2="' + CR + '" y1="' + n1(yy(v)) + '" y2="' + n1(yy(v)) + '"/>' +
          '<text class="glabel" x="' + (CL - 4) + '" y="' + n1(yy(v) + 3) + '" text-anchor="end">' + v + '</text>';
      });
    } else {
      h += '<line class="flat" x1="' + CL + '" x2="' + CR + '" y1="' + ((CTOP + CBOT) / 2) + '" y2="' + ((CTOP + CBOT) / 2) + '"/>';
    }

    // time axis: end labels, inner years, one tick for every milestone date
    h += '<line class="t-axis" x1="' + CL + '" x2="' + CR + '" y1="' + CAX + '" y2="' + CAX + '"/>';
    var d0 = new Date(chart.t0), d1 = new Date(chart.t1);
    h += '<text class="tick-t" x="' + CL + '" y="' + (CHH - 3) + '" text-anchor="start">' + MONTHS_S[d0.getUTCMonth()] + ' ' + d0.getUTCFullYear() + '</text>';
    h += '<text class="tick-t" x="' + CR + '" y="' + (CHH - 3) + '" text-anchor="end">' + MONTHS_S[d1.getUTCMonth()] + ' ' + d1.getUTCFullYear() + '</text>';
    for (var y = d0.getUTCFullYear() + 1; y <= d1.getUTCFullYear(); y++) {
      var tx = chartX(Date.UTC(y, 0, 1));
      if (tx < CL + 50 || tx > CR - 50) continue;
      h += '<line class="t-yr" x1="' + n1(tx) + '" x2="' + n1(tx) + '" y1="' + CAX + '" y2="' + (CAX + 4) + '"/>' +
        '<text class="tick-t" x="' + n1(tx) + '" y="' + (CHH - 3) + '" text-anchor="middle">' + y + '</text>';
    }
    MS.forEach(function (ms) {
      var t = dnum(ms.date);
      if (t < chart.t0) return;
      h += '<line class="t-ev" data-t="' + t + '" x1="' + n1(chartX(t)) + '" x2="' + n1(chartX(t)) + '" y1="' + (CAX - 3) + '" y2="' + (CAX + 3) + '"/>';
    });

    if (!has) {
      h += '<line class="cursor" x1="' + CL + '" x2="' + CL + '" y1="6" y2="' + CAX + '"/>';
      return h;
    }

    var inWin = rd.filter(function (r) { return dnum(r.date) >= chart.t0; });
    var lines = 0;
    inWin.forEach(function (r) { lines = Math.max(lines, r.values.length); });
    var ghost = '', live = '';
    if (inWin.length >= 2) {
      for (var j = 0; j < lines; j++) {
        var pts = inWin.filter(function (r) { return r.values[j] !== undefined; });
        var path = pts.map(function (r, k) { return (k ? 'L' : 'M') + n1(chartX(dnum(r.date))) + ' ' + n1(yy(r.values[j])); }).join(' ');
        ghost += '<path class="ghost" d="' + path + '"/>';
        if (lines === 1) {
          live += '<path class="area" d="' + path + ' L' + n1(chartX(dnum(pts[pts.length - 1].date))) + ' ' + CAX + ' L' + n1(chartX(dnum(pts[0].date))) + ' ' + CAX + ' Z"/>';
        }
        live += '<path class="live-line' + (j ? ' second' : '') + '" d="' + path + '"/>';
      }
    }
    inWin.forEach(function (r) {
      var x = n1(chartX(dnum(r.date)));
      if (r.values.length === 2 && (inWin.length < 2 || !r.synthetic)) {
        ghost += '<line class="ghost" x1="' + x + '" x2="' + x + '" y1="' + n1(yy(r.values[0])) + '" y2="' + n1(yy(r.values[1])) + '"/>';
        live += '<line class="bar" x1="' + x + '" x2="' + x + '" y1="' + n1(yy(r.values[0])) + '" y2="' + n1(yy(r.values[1])) + '"/>';
      }
      r.values.forEach(function (v) {
        ghost += '<circle class="ghost-dot" cx="' + x + '" cy="' + n1(yy(v)) + '" r="4.5"/>';
        live += '<circle class="pt' + (r.synthetic ? ' syn' : '') + '" cx="' + x + '" cy="' + n1(yy(v)) + '" r="4.5"/>';
      });
    });
    h += ghost +
      '<clipPath id="cl-' + i + '"><rect class="clr" x="0" y="0" width="0" height="' + CHH + '"/></clipPath>' +
      '<g clip-path="url(#cl-' + i + ')">' + live + '</g>' +
      '<line class="cursor" x1="' + CL + '" x2="' + CL + '" y1="6" y2="' + CAX + '"/>';
    return h;
  }

  function buildTrends() {
    var byId = {};
    DATA.events.forEach(function (e) { byId[e.id] = e; });
    chart.t0 = dnum(state.start);
    chart.t1 = dnum(MS[MS.length - 1].date);
    if (chart.t1 <= chart.t0) chart.t1 = chart.t0 + 30 * 86400000;
    $('#trends').innerHTML = DATA.measures.map(function (m, i) {
      var rd = (m.readings || []).slice().sort(function (a, b) { return a.date < b.date ? -1 : 1; });
      var nSyn = rd.filter(function (r) { return r.synthetic; }).length;
      var tag = !nSyn ? '' : nSyn === rd.length ? 'Sample' : 'Sample + record';
      var svg = '<svg viewBox="0 0 260 ' + CHH + '" role="img" aria-label="' + esc(m.label) + (rd.length ? (nSyn ? ' over the story, sample readings' : ' over the story') : ': not documented') + '">' + trendSvg(m, i, rd) + '</svg>';
      var head = '<div class="trend-head"><span class="trend-name">' + esc(m.label) + (tag ? '<i class="tag">' + tag + '</i>' : '') + '</span><span class="trend-val"></span></div>';
      if (!m.ev) return '<div class="trend' + (rd.length ? '' : ' missing') + '" role="group" aria-label="' + esc(m.label) + (rd.length ? ': sample readings' : ': not documented') + '">' + head + svg + '</div>';
      return '<button type="button" class="trend" data-ev="' + m.ev + '" aria-label="' + esc(m.label + ' ' + m.value + ', recorded ' + m.date + '. Zoom in on this date') + '">' + head + svg + '</button>';
    }).join('');
    $('#trends-note').textContent = DATA.readingsNote || '';
    chart.items = [];
    var els = $('#trends').children;
    for (var i = 0; i < els.length; i++) {
      var m2 = DATA.measures[i];
      var rd2 = (m2.readings || []).map(function (r) { return { t: dnum(r.date), text: r.text }; }).sort(function (a, b) { return a.t - b.t; });
      chart.items.push({
        root: els[i], readings: rd2, missing: !rd2.length,
        cur: els[i].querySelector('.cursor'), clr: els[i].querySelector('.clr'), val: els[i].querySelector('.trend-val'),
        ticks: [].slice.call(els[i].querySelectorAll('.t-ev')).map(function (t) { return { el: t, t: +t.getAttribute('data-t') }; })
      });
    }
    markTrendLeads();
    updateCharts(chart.t0);
  }

  function markTrendLeads() {
    var els = document.querySelectorAll('.trend[data-ev]');
    for (var i = 0; i < els.length; i++) {
      var id = els[i].getAttribute('data-ev');
      var ev = DATA.events.filter(function (e) { return e.id === id; })[0];
      els[i].classList.toggle('lead', !!ev && ev._sal === 'lead');
    }
  }

  function updateCharts(T) {
    chart.T = T;
    var cx = n1(chartX(T));
    chart.items.forEach(function (it) {
      it.cur.setAttribute('x1', cx);
      it.cur.setAttribute('x2', cx);
      if (it.clr) it.clr.setAttribute('width', n1(Math.min(CHW, +cx + 6)));
      for (var k = 0; k < it.ticks.length; k++) it.ticks[k].el.classList.toggle('on', it.ticks[k].t <= T);
      var last = null;
      it.readings.forEach(function (r) { if (r.t <= T) last = r; });
      it.root.classList.toggle('reached', !!last);
      it.val.textContent = it.missing ? 'Not documented' : (last ? last.text : 'No reading yet');
    });
  }

  function tweenCharts(toT, ms) {
    cancelAnimationFrame(chart.tw);
    if (REDUCED || ms <= 0 || chart.T === toT) { updateCharts(toT); return; }
    var from = chart.T, t0 = performance.now();
    (function step(now) {
      var f = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - f, 3);
      updateCharts(from + (toT - from) * e);
      if (f < 1) chart.tw = requestAnimationFrame(step);
    })(t0);
  }

  // The circle's place on the line becomes a date: a straight blend between milestone dates.
  function mainDate(s) {
    var n = s.stops.length;
    if (!n) return chart.t1;
    var px = s.startX, pt = chart.t0;
    for (var i = 0; i < n; i++) {
      var st = s.stops[i];
      if (s.x <= st.x) {
        var span = st.x - px;
        return pt + (st.t - pt) * (span > 0 ? Math.max(0, (s.x - px) / span) : 1);
      }
      px = st.x; pt = st.t;
    }
    return pt;
  }

  /* ---------- Light and dark ---------- */
  function bindTheme() {
    var btn = $('#theme'), root = document.documentElement;
    function apply(t, save) {
      root.setAttribute('data-theme', t);
      btn.setAttribute('aria-checked', t === 'dark' ? 'true' : 'false');
      if (save) { try { localStorage.setItem('perspective-theme', t); } catch (e) { /* storage unavailable */ } }
    }
    apply(root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light', false);
    btn.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      apply(next, true);
      say((next === 'dark' ? 'Dark' : 'Light') + ' mode on.');
    });
    var mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    if (mq && mq.addEventListener) {
      mq.addEventListener('change', function (e) {
        var saved = null;
        try { saved = localStorage.getItem('perspective-theme'); } catch (err) { /* ignore */ }
        if (!saved) apply(e.matches ? 'dark' : 'light', false);
      });
    }
  }

  /* ---------- Patient overview: an AR-style panel (added below the story) ---------- */
  var ovOpen = {};
  /* A soft-shaded, front-view mannequin drawn as SVG (no organs, no arteries). */
  var FW = 240;
  function mx(x) { return +(FW - x).toFixed(2); }
  // Build a closed, left-right symmetric outline from its left half.
  // half = { s: [x, y], c: [[c1x, c1y, c2x, c2y, x, y], ...] }, the last point lies on the centre line.
  function fullOutline(half) {
    var pts = [half.s], d = 'M' + half.s.join(' ');
    half.c.forEach(function (g) { d += 'C' + g.join(' '); pts.push([g[4], g[5]]); });
    for (var i = half.c.length - 1; i >= 0; i--) {
      var g = half.c[i], p = pts[i];
      d += 'C' + mx(g[2]) + ' ' + g[3] + ' ' + mx(g[0]) + ' ' + g[1] + ' ' + mx(p[0]) + ' ' + p[1];
    }
    return d + 'Z';
  }
  // Mirror an absolute path (M, L, C, Q, Z with number pairs) across the centre line.
  function mirrorPath(d) {
    return d.replace(/(-?\d+(?:\.\d+)?)[ ,](-?\d+(?:\.\d+)?)/g, function (m, x, y) { return mx(+x) + ' ' + y; });
  }

  var HEAD = { s: [120, 5], c: [[107, 5, 100, 15, 100, 29], [100, 41, 101, 49, 105, 55], [109, 62, 114, 66, 120, 66]] };
  var NECK = { s: [120, 54], c: [[114, 54, 111, 57, 111, 62], [110.5, 70, 110, 76, 108, 82], [112, 84, 116, 85, 120, 85]] };
  var TORSO = { s: [120, 82], c: [[108, 82, 96, 85, 84, 90], [76, 93, 70, 99, 70, 110], [72, 126, 74, 142, 78, 156], [82, 172, 88, 186, 88, 204], [88, 216, 82, 226, 82, 240], [92, 252, 108, 257, 120, 257]] };
  var LEG = 'M119 252C119 290 117 320 114 350C113 362 113 372 113 382C108 400 113 440 112 490' +
    'C112 500 115 508 117 516C119 526 120 534 115 539C107 545 96 545 91 537C86 530 89 516 92 500' +
    'C95 480 96 450 91 420C86 396 88 372 90 355C92 335 80 300 80 270C80 255 80 245 83 236C90 240 105 246 119 252Z';
  var ARM = 'M80 90C70 90 60 95 57 108C53 122 50 140 48 160C47 170 44 180 42 192C39 208 35 222 32 238' +
    'C29 250 26 262 25 272C24 282 26 290 30 294C34 297 39 296 42 290C45 284 46 272 47 260' +
    'C48 252 47 246 47 240C50 224 56 206 60 190C62 178 64 168 66 160C69 148 72 138 75 126C76 118 77 108 78 100Z';
  var TL = 'translate(0 252) scale(1 .84) translate(0 -252)'; // shortens the legs
  var EAR = 'M100 30C95 28 94 36 96 41C97 44 99 45 100 44Z';


  function bodyParts() {
    return '<path d="' + fullOutline(HEAD) + '"/><path d="' + fullOutline(NECK) + '"/><path d="' + fullOutline(TORSO) + '"/>' +
      '<path transform="' + TL + '" d="' + LEG + '"/><path transform="' + TL + '" d="' + mirrorPath(LEG) + '"/>' +
      '<path d="' + ARM + '"/><path d="' + mirrorPath(ARM) + '"/>' +
      '<path d="' + EAR + '"/><path d="' + mirrorPath(EAR) + '"/>';
  }
  // soft shadow / highlight strokes: list the left half, the right half is mirrored
  function softStroke(d, w, cls) {
    return '<path class="' + cls + '" stroke-width="' + w + '" d="' + d + '"/><path class="' + cls + '" stroke-width="' + w + '" d="' + mirrorPath(d) + '"/>';
  }
  function bodyDetails() {
    var S = softStroke, s = '';
    // chest, ribs, belly
    s += S('M119 142C108 150 92 149 80 134', 4.5, 'sh a');                    // under the pecs
    s += S('M84 104C94 109 108 109 118 103', 3.4, 'hi a');                    // upper chest
    s += S('M118 93C106 91 94 93 83 99', 2, 'sh b');                          // collarbone
    s += S('M118 98C106 96 95 98 86 103', 2, 'hi b');
    s += '<path class="sh a" stroke-width="2.4" d="M120 102L120 150"/>';      // breastbone
    s += '<path class="sh b" stroke-width="2.4" d="M109 160Q120 163 131 160"/><path class="sh b" stroke-width="2.4" d="M109 175Q120 178 131 175"/>' +
      '<path class="sh b" stroke-width="2.4" d="M110 190Q120 193 130 190"/><path class="sh b" stroke-width="2.2" d="M120 150L120 206"/>';
    s += S('M104 152C103 170 104 190 108 206', 3, 'sh b');                    // rectus edge
    s += S('M82 150C84 166 90 182 92 204', 3.6, 'sh a');                      // ribs and side
    s += '<ellipse class="sh a" cx="120" cy="198" rx="2" ry="2.6"/>';
    s += S('M90 222C98 238 110 248 120 255', 4, 'sh a');                      // hip crease
    s += S('M94 214C100 226 108 234 118 238', 3, 'hi b');
    // arms
    s += S('M76 112C74 124 74 140 72 152', 4, 'sh a');                        // armpit side
    s += S('M63 104C58 112 56 124 55 140', 4, 'hi a');                        // shoulder
    s += S('M70 140C67 152 64 164 63 176', 3.6, 'sh a');                      // inner upper arm
    s += S('M51 150C50 164 48 176 46 186', 3, 'sh b');                        // outer upper arm
    s += S('M50 196C47 208 43 220 40 232', 3.4, 'hi a');                      // forearm
    s += S('M57 198C54 212 51 226 49 238', 3, 'sh a');
    // head and neck
    s += '<ellipse class="sh b" cx="120" cy="69" rx="12" ry="4"/>';           // jaw shadow on the neck
    s += S('M113 70C112 76 110 82 108 86', 5, 'sh a');                        // neck sides
    s += S('M104 44C106 54 112 61 120 62', 3, 'sh a');                        // jaw line
    s += S('M104 14C108 10 114 8 120 8', 4, 'hi a');                          // crown highlight
    return s;
  }
  function crispDetails() {
    var S = softStroke, s = '';
    s += S('M30 262C29 270 28 278 28 286', 1.3, 'sh a') + S('M34 264C34 272 34 280 34 290', 1.3, 'sh a') +
      S('M38 262C38 270 38 278 39 288', 1.3, 'sh a') + S('M43 256C43 262 43 268 43 274', 1.3, 'sh a');
    s += '<ellipse class="sh a" cx="111" cy="33" rx="4.2" ry="1.9"/><ellipse class="sh a" cx="129" cy="33" rx="4.2" ry="1.9"/>'; // eye sockets
    s += S('M105 28C108 27 112 27 115 28', 1.3, 'sh b');                       // brows
    s += S('M118 34C117 40 116 44 115 46C117 48 119 48 120 48', 1.4, 'sh a');  // nose
    s += S('M114 56C117 57 119 57 120 57', 1.5, 'sh a');                       // mouth
    return s;
  }
  function legDetails() {
    var S = softStroke, s = '';
    s += S('M94 262C92 290 92 318 96 346', 5, 'hi a');                        // thigh highlight
    s += S('M108 270C109 296 108 322 106 344', 4, 'sh b');                    // inner quad edge
    s += S('M86 262C84 290 88 320 92 348', 4, 'sh b');                        // outer thigh
    s += S('M100 352C98 358 100 366 104 372', 4, 'sh a');                     // knee
    s += S('M95 356C94 362 96 368 99 372', 3, 'hi b');
    s += S('M97 384C95 404 99 424 101 442', 5, 'hi a');                       // shin
    s += S('M92 386C90 408 92 430 96 448', 3.4, 'sh b');                      // calf
    s += S('M108 384C106 408 109 440 109 482', 3, 'sh b');
    s += S('M97 524C102 528 108 528 113 524', 2, 'sh b') + S('M101 534C104 536 108 536 111 533', 1.6, 'sh b');
    return s;
  }

  function buildFigure() {
    var u = bodyParts();
    $('#ar-fig').innerHTML =
      '<svg class="fig-svg" viewBox="0 0 240 520" role="img" aria-label="Body outline. A marker on the chest shows where chest pain was recorded.">' +
      '<defs>' +
      '<linearGradient id="skin" x1="0" y1="0" x2="1" y2="0"><stop class="g0" offset="0"/><stop class="g1" offset="0.3"/><stop class="g2" offset="0.55"/><stop class="g3" offset="1"/></linearGradient>' +
      '<linearGradient id="skinv" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="520"><stop class="v0" offset="0"/><stop class="v1" offset="1"/></linearGradient>' +
      '<linearGradient id="lite" gradientUnits="userSpaceOnUse" x1="30" y1="0" x2="210" y2="0"><stop class="l0" offset="0"/><stop class="l1" offset="0.55"/><stop class="l2" offset="1"/></linearGradient>' +
      '<linearGradient id="scang" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="80"><stop class="sc" offset="0" stop-opacity="0"/><stop class="sc" offset="0.6" stop-opacity="0.55"/><stop class="sc" offset="1" stop-opacity="0"/></linearGradient>' +
      '<filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2"/></filter>' +
      '<filter id="crisp" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="0.7"/></filter>' +
      '<filter id="floor" x="-30%" y="-300%" width="160%" height="700%"><feGaussianBlur stdDeviation="6"/></filter>' +
      '<clipPath id="bodyclip">' + u + '</clipPath>' +
      '</defs>' +
      '<ellipse class="floor" cx="120" cy="505" rx="62" ry="7" filter="url(#floor)"/>' +
      '<g class="body" transform="translate(120 0) scale(1.15 1) translate(-120 0)"><g class="parts" fill="url(#skin)">' + u + '</g>' +
      '<g clip-path="url(#bodyclip)">' +
      '<rect x="0" y="0" width="240" height="520" fill="url(#skinv)"/>' +
      '<g class="soft" filter="url(#soft)">' + bodyDetails() + '<g transform="' + TL + '">' + legDetails() + '</g></g><g class="soft" filter="url(#crisp)">' + crispDetails() + '</g>' +
      '<rect x="0" y="0" width="240" height="520" fill="url(#lite)"/>' +
      '<rect class="scan" x="0" y="-80" width="240" height="80" fill="url(#scang)"/>' +
      '</g></g></svg>' +
      '<button type="button" class="ar-marker" id="ar-marker" aria-label="Chest. Chest pain recorded 2026-03-12. Open in the story">' +
      '<span class="ring"></span><span class="core"></span></button>' +
      '<span class="ar-marker-tag" aria-hidden="true">Chest</span>';
  }

  function ovItems(list, emptyText) {
    if (!list.length) return '<p class="nd">' + esc(emptyText || 'Not documented') + '</p>';
    return list.map(function (e) {
      return '<button type="button" class="ar-item' + (e._sal === 'lead' ? ' lead' : '') + (e.flag ? ' flagged' : '') + '" data-ev="' + e.id + '">' +
        '<span class="d">' + e.date + '</span>' +
        '<span class="t">' + esc(e.title) + (e._sal === 'lead' ? '<i class="lead-tag">Lead</i>' : '') + '</span>' +
        '<span class="s">' + esc(e.source.document) + '</span></button>';
    }).join('');
  }

  function ovAcc(key, label, list, emptyText) {
    var open = !!ovOpen[key];
    return '<div class="acc glass' + (open ? ' open' : '') + '" data-key="' + key + '">' +
      '<button type="button" class="acc-h" aria-expanded="' + open + '" aria-controls="acc-' + key + '">' +
      '<span class="lbl">' + esc(label) + '</span>' +
      (list && list.length ? '<span class="n">(' + list.length + ')</span>' : '<span class="n nd">Not documented</span>') +
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></button>' +
      '<div class="acc-p" id="acc-' + key + '"><div class="acc-in">' + ovItems(list || [], emptyText) + '</div></div></div>';
  }

  function byDate(a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; }
  function ofType() {
    var t = [].slice.call(arguments);
    return DATA.events.filter(function (e) { return t.indexOf(e.type) >= 0; }).sort(byDate);
  }
  function detail(e, label) {
    var d = e.details.filter(function (x) { return x[0] === label; })[0];
    return d ? d[1] : null;
  }

  function renderOverview() {
    if (!$('#ar-left') || !DATA) return;
    var role = DATA.roles[state.role], obj = DATA.objectives[state.objective], p = DATA.patient;
    $('#ar-patient').innerHTML = '<span class="av">' + esc(p.initials) + '</span><div><b>' + esc(p.name) + '</b><small>' + p.age + ' · ' + esc(p.sex.charAt(0).toUpperCase() + p.sex.slice(1)) + '</small></div>';
    $('#ar-role').innerHTML = '<small>Viewing as</small><b>' + esc(role.label) + '</b><span>' + esc(obj.label) + '</span>';

    // the callout that the marker points to
    var reason = DATA.events.filter(function (e) { return e.tags.indexOf('reason') >= 0 && e.type === 'admission'; })[0];
    var symptom = DATA.events.filter(function (e) { return e.tags.indexOf('symptom') >= 0; })[0];
    var call = '';
    if (reason) {
      var why = reason._sal === 'lead' && reason._why ? '<p class="ar-why"><b>Why it matters for ' + esc(role.label) + '</b>' + esc(reason._why) + '</p>' : '';
      call = '<article class="ar-call glass" id="ar-call" data-ev="' + reason.id + '" tabindex="0" role="button" aria-label="Chest pain, admitted ' + reason.date + '. Open in the story">' +
        '<p class="ar-k">Chest pain</p><p class="ar-date">' + reason.date + ' · ' + esc(reason.source.document) + '</p>' +
        '<ul><li><b>Reason for admission</b><span>' + esc(detail(reason, 'Reason for admission') || 'Not documented') + '</span></li>' +
        (symptom ? '<li><b>Symptoms</b><span>' + esc(detail(symptom, 'Symptoms') || 'Not documented') + '</span><em>' + esc(symptom.source.document) + ' · ' + symptom.date + '</em></li>' : '') +
        '</ul>' + why + '</article>';
    }
    $('#ar-left').innerHTML = call +
      ovAcc('history', 'Medical history', ofType('diagnosis', 'procedure')) +
      ovAcc('allergies', 'Allergies', ofType('allergy')) +
      ovAcc('immun', 'Immunizations', [], 'Not documented');
    $('#ar-right').innerHTML =
      ovAcc('meds', 'Current medications', ofType('medication')) +
      ovAcc('plan', 'Treatment plan', [], 'Not documented') +
      ovAcc('labs', 'Lab results', ofType('lab')) +
      ovAcc('notes', 'Notes', ofType('note'));
    drawLeader();
  }

  function stagePos(el, stage) {
    var x = 0, y = 0;
    while (el && el !== stage) { x += el.offsetLeft; y += el.offsetTop; el = el.offsetParent; }
    return { x: x, y: y };
  }
  function drawLeader() {
    var stage = $('#ar-stage'), mk = $('#ar-marker'), call = $('#ar-call'), path = $('#ar-leader'), dot = $('#ar-leader-dot');
    if (!stage || !mk || !call || window.innerWidth <= 1180) { if (path) { path.setAttribute('d', ''); dot.setAttribute('r', 0); } return; }
    var a = stagePos(mk, stage), b = stagePos(call, stage);
    var x1 = a.x + mk.offsetWidth / 2, y1 = a.y + mk.offsetHeight / 2;
    var x2 = b.x + call.offsetWidth, y2 = b.y + Math.min(call.offsetHeight / 2, 70);
    var dy = y1 - y2, x3 = Math.max(x2 + 24, x1 - Math.abs(dy) * 0.55);
    path.setAttribute('d', 'M' + x1 + ' ' + y1 + ' L' + x3 + ' ' + y2 + ' L' + x2 + ' ' + y2);
    var len = path.getTotalLength();
    path.style.setProperty('--len', len);
    dot.setAttribute('cx', x2); dot.setAttribute('cy', y2); dot.setAttribute('r', 3.5);
  }

  function openFromOverview(id, trigger) {
    state.lastFocus = trigger;
    var tl = document.getElementById('timeline');
    if (tl) tl.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' });
    setTimeout(function () { openZoom(indexOfEvent(id), id); }, REDUCED ? 0 : 450);
  }

  function bindOverview() {
    var root = $('#overview');
    if (!root) return;
    buildFigure();
    root.addEventListener('click', function (e) {
      var acc = e.target.closest('.acc-h');
      if (acc) {
        var box = acc.parentNode, key = box.getAttribute('data-key');
        ovOpen[key] = !ovOpen[key];
        box.classList.toggle('open', ovOpen[key]);
        acc.setAttribute('aria-expanded', ovOpen[key] ? 'true' : 'false');
        return;
      }
      var t = e.target.closest('[data-ev]');
      if (t) { openFromOverview(t.getAttribute('data-ev'), t); return; }
      var mk = e.target.closest('#ar-marker');
      if (mk) { var c = $('#ar-call'); if (c) openFromOverview(c.getAttribute('data-ev'), mk); }
    });
    root.addEventListener('keydown', function (e) {
      var c = e.target.closest && e.target.closest('#ar-call');
      if (c && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); openFromOverview(c.getAttribute('data-ev'), c); }
    });
    var hot = function (on) { var c = $('#ar-call'), p = $('#ar-leader'); if (c) c.classList.toggle('hot', on); if (p) p.classList.toggle('hot', on); };
    root.addEventListener('mouseover', function (e) { if (e.target.closest('#ar-marker')) hot(true); });
    root.addEventListener('mouseout', function (e) { if (e.target.closest('#ar-marker')) hot(false); });
    root.addEventListener('focusin', function (e) { if (e.target.closest('#ar-marker')) hot(true); });
    root.addEventListener('focusout', function (e) { if (e.target.closest('#ar-marker')) hot(false); });

    var enter = function () { root.classList.add('in'); setTimeout(drawLeader, 60); };
    if (REDUCED || !('IntersectionObserver' in window)) enter();
    else {
      var io = new IntersectionObserver(function (es) {
        if (es.some(function (x) { return x.isIntersecting; })) { enter(); io.disconnect(); }
      }, { threshold: 0.2 });
      io.observe(root);
    }
    var rz;
    window.addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(drawLeader, 120); });
  }

  /* ---------- Start ---------- */
  function init(data) {
    DATA = data;
    rail = $('#rail'); track = $('#track'); tip = $('#tip'); wrap = $('#rail-wrap'); zoom = $('#zoom');
    buildMilestones();
    state.start = DATA.requestedStart;
    renderPatient();
    renderSummary();
    renderMeasures();
    renderControls();
    bindSideCards();
    bindRail();
    bindZoom();
    bindTheme();
    bindOverview();
    $('#play').addEventListener('click', togglePlay);
    evaluate();
    render(true);
    setRole('physician', true);
    // Re-render once so the first paint is already ranked for the default role.
    updateSalienceDom(true);
  }

  loadData().then(init).catch(function (err) {
    document.body.insertAdjacentHTML('afterbegin', '<p style="padding:24px;color:#be123c">Could not load the patient data: ' + esc(err.message) + '</p>');
  });
})();
