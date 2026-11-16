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
    var byId = {};
    DATA.events.forEach(function (e) { byId[e.id] = e; });
    $('#measures').innerHTML = DATA.measures.map(function (m) {
      if (!m.ev) {
        return '<div class="tile missing"><div class="n">' + esc(m.label) + '</div><div class="v">Not documented</div><div class="one"></div><div class="f">&nbsp;</div></div>';
      }
      var ev = byId[m.ev];
      return '<button type="button" class="tile" data-ev="' + ev.id + '" aria-label="' + esc(m.label + ' ' + m.value + ', recorded ' + m.date + '. Zoom in on this date') + '">' +
        '<div class="n">' + esc(m.label) + '</div><div class="v">' + esc(m.value) + '</div>' +
        '<div class="one"><b></b></div><div class="f">1 reading · ' + m.date.slice(5) + '</div></button>';
    }).join('');
    $('#measures').addEventListener('click', function (e) {
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
    var tiles = document.querySelectorAll('.tile[data-ev]');
    for (var i = 0; i < tiles.length; i++) {
      var ev = DATA.events.filter(function (e) { return e.id === tiles[i].getAttribute('data-ev'); })[0];
      tiles[i].classList.toggle('lead', ev._sal === 'lead');
    }
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

    var home = mk ? Math.max(0, mk.offsetLeft - 40) : 0;
    rail.scrollTo({ left: home, behavior: (REDUCED || initial) ? 'auto' : 'smooth' });

    var stops = [];
    for (var i = state.startIdx; i < MS.length; i++) {
      var el = track.querySelector('.ms[data-idx="' + i + '"]');
      stops.push({ x: el.offsetLeft + el.offsetWidth / 2, el: el });
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
