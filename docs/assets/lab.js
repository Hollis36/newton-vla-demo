/* Offset-tower stability lab — the page twin of `make experiment`.
   Buttons restack 3 line-art blocks at d = 0 / 40 / 90 mm per layer;
   gravity + contacts decide; CoM plumb line flips amber when the
   criterion (CoM outside the support base) is violated. */
(function () {
  'use strict';
  var box = document.getElementById('lab-scene-box');
  var canvas = document.getElementById('lab-scene');
  if (!box || !canvas || !window.Matter) return;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var M = Matter, W = 560, H = 360;
  var BLUE = '#1d4ed8', INK = '#0f1a2e', GREY = '#8a94a6', AMBER = '#e8a23d';
  var S = 84;                 // block side px  (≙ 200 mm  → 1 mm = 0.42 px)
  var MM = S / 200;           // px per mm
  var GROUND_Y = 331, BASE_X = 292;
  var engine, blocks = [], curD = 40, raf = null, settledAt = 0, started = false;

  function build(dmm) {
    curD = dmm;
    engine = M.Engine.create({ gravity: { x: 0, y: 1, scale: 0.0011 } });
    var ground = M.Bodies.rectangle(W / 2, GROUND_Y + 30, W * 2, 60, { isStatic: true });
    blocks = [0, 1, 2].map(function (i) {
      return M.Bodies.rectangle(
        BASE_X - i * dmm * MM, GROUND_Y - S / 2 - i * S, S, S,
        { friction: 0.6, restitution: 0, density: 0.002 });
    });
    var mouse = M.Mouse.create(canvas);
    function syncMouse() {
      var r = canvas.getBoundingClientRect();
      M.Mouse.setScale(mouse, { x: W / r.width, y: H / r.height });
    }
    syncMouse(); addEventListener('resize', syncMouse);
    var mc = M.MouseConstraint.create(engine, {
      mouse: mouse, constraint: { stiffness: 0.1, damping: 0.1 },
    });
    M.Composite.add(engine.world, blocks.concat([ground, mc]));
    canvas.addEventListener('pointerdown', wake);
  }

  function draw() {
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    ctx.font = '10px ui-monospace, monospace'; ctx.lineJoin = 'round';
    // ground
    ctx.strokeStyle = INK; ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.moveTo(60, GROUND_Y); ctx.lineTo(W - 40, GROUND_Y); ctx.stroke();
    // blocks
    blocks.forEach(function (b, i) {
      ctx.strokeStyle = i === 2 ? BLUE : INK;
      ctx.fillStyle = i === 2 ? 'rgba(29,78,216,.05)' : '#fff';
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      b.vertices.forEach(function (v, j) { j ? ctx.lineTo(v.x, v.y) : ctx.moveTo(v.x, v.y); });
      ctx.closePath(); ctx.fill(); ctx.stroke();
    });
    // CoM plumb + support bracket
    var com = blocks.reduce(function (s, b) { return s + b.position.x; }, 0) / 3;
    var bottom = blocks[0];
    var lo = bottom.position.x - S / 2, hi = bottom.position.x + S / 2;
    var stable = com >= lo && com <= hi;
    var tipped = blocks.some(function (b) {
      return Math.abs(((b.angle % 6.283) + 6.283) % 6.283 - 0) > 0.3 &&
             Math.abs(((b.angle % 6.283) + 6.283) % 6.283 - 6.283) > 0.3;
    });
    var c = stable && !tipped ? BLUE : AMBER;
    ctx.strokeStyle = c; ctx.lineWidth = 1; ctx.setLineDash([4, 6]);
    ctx.beginPath(); ctx.moveTo(com, 36); ctx.lineTo(com, GROUND_Y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = c; ctx.fillText('⌖ CoM', com - 16, 26);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(lo, GROUND_Y + 11); ctx.lineTo(hi, GROUND_Y + 11);
    ctx.moveTo(lo, GROUND_Y + 6); ctx.lineTo(lo, GROUND_Y + 16);
    ctx.moveTo(hi, GROUND_Y + 6); ctx.lineTo(hi, GROUND_Y + 16);
    ctx.stroke();
    ctx.fillStyle = GREY;
    ctx.fillText('support base', (lo + hi) / 2 - 32, GROUND_Y + 28);
    var read = document.getElementById('lab-readout');
    if (read) read.textContent = 'd = ' + curD + ' mm · ' +
      (tipped ? 'TOPPLED — CoM left the base' :
       stable ? 'CoM inside base · STABLE' : 'CoM outside base · UNSTABLE');
  }

  function step(t) {
    M.Engine.update(engine, 1000 / 60);
    draw();
    var maxV = Math.max.apply(null, blocks.map(function (b) { return b.speed; }));
    if (maxV > 0.05) settledAt = t;
    raf = (t - settledAt < 2000) ? requestAnimationFrame(step) : null;
  }
  function wake() { if (!raf) { settledAt = performance.now(); raf = requestAnimationFrame(step); } }
  function restack(d) { build(d); box.classList.add('live'); wake(); }

  document.querySelectorAll('.lab-controls button').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.lab-controls button').forEach(function (x) { x.classList.remove('on'); });
      b.classList.add('on');
      restack(+b.dataset.d);
    });
  });
  document.getElementById('lab-reset').addEventListener('click', function () { restack(curD); });
  new IntersectionObserver(function (es) {
    if (es[0].isIntersecting) { if (!started) { started = true; restack(40); } else wake(); }
    else if (raf) { cancelAnimationFrame(raf); raf = null; }
  }, { threshold: 0.15 }).observe(canvas);
})();
