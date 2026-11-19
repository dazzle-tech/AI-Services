/* Synopsis: anatomical 3D body.
 *
 * Renders the packed "Human Muscles" model (Grab3D, CC0 1.0, see models/body-muscles.js and
 * tools/pack_body.py) as a translucent, blue-rimmed anatomical figure. The model is one mesh,
 * so body areas are assigned per vertex from landmark heights (classify) and highlighted in the
 * shader. A coarse proxy mesh built at load time serves ray picking.
 *
 *   window.PerspectiveBody.create(container, {
 *     theme, reduced, flagged: ['chest'], anchors: { chest: [x, y] }, label,
 *     onAnchors(map), onView(name), onHover(part, x, y, changed), onPick(part, x, y), onFail(reason)
 *   }) -> { setTheme, setFlagged, setSelected, setActive, rotateBy, snapTo, view, label, canvas }
 *
 * Returns null when WebGL, the packed model or gzip decoding is unavailable (the page then
 * draws its flat figure).
 */
(function () {
  'use strict';
  var T = window.THREE;
  if (!T) return;
  var PI = Math.PI, TAU = PI * 2, H = PI / 2;

  var LABELS = {
    head: 'Head', neck: 'Neck', chest: 'Chest', upperBack: 'Upper back', abdomen: 'Abdomen', lowerBack: 'Lower back',
    pelvis: 'Pelvis', buttocks: 'Buttocks', upperArmL: 'Left upper arm', upperArmR: 'Right upper arm',
    forearmL: 'Left forearm', forearmR: 'Right forearm', handL: 'Left hand', handR: 'Right hand',
    thighL: 'Left thigh', thighR: 'Right thigh', shinL: 'Left lower leg', shinR: 'Right lower leg',
    footL: 'Left foot', footR: 'Right foot'
  };
  var PART_IDS = Object.keys(LABELS);
  var PART_INDEX = {};
  PART_IDS.forEach(function (id, i) { PART_INDEX[id] = i + 1; });

  function wrapAngle(a) { a = (a + PI) % TAU; if (a < 0) a += TAU; return a - PI; }

  /* ---------- body areas from landmark heights (metres; the model is 1.80 m tall, +x = patient's left) ---------- */
  function classify(x, y, z) {
    var ax = Math.abs(x), side = x >= 0 ? 'L' : 'R';
    if (y > 1.60 || (y > 1.55 && z > 0.02)) return 'head';
    if ((y > 1.50 && ax < 0.12) || (y > 1.46 && ax < 0.075)) return 'neck';
    var edge = y > 1.35 ? 0.215 : y > 1.2 ? 0.215 + (1.35 - y) / 0.15 * 0.02 : 0.235;
    if (ax > edge && y > 0.70) {
      if (y > 1.13) return 'upperArm' + side;
      if (y > 0.97) return 'forearm' + side;
      return 'hand' + side;
    }
    var back = z < -0.035;
    if (y > 0.85 || (y > 0.78 && z < -0.05)) {
      if (y > 1.17) return back ? 'upperBack' : 'chest';
      if (y > 0.99) return back ? 'lowerBack' : 'abdomen';
      return back ? 'buttocks' : 'pelvis';
    }
    if (y > 0.50) return 'thigh' + side;
    if (y > 0.10) return 'shin' + side;
    return 'foot' + side;
  }

  /* ---------- decoding the packed model ---------- */
  var modelPromise = null;
  function loadModel() {
    if (modelPromise) return modelPromise;
    modelPromise = new Promise(function (resolve, reject) {
      var b64 = window.PERSPECTIVE_BODY_B64;
      if (!b64) { reject(new Error('model missing')); return; }
      var bin = atob(b64), u8 = new Uint8Array(bin.length), i;
      for (i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
      new Response(new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer().then(function (buf) {
        resolve(parse(buf));
      }, reject);
    });
    return modelPromise;
  }
  function pad4(n) { return (n + 3) & ~3; }
  function parse(buf) {
    var dv = new DataView(buf), hl = dv.getUint32(0, true);
    var head = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hl)));
    var n = head.count, o = 4 + hl;
    var q = new Int16Array(buf, o, n * 3); o += pad4(n * 6);
    var nrm = new Int8Array(buf, o, n * 3); o += pad4(n * 3);
    var tone = new Uint8Array(buf, o, n); o += pad4(n);
    var idx = new Uint32Array(buf, o, head.index);
    var pos = new Float32Array(n * 3), part = new Uint8Array(n), i, k;
    var mn = head.min, mx = head.max, sx = (mx[0] - mn[0]) / 65535, sy = (mx[1] - mn[1]) / 65535, sz = (mx[2] - mn[2]) / 65535;
    for (i = 0, k = 0; i < n; i++, k += 3) {
      var x = (q[k] + 32768) * sx + mn[0], y = (q[k + 1] + 32768) * sy + mn[1], z = (q[k + 2] + 32768) * sz + mn[2];
      pos[k] = x; pos[k + 1] = y; pos[k + 2] = z;
      part[i] = PART_INDEX[classify(x, y, z)];
    }
    return { count: n, pos: pos, nrm: nrm, tone: tone, idx: idx, part: part, proxy: buildProxy(pos, idx, 0.016) };
  }
  /* vertex clustering: a light copy of the surface that keeps ray picking fast */
  function buildProxy(pos, idx, cell) {
    var map = new Map(), n = pos.length / 3, remap = new Int32Array(n), sums = [], i, id;
    for (i = 0; i < n; i++) {
      var ix = Math.round(pos[i * 3] / cell) + 128, iy = Math.round(pos[i * 3 + 1] / cell) + 128, iz = Math.round(pos[i * 3 + 2] / cell) + 128;
      var key = ix * 65536 + iy * 256 + iz;
      id = map.get(key);
      if (id === undefined) { id = sums.length / 4; map.set(key, id); sums.push(0, 0, 0, 0); }
      remap[i] = id;
      sums[id * 4] += pos[i * 3]; sums[id * 4 + 1] += pos[i * 3 + 1]; sums[id * 4 + 2] += pos[i * 3 + 2]; sums[id * 4 + 3]++;
    }
    var count = sums.length / 4, p = new Float32Array(count * 3);
    for (id = 0; id < count; id++) {
      var c = sums[id * 4 + 3];
      p[id * 3] = sums[id * 4] / c; p[id * 3 + 1] = sums[id * 4 + 1] / c; p[id * 3 + 2] = sums[id * 4 + 2] / c;
    }
    var tris = [];
    for (i = 0; i < idx.length; i += 3) {
      var a = remap[idx[i]], b = remap[idx[i + 1]], d = remap[idx[i + 2]];
      if (a !== b && b !== d && a !== d) tris.push(a, b, d);
    }
    var g = new T.BufferGeometry();
    g.setAttribute('position', new T.BufferAttribute(p, 3));
    g.setIndex(new T.BufferAttribute(new Uint32Array(tris), 1));
    return g;
  }

  /* ---------- the anatomical shader ---------- */
  var VERT = [
    'attribute float aTone; attribute float aPart;',
    'varying vec3 vN; varying vec3 vVP; varying vec3 vPos; varying float vTone; varying float vPart;',
    'void main(){',
    '  vec4 mv = modelViewMatrix * vec4(position, 1.0);',
    '  vN = normalize(normalMatrix * normal); vVP = mv.xyz; vPos = position; vTone = aTone; vPart = aPart;',
    '  gl_Position = projectionMatrix * mv;',
    '}'
  ].join('\n');
  var FRAG = [
    'precision highp float;',
    'uniform vec3 uBase; uniform vec3 uBase2; uniform vec3 uRim; uniform vec3 uSpine; uniform vec3 uHoverC; uniform vec3 uAlertC;',
    'uniform float uBack; uniform float uRimI; uniform float uRimPow; uniform float uAlpha; uniform float uTime;',
    'uniform float uHover; uniform float uSel; uniform vec4 uAlertP; uniform float uPulse; uniform float uSpineI;',
    'varying vec3 vN; varying vec3 vVP; varying vec3 vPos; varying float vTone; varying float vPart;',
    'float mask(float p){ return p < 0.5 ? 0.0 : 1.0 - smoothstep(0.30, 0.50, abs(vPart - p)); }',
    'void main(){',
    '  vec3 n = normalize(vN); if (!gl_FrontFacing) n = -n;',
    '  vec3 v = normalize(-vVP);',
    '  float ndv = clamp(dot(n, v), 0.0, 1.0);',
    '  float fres = pow(1.0 - ndv, uRimPow);',
    '  vec3 L = normalize(vec3(-0.45, 0.62, 0.64));',
    '  float lit = 0.40 + 0.60 * max(dot(n, L), 0.0);',
    '  float t = vTone;',
    '  vec3 col = mix(uBase, uBase2, t) * lit;',
    '  col += uRim * fres * uRimI;',
    '  col += uRim * smoothstep(0.72, 1.0, t) * 0.30 * (0.5 + fres);',
    '  float a = uAlpha + fres * 0.55 + t * 0.10;',
    '  if (uBack > 0.5) { col *= 0.55; a = uAlpha * 0.55; }',
    /* the spine glows along the back */
    '  if (uBack < 0.5) {',
    '    float onBack = 1.0 - smoothstep(-0.06, -0.015, vPos.z);',
    '    float inY = smoothstep(0.86, 0.92, vPos.y) * (1.0 - smoothstep(1.56, 1.62, vPos.y));',
    '    float line = exp(-pow(vPos.x / 0.0125, 2.0));',
    '    float beads = 0.65 + 0.35 * sin(vPos.y * 230.0);',
    '    float sp = line * inY * onBack * beads * uSpineI;',
    '    col += uSpine * sp * 1.6; a = max(a, sp * 0.95);',
    '  }',
    '  float h = max(mask(uHover), mask(uSel));',
    '  col = mix(col, uHoverC, 0.30 * h) + uHoverC * 0.30 * h * (0.35 + t); a = max(a, 0.78 * h);',
    '  float al = max(max(mask(uAlertP.x), mask(uAlertP.y)), max(mask(uAlertP.z), mask(uAlertP.w)));',
    '  float ap = al * uPulse;',
    '  col = mix(col, uAlertC, 0.30 * ap) + uAlertC * 0.34 * ap * (0.35 + t); a = max(a, 0.66 * al);',
    '  gl_FragColor = vec4(col, clamp(a, 0.0, 1.0));',
    '}'
  ].join('\n');

  var PALETTE = {
    base: [0.050, 0.085, 0.165], base2: [0.290, 0.400, 0.610], rim: [0.28, 0.58, 1.0], spine: [0.45, 0.80, 1.0],
    hover: [0.33, 0.66, 1.0], alert: [1.0, 0.27, 0.40], glow: [64, 140, 255]
  };

  function create(container, opts) {
    opts = opts || {};
    if (typeof DecompressionStream === 'undefined' || !window.PERSPECTIVE_BODY_B64 || typeof Response === 'undefined') return null;
    var renderer;
    try {
      renderer = new T.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
    } catch (e) { return null; }
    if (!renderer.getContext()) return null;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    var canvas = renderer.domElement;
    canvas.className = 'fig-canvas';
    canvas.addEventListener('webglcontextlost', function (e) { e.preventDefault(); });
    canvas.addEventListener('webglcontextrestored', function () { dirty = true; });
    canvas.style.touchAction = 'pan-y';
    canvas.setAttribute('tabindex', '0');
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', opts.label || '3D body model. Drag or use the arrow keys to turn it.');
    container.appendChild(canvas);
    container.classList.add('loading');

    var scene = new T.Scene();
    var camera = new T.PerspectiveCamera(26, 1, 0.5, 30);
    var model = new T.Group();
    scene.add(model);

    /* ---------- material ---------- */
    function uniforms(back) {
      var c = function (a) { return new T.Vector3(a[0], a[1], a[2]); };
      return {
        uBase: { value: c(PALETTE.base) }, uBase2: { value: c(PALETTE.base2) }, uRim: { value: c(PALETTE.rim) },
        uSpine: { value: c(PALETTE.spine) }, uHoverC: { value: c(PALETTE.hover) }, uAlertC: { value: c(PALETTE.alert) },
        uBack: { value: back ? 1 : 0 }, uRimI: { value: 1.25 }, uRimPow: { value: 2.1 }, uAlpha: { value: 0.50 }, uTime: { value: 0 },
        uHover: { value: 0 }, uSel: { value: 0 }, uAlertP: { value: new T.Vector4(0, 0, 0, 0) }, uPulse: { value: 1 }, uSpineI: { value: 1 }
      };
    }
    var frontU = uniforms(false), backU = uniforms(true);
    var frontMat = new T.ShaderMaterial({ uniforms: frontU, vertexShader: VERT, fragmentShader: FRAG, transparent: true, side: T.FrontSide, depthWrite: true });
    var backMat = new T.ShaderMaterial({ uniforms: backU, vertexShader: VERT, fragmentShader: FRAG, transparent: true, side: T.BackSide, depthWrite: false });
    var bodyFront = null, bodyBack = null, proxy = null;

    /* ---------- floor: glow, rings, ticks, scan ring ---------- */
    var floorTex = new T.CanvasTexture(document.createElement('canvas'));
    var floor = new T.Mesh(new T.CircleGeometry(0.64, 64), new T.MeshBasicMaterial({ map: floorTex, transparent: true, depthWrite: false }));
    floor.rotation.x = -H; floor.position.y = 0.001; scene.add(floor);
    function ring(r, w, opacity) {
      var m = new T.Mesh(new T.RingGeometry(r - w, r + w, 128), new T.MeshBasicMaterial({ color: 0x4f94ff, transparent: true, opacity: opacity, depthWrite: false, blending: T.AdditiveBlending, side: T.DoubleSide }));
      m.rotation.x = -H; m.position.y = 0.003; scene.add(m);
      return m;
    }
    ring(0.30, 0.004, 0.85); ring(0.30, 0.022, 0.16);
    ring(0.44, 0.003, 0.60); ring(0.44, 0.018, 0.10);
    ring(0.58, 0.003, 0.40);
    var tickMat = new T.LineBasicMaterial({ color: 0x6fb0ff, transparent: true, opacity: 0.55, blending: T.AdditiveBlending, depthWrite: false });
    var tp = [], q;
    for (q = 0; q < 120; q++) {
      var ta = TAU * q / 120, r0 = q % 5 === 0 ? 0.50 : 0.53, r1 = 0.56;
      tp.push(Math.cos(ta) * r0, 0.004, Math.sin(ta) * r0, Math.cos(ta) * r1, 0.004, Math.sin(ta) * r1);
    }
    var tg = new T.BufferGeometry(); tg.setAttribute('position', new T.Float32BufferAttribute(tp, 3));
    model.add(new T.LineSegments(tg, tickMat));
    var scanMat = new T.MeshBasicMaterial({ color: 0x6fb0ff, transparent: true, opacity: 0.6, depthWrite: false, blending: T.AdditiveBlending });
    var scan = new T.Mesh(new T.TorusGeometry(0.56, 0.0035, 6, 128), scanMat);
    scan.rotation.x = H; scene.add(scan);
    var scanGlowMat = new T.MeshBasicMaterial({ color: 0x4f94ff, transparent: true, opacity: 0.1, depthWrite: false, blending: T.AdditiveBlending });
    var scanGlow = new T.Mesh(new T.TorusGeometry(0.56, 0.022, 6, 128), scanGlowMat);
    scanGlow.rotation.x = H; scene.add(scanGlow);

    function paintFloor() {
      var c = floorTex.image, g = c.getContext('2d'), rgb = PALETTE.glow.join(',');
      c.width = c.height = 256;
      var gr = g.createRadialGradient(128, 128, 10, 128, 128, 126);
      gr.addColorStop(0, 'rgba(' + rgb + ',0.55)'); gr.addColorStop(0.55, 'rgba(' + rgb + ',0.20)'); gr.addColorStop(1, 'rgba(' + rgb + ',0)');
      g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
      floorTex.needsUpdate = true;
    }
    paintFloor();

    /* ---------- state ---------- */
    var rot = 0, target = null, vel = 0, sway = 0, idleFor = 0, dragging = false, pointerOver = false;
    var hovered = null, selected = null, flagged = [], dirty = true, active = true, lastView = '', anchorState = '';
    var ptr = { x: 0, y: 0, moved: false };
    var reduced = !!opts.reduced, failed = false, ready = false;
    var rc = new T.Raycaster(), ndc = new T.Vector2();
    var anchors = {};

    function setTheme() { dirty = true; }   // the figure keeps one look; the page behind it adapts
    function setHighlights() {
      frontU.uHover.value = hovered ? PART_INDEX[hovered] : 0;
      frontU.uSel.value = selected ? PART_INDEX[selected] : 0;
      var a = [0, 0, 0, 0]; flagged.slice(0, 4).forEach(function (k, i) { a[i] = PART_INDEX[k] || 0; });
      frontU.uAlertP.value.set(a[0], a[1], a[2], a[3]);
      dirty = true;
    }
    function setFlagged(list) { flagged = (list || []).slice(); setHighlights(); }
    function setSelected(part) { selected = part || null; setHighlights(); }

    function size() {
      var w = Math.max(120, container.clientWidth), h = Math.max(160, container.clientHeight);
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      var vf = Math.tan(camera.fov * PI / 360);
      var dist = Math.max((2.0 / 2) / vf, (1.30 / 2) / (vf * camera.aspect));
      camera.position.set(0, 1.9, dist);
      camera.lookAt(0, 0.9, 0);
      camera.updateProjectionMatrix();
      dirty = true;
    }
    if (window.ResizeObserver) new ResizeObserver(size).observe(container); else window.addEventListener('resize', size);

    function viewName() {
      var a = ((rot % TAU) + TAU) % TAU;
      if (a < PI / 4 || a > TAU - PI / 4) return 'front';
      if (Math.abs(a - PI) < PI / 4) return 'back';
      return 'side';
    }

    /* ---------- build the body once the model is decoded ---------- */
    loadModel().then(function (m) {
      var g = new T.BufferGeometry();
      g.setAttribute('position', new T.BufferAttribute(m.pos, 3));
      g.setAttribute('normal', new T.BufferAttribute(m.nrm, 3, true));
      g.setAttribute('aTone', new T.BufferAttribute(m.tone, 1, true));
      g.setAttribute('aPart', new T.BufferAttribute(m.part, 1, false));
      g.setIndex(new T.BufferAttribute(m.idx, 1));
      g.boundingSphere = new T.Sphere(new T.Vector3(0, 0.9, 0), 1.2);
      g.boundingBox = new T.Box3(new T.Vector3(-0.6, 0, -0.2), new T.Vector3(0.6, 1.8, 0.2));
      bodyBack = new T.Mesh(g, backMat); bodyBack.renderOrder = 1; bodyBack.frustumCulled = false;
      bodyFront = new T.Mesh(g, frontMat); bodyFront.renderOrder = 2; bodyFront.frustumCulled = false;
      model.add(bodyBack, bodyFront);
      proxy = new T.Mesh(m.proxy, new T.MeshBasicMaterial({ side: T.DoubleSide }));
      proxy.visible = false; model.add(proxy);
      model.updateMatrixWorld(true);
      var a = opts.anchors || {};
      Object.keys(a).forEach(function (name) {
        var p = a[name], hit = new T.Raycaster(new T.Vector3(p[0], p[1], 2), new T.Vector3(0, 0, -1)).intersectObject(proxy, false)[0];
        var loc = hit ? model.worldToLocal(hit.point.clone()) : new T.Vector3(p[0], p[1], p[2] || 0.1);
        anchors[name] = { local: loc, normal: new T.Vector3(0, 0, 1) };
      });
      ready = true; anchorState = '';
      container.classList.remove('loading');
      dirty = true;
    }).catch(function (err) {
      failed = true; container.classList.remove('loading');
      if (opts.onFail) opts.onFail(err && err.message ? err.message : 'model failed');
    });

    function pick(px, py) {
      if (!ready) return null;
      var r = canvas.getBoundingClientRect();
      ndc.set(((px - r.left) / r.width) * 2 - 1, -((py - r.top) / r.height) * 2 + 1);
      rc.setFromCamera(ndc, camera);
      var hit = rc.intersectObject(proxy, false)[0];
      if (!hit) return null;
      var p = proxy.worldToLocal(hit.point.clone());
      return classify(p.x, p.y, p.z);
    }

    /* ---------- anchors (points on the body that the page labels) ---------- */
    function reportAnchors() {
      if (!opts.onAnchors || !ready) return;
      var w = container.clientWidth, h = container.clientHeight, out = {}, sig = '';
      var v = new T.Vector3(), n = new T.Vector3(), view = new T.Vector3();
      Object.keys(anchors).forEach(function (name) {
        var an = anchors[name];
        v.copy(an.local).applyMatrix4(model.matrixWorld);
        n.copy(an.normal).transformDirection(model.matrixWorld);
        view.copy(camera.position).sub(v).normalize();
        var visible = n.dot(view) > 0.3;
        v.project(camera);
        var x = (v.x * 0.5 + 0.5) * w, y = (-v.y * 0.5 + 0.5) * h;
        out[name] = { x: x, y: y, visible: visible };
        sig += name + Math.round(x * 2) + ',' + Math.round(y * 2) + visible;
      });
      if (sig !== anchorState) { anchorState = sig; opts.onAnchors(out); }
    }

    /* ---------- input ---------- */
    var down = null;
    function local(e) { var r = container.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
    canvas.addEventListener('pointerdown', function (e) {
      if (e.button !== undefined && e.button !== 0) return;
      dragging = true; down = { x: e.clientX, lx: e.clientX, t: performance.now(), moved: 0 }; vel = 0; target = null; idleFor = 0;
      try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* not supported */ }
      canvas.style.cursor = 'grabbing';
    });
    canvas.addEventListener('pointermove', function (e) {
      ptr.x = e.clientX; ptr.y = e.clientY; ptr.moved = true; pointerOver = true; idleFor = 0;
      if (dragging && down) {
        var step = e.clientX - down.lx;
        down.lx = e.clientX; down.moved += Math.abs(step);
        rot += step * 0.011; vel = step * 0.011 * 60; dirty = true;
        if (down.moved > 4) setHovered(null, e);
      }
    });
    function endDrag(e, cancelled) {
      if (!dragging) return;
      dragging = false;
      try { canvas.releasePointerCapture(e.pointerId); } catch (err) { /* not captured */ }
      var wasClick = down && down.moved < 5 && performance.now() - down.t < 600 && !cancelled;
      down = null; canvas.style.cursor = hovered ? 'pointer' : 'grab';
      if (wasClick && opts.onPick) {
        var part = pick(e.clientX, e.clientY), p = local(e);
        setSelected(part);
        opts.onPick(part, p.x, p.y);
      }
    }
    canvas.addEventListener('pointerup', function (e) { endDrag(e, false); });
    canvas.addEventListener('pointercancel', function (e) { endDrag(e, true); });
    canvas.addEventListener('pointerleave', function (e) { pointerOver = false; if (!dragging) setHovered(null, e); });
    canvas.addEventListener('keydown', function (e) {
      var k = e.key;
      if (k === 'ArrowLeft') { rotateBy(-PI / 12); e.preventDefault(); }
      else if (k === 'ArrowRight') { rotateBy(PI / 12); e.preventDefault(); }
      else if (k === 'Home') { snapTo(0); e.preventDefault(); }
      else if (k === 'End') { snapTo(PI); e.preventDefault(); }
      else if (k === 'Escape') { setSelected(null); if (opts.onPick) opts.onPick(null, 0, 0); }
    });
    canvas.style.cursor = 'grab';

    function setHovered(part, e) {
      var changed = part !== hovered;
      hovered = part;
      if (changed) { setHighlights(); canvas.style.cursor = dragging ? 'grabbing' : (hovered ? 'pointer' : 'grab'); }
      if (opts.onHover) { var p = e ? local(e) : { x: 0, y: 0 }; opts.onHover(part, p.x, p.y, changed); }
    }

    function rotateBy(d) { target = (target === null ? rot : target) + d; idleFor = 0; vel = 0; if (reduced) { rot = target; target = null; } dirty = true; }
    function snapTo(a) {
      var base = target === null ? rot : target;
      target = base + wrapAngle(a - base); idleFor = 0; vel = 0;
      if (reduced) { rot = target; target = null; }
      dirty = true;
    }

    /* ---------- loop ---------- */
    var last = performance.now(), clock = 0, lastPick = 0, lastDraw = 0;
    function frame(now) {
      requestAnimationFrame(frame);
      if (!active || document.hidden || failed) { last = now; return; }
      var dt = Math.min(0.05, (now - last) / 1000); last = now; clock += dt;
      var busy = dragging;

      if (!dragging) {
        if (target !== null) {
          var diff = target - rot;
          rot += diff * (1 - Math.exp(-8 * dt));
          if (Math.abs(diff) < 0.0008) { rot = target; target = null; }
          dirty = true; busy = true;
        } else if (Math.abs(vel) > 0.002) {
          rot += vel * dt; vel *= Math.exp(-3.2 * dt); dirty = true; busy = true;
        }
      }
      idleFor += dt;
      var wantSway = !reduced && !dragging && !pointerOver && target === null && idleFor > 3 && !selected;
      var swayGoal = wantSway ? 1 : 0;
      if (Math.abs(sway - swayGoal) > 0.001) { sway += (swayGoal - sway) * (1 - Math.exp(-1.6 * dt)); dirty = true; }
      var swayAngle = sway * Math.sin(clock * 0.7) * 0.32;
      if (sway > 0.001) dirty = true;

      if (ptr.moved && !dragging && pointerOver) {
        ptr.moved = false; busy = true;
        setHovered(pick(ptr.x, ptr.y), { clientX: ptr.x, clientY: ptr.y });
      } else if (!dragging && pointerOver && dirty && now - lastPick > 90) {
        lastPick = now;   // the model moved under a resting pointer
        var again = pick(ptr.x, ptr.y);
        if (again !== hovered) setHovered(again, { clientX: ptr.x, clientY: ptr.y });
      }

      if (!reduced) {
        if (flagged.length) { frontU.uPulse.value = 0.55 + 0.45 * Math.sin(clock * 2.6); dirty = true; }
        var ph = (clock % 6) / 6;
        scan.position.y = scanGlow.position.y = 0.02 + ph * 1.78;
        var fade = Math.pow(Math.sin(PI * ph), 0.6);
        scanMat.opacity = 0.65 * fade; scanGlowMat.opacity = 0.12 * fade;
        scan.visible = scanGlow.visible = true; dirty = true;
      } else { scan.visible = scanGlow.visible = false; frontU.uPulse.value = 1; }

      if (dirty && (busy || now - lastDraw > 30)) {   // idle animation runs at about 30 fps
        lastDraw = now;
        model.rotation.y = rot + swayAngle;
        model.updateMatrixWorld(true);
        renderer.render(scene, camera);
        reportAnchors();
        dirty = false;
        var v = viewName();
        if (v !== lastView) { lastView = v; if (opts.onView) opts.onView(v); }
      }
    }
    setFlagged(opts.flagged);
    size();
    requestAnimationFrame(frame);

    return {
      setTheme: setTheme,
      setFlagged: setFlagged,
      setSelected: setSelected,
      setActive: function (on) { active = !!on; if (active) dirty = true; },
      rotateBy: rotateBy,
      snapTo: snapTo,
      view: function () { return lastView || viewName(); },
      label: function (part) { return LABELS[part] || part; },
      canvas: canvas
    };
  }

  window.PerspectiveBody = { create: create, labels: LABELS, classify: classify };
})();
