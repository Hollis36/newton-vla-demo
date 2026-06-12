/* Six-cable parallel robot hero scene — line-art matter.js miniature.
   Cabin hangs from 6 cables (3 anchor points × 2 attach points); drag it,
   watch tensions; a "GAIN" meter maps cabin deviation to dB loss
   (structure → electromagnetic performance). Sleeps when settled. */
(function () {
  'use strict';
  var box = document.getElementById('hero-scene-box');
  var canvas = document.getElementById('hero-scene');
  if (!box || !canvas || !window.Matter) return;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (matchMedia('(pointer: coarse)').matches && innerWidth < 700) return;

  var M = Matter, W = 560, H = 420;
  var BLUE = '#1d4ed8', INK = '#0f1a2e', GREY = '#8a94a6', AMBER = '#e8a23d';
  var engine, cabin, cables, mouseC, raf = null, settledAt = 0;
  var TARGET = { x: 300, y: 252 };
  var ANCHORS = [{ x: 65, y: 72 }, { x: 272, y: 42 }, { x: 495, y: 72 }];

  function build() {
    engine = M.Engine.create({ gravity: { x: 0, y: 1, scale: 0.0008 } });
    cabin = M.Bodies.polygon(280, 235, 6, 34, {
      frictionAir: 0.03, density: 0.004, angle: Math.PI / 6,
    });
    cables = ANCHORS.flatMap(function (a, i) {
      return [-12, 12].map(function (dx) {
        return M.Constraint.create({
          pointA: a, bodyB: cabin, pointB: { x: dx, y: -14 },
          stiffness: 0.05, damping: 0.08,
          length: Math.hypot(a.x - (280 + dx), a.y - 221) * 0.99,
        });
      });
    });
    var mouse = M.Mouse.create(canvas);
    // matter reads CSS pixels; canvas is responsive — fix the scale.
    function syncMouse() {
      var r = canvas.getBoundingClientRect();
      M.Mouse.setScale(mouse, { x: W / r.width, y: H / r.height });
    }
    syncMouse(); addEventListener('resize', syncMouse);
    mouseC = M.MouseConstraint.create(engine, {
      mouse: mouse, constraint: { stiffness: 0.08, damping: 0.1 },
    });
    M.Composite.add(engine.world, [cabin].concat(cables, [mouseC]));
    canvas.addEventListener('pointerdown', wake);
  }

  function tension(c) {
    var dx = c.pointA.x - (c.bodyB.position.x + c.pointB.x),
        dy = c.pointA.y - (c.bodyB.position.y + c.pointB.y);
    return Math.max(0, Math.hypot(dx, dy) - c.length);
  }

  function draw() {
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    ctx.lineJoin = 'round'; ctx.font = '10px ui-monospace, monospace';
    // towers (static decoration)
    ctx.strokeStyle = INK; ctx.lineWidth = 1.3;
    [[50, 65, 80], [480, 495, 510]].forEach(function (t) {
      ctx.beginPath();
      ctx.moveTo(t[0], 360); ctx.lineTo(t[1], 70); ctx.lineTo(t[2], 360);
      [290, 230, 160].forEach(function (y, i) {
        ctx.moveTo(t[1] - 10 + i * 3, y); ctx.lineTo(t[1] + 10 - i * 3, y);
      });
      ctx.stroke();
    });
    ctx.globalAlpha = 0.35;
    ctx.beginPath(); ctx.moveTo(262, 372); ctx.lineTo(272, 40); ctx.lineTo(282, 372); ctx.stroke();
    ctx.globalAlpha = 1;
    // dish
    ctx.lineWidth = 1.2; ctx.beginPath();
    ctx.moveTo(60, 392); ctx.quadraticCurveTo(280, 318, 500, 392); ctx.stroke();
    // cables — width maps to tension
    var tens = cables.map(tension), tMax = Math.max.apply(null, tens) || 1;
    cables.forEach(function (c, i) {
      var p = M.Constraint.pointBWorld(c);
      ctx.strokeStyle = BLUE; ctx.lineWidth = 0.7 + 1.6 * (tens[i] / tMax);
      ctx.globalAlpha = i >= 2 && i < 4 ? 0.55 : 1;   // center pair behind
      ctx.beginPath(); ctx.moveTo(c.pointA.x, c.pointA.y); ctx.lineTo(p.x, p.y); ctx.stroke();
      ctx.globalAlpha = 1;
    });
    ctx.fillStyle = BLUE;
    ctx.fillText('T₁ ' + (380 + tens[0] * 14 | 0) + ' N', 150, 105);
    ctx.fillStyle = GREY;
    ctx.fillText('T₂ ' + (380 + tens[4] * 14 | 0) + ' N', 360, 105);
    // cabin
    ctx.strokeStyle = BLUE; ctx.lineWidth = 1.4;
    ctx.fillStyle = 'rgba(29,78,216,.05)';
    ctx.beginPath();
    cabin.vertices.forEach(function (v, i) { i ? ctx.lineTo(v.x, v.y) : ctx.moveTo(v.x, v.y); });
    ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cabin.position.x - 9, cabin.position.y); ctx.lineTo(cabin.position.x + 9, cabin.position.y);
    ctx.moveTo(cabin.position.x, cabin.position.y - 9); ctx.lineTo(cabin.position.x, cabin.position.y + 9);
    ctx.stroke();
    // Stewart-platform hint: three short struts under the cabin (decoration,
    // rotates with the body via its lower vertices).
    ctx.strokeStyle = INK; ctx.lineWidth = 0.9;
    var vb = cabin.vertices;
    ctx.beginPath();
    ctx.moveTo(vb[3].x, vb[3].y); ctx.lineTo(cabin.position.x - 10, cabin.position.y + 46);
    ctx.moveTo(vb[4].x, vb[4].y); ctx.lineTo(cabin.position.x + 10, cabin.position.y + 46);
    ctx.moveTo(cabin.position.x - 10, cabin.position.y + 46);
    ctx.lineTo(cabin.position.x + 10, cabin.position.y + 46);
    ctx.stroke();
    // target + deviation
    var dev = Math.hypot(cabin.position.x - TARGET.x, cabin.position.y - TARGET.y);
    var mm = dev * 2.4;  // page scale: ≈2.4 mm per px (toy units)
    ctx.strokeStyle = AMBER;
    ctx.beginPath(); ctx.arc(TARGET.x, TARGET.y, 3.5, 0, 7); ctx.stroke();
    if (dev > 6) {
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(cabin.position.x, cabin.position.y);
      ctx.lineTo(TARGET.x, TARGET.y); ctx.stroke(); ctx.setLineDash([]);
    }
    // gain meter (electromechanical coupling)
    var loss = Math.min(3, mm / 80);
    ctx.strokeStyle = '#e3e8f0'; ctx.strokeRect(420, 140, 110, 46);
    ctx.fillStyle = GREY; ctx.fillText('GAIN  (structure→EM)', 428, 156);
    ctx.strokeRect(428, 162, 94, 6);
    ctx.fillStyle = loss > 1.5 ? AMBER : BLUE;
    ctx.fillRect(428, 162, 94 * (1 - loss / 3), 6);
    ctx.fillText('−' + loss.toFixed(1) + ' dB', 428, 182);
    var read = document.getElementById('hero-readout');
    if (read) read.textContent =
      'Δ ' + mm.toFixed(0) + ' mm · gain −' + loss.toFixed(1) + ' dB' +
      (loss > 1.5 ? ' · REPOINT' : ' · ON TARGET');
  }

  function step(t) {
    M.Engine.update(engine, 1000 / 60);
    draw();
    var moving = cabin.speed > 0.06 || (mouseC.body !== null);
    if (moving) settledAt = t;
    raf = (t - settledAt < 2200) ? requestAnimationFrame(step) : null;
  }
  function wake() { if (!raf) { settledAt = performance.now(); raf = requestAnimationFrame(step); } }

  build();
  box.classList.add('live');
  document.getElementById('hero-reset').addEventListener('click', function () {
    M.Body.setPosition(cabin, { x: 280, y: 235 });
    M.Body.setVelocity(cabin, { x: 0, y: 0 });
    M.Body.setAngularVelocity(cabin, 0);
    wake();
  });
  new IntersectionObserver(function (es) {
    es[0].isIntersecting ? wake() : (raf && cancelAnimationFrame(raf), raf = null);
  }, { threshold: 0.1 }).observe(canvas);
})();
