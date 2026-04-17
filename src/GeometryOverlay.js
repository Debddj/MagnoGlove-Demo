/**
 * GeometryOverlay.js
 * 
 * Renders real-time geometric measurements on a 2D canvas overlay.
 * Uses hand landmarks as vertices to form triangles and circles,
 * then calculates and displays euclidean distances, areas, angles,
 * and the missing third side prediction.
 */

export class GeometryOverlay {
  constructor() {
    // Create a dedicated 2D canvas on top of the 3D scene
    this.canvas = document.createElement('canvas');
    this.canvas.id = 'geo-canvas';
    this.canvas.style.cssText = `
      position: absolute; top: 0; left: 0;
      width: 100%; height: 100%;
      z-index: 3; pointer-events: none;
    `;
    document.getElementById('app').appendChild(this.canvas);
    this.ctx = this.canvas.getContext('2d');

    this.resize();
    window.addEventListener('resize', () => this.resize());

    // Store computed geometry for HUD display
    this.lastGeo = null;
  }

  resize() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }

  /**
   * Convert MediaPipe normalized coords to mirrored screen pixels
   */
  toScreen(lm) {
    // Mirror X because CSS scaleX(-1) flips the video
    return {
      x: (1 - lm.x) * this.canvas.width,
      y: lm.y * this.canvas.height
    };
  }

  /**
   * Euclidean distance between two screen points
   */
  dist(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  /**
   * Convert pixel distance to a "virtual cm" scale for display
   * (roughly 1 cm per 30 pixels at 720p)
   */
  toCm(px) {
    const scale = this.canvas.height / 720 * 30;
    return (px / scale).toFixed(1);
  }

  /**
   * Calculate triangle area using Heron's formula
   */
  triangleArea(a, b, c) {
    const s = (a + b + c) / 2;
    const val = s * (s - a) * (s - b) * (s - c);
    return val > 0 ? Math.sqrt(val) : 0;
  }

  /**
   * Calculate angle at vertex B in triangle ABC (in degrees)
   */
  angleDeg(A, B, C) {
    const ab = { x: A.x - B.x, y: A.y - B.y };
    const cb = { x: C.x - B.x, y: C.y - B.y };
    const dot = ab.x * cb.x + ab.y * cb.y;
    const magAB = Math.hypot(ab.x, ab.y);
    const magCB = Math.hypot(cb.x, cb.y);
    if (magAB === 0 || magCB === 0) return 0;
    const cosAngle = Math.max(-1, Math.min(1, dot / (magAB * magCB)));
    return (Math.acos(cosAngle) * 180 / Math.PI);
  }

  /**
   * Main update — call each frame with hand data
   * @param {Array} handsData - array of { landmarks, handedness }
   */
  update(handsData) {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.lastGeo = null;

    if (!handsData || handsData.length === 0) return;

    // ── Use case 1: Single hand → show distances between fingertips ──
    // ── Use case 2: Two hands → triangle from 3 points ──

    if (handsData.length >= 2) {
      this.drawTriangleMode(handsData, ctx);
    } else if (handsData.length === 1) {
      this.drawSingleHandMode(handsData[0], ctx);
    }
  }

  /**
   * TRIANGLE MODE: 3 points from 2 hands
   * Left index tip (vertex A), Right index tip (vertex B), 
   * Average of both thumbs (vertex C)
   */
  drawTriangleMode(handsData, ctx) {
    const leftHand = handsData.find(h => h.handedness === 'Left');
    const rightHand = handsData.find(h => h.handedness === 'Right');
    if (!leftHand || !rightHand) {
      // Fallback: just use both as single hands
      this.drawSingleHandMode(handsData[0], ctx);
      return;
    }

    const lLms = leftHand.landmarks;
    const rLms = rightHand.landmarks;

    // Three vertices
    const A = this.toScreen(lLms[8]);   // Left index fingertip
    const B = this.toScreen(rLms[8]);   // Right index fingertip
    const C = this.toScreen(lLms[4]);   // Left thumb tip

    // Side lengths in pixels
    const sideAB = this.dist(A, B);
    const sideBC = this.dist(B, C);
    const sideCA = this.dist(C, A);

    // Side lengths in "cm"
    const cmAB = this.toCm(sideAB);
    const cmBC = this.toCm(sideBC);
    const cmCA = this.toCm(sideCA);

    // Area
    const area = this.triangleArea(sideAB, sideBC, sideCA);
    const areaCm = (area / Math.pow(this.canvas.height / 720 * 30, 2)).toFixed(1);

    // Angles
    const angleA = this.angleDeg(B, A, C).toFixed(1);
    const angleB = this.angleDeg(A, B, C).toFixed(1);
    const angleC = this.angleDeg(A, C, B).toFixed(1);

    // ── Draw filled triangle ──
    ctx.beginPath();
    ctx.moveTo(A.x, A.y);
    ctx.lineTo(B.x, B.y);
    ctx.lineTo(C.x, C.y);
    ctx.closePath();
    ctx.fillStyle = 'rgba(0, 229, 255, 0.06)';
    ctx.fill();

    // ── Draw edges with glow ──
    ctx.shadowColor = '#00e5ff';
    ctx.shadowBlur = 12;
    ctx.strokeStyle = '#00e5ff';
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(A.x, A.y);
    ctx.lineTo(B.x, B.y);
    ctx.lineTo(C.x, C.y);
    ctx.closePath();
    ctx.stroke();
    ctx.shadowBlur = 0;

    // ── Draw vertices ──
    [
      { p: A, label: 'A', color: '#00e5ff' },
      { p: B, label: 'B', color: '#ffab00' },
      { p: C, label: 'C', color: '#00e676' }
    ].forEach(v => {
      ctx.beginPath();
      ctx.arc(v.p.x, v.p.y, 8, 0, Math.PI * 2);
      ctx.fillStyle = v.color;
      ctx.shadowColor = v.color;
      ctx.shadowBlur = 15;
      ctx.fill();
      ctx.shadowBlur = 0;

      // Vertex label
      ctx.font = "bold 16px 'Orbitron', sans-serif";
      ctx.fillStyle = v.color;
      ctx.textAlign = 'center';
      ctx.fillText(v.label, v.p.x, v.p.y - 16);
    });

    // ── Draw edge length labels ──
    this.drawEdgeLabel(ctx, A, B, `${cmAB} cm`, '#00e5ff');
    this.drawEdgeLabel(ctx, B, C, `${cmBC} cm`, '#ffab00');
    this.drawEdgeLabel(ctx, C, A, `${cmCA} cm`, '#00e676');

    // ── Draw angle arcs ──
    this.drawAngleArc(ctx, B, A, C, angleA, '#00e5ff');
    this.drawAngleArc(ctx, A, B, C, angleB, '#ffab00');
    this.drawAngleArc(ctx, A, C, B, angleC, '#00e676');

    // ── Info panel (top-right) ──
    this.drawInfoBox(ctx, [
      { label: 'TRIANGLE ANALYSIS', value: '', color: '#00e5ff', isTitle: true },
      { label: 'Side AB', value: `${cmAB} cm`, color: '#00e5ff' },
      { label: 'Side BC', value: `${cmBC} cm`, color: '#ffab00' },
      { label: 'Side CA', value: `${cmCA} cm`, color: '#00e676' },
      { label: '∠A', value: `${angleA}°`, color: '#00e5ff' },
      { label: '∠B', value: `${angleB}°`, color: '#ffab00' },
      { label: '∠C', value: `${angleC}°`, color: '#00e676' },
      { label: 'Area', value: `${areaCm} cm²`, color: '#c0d4ee' },
      { label: 'Perimeter', value: `${(+cmAB + +cmBC + +cmCA).toFixed(1)} cm`, color: '#c0d4ee' },
    ]);

    // ── Missing side predictor ──
    // Show: given sides AB and CA, the possible range of BC
    const minBC = Math.abs(sideAB - sideCA);
    const maxBC = sideAB + sideCA;
    this.drawPredictionBox(ctx, {
      knownSides: [{ name: 'AB', cm: cmAB }, { name: 'CA', cm: cmCA }],
      predictedSide: 'BC',
      actualCm: cmBC,
      minCm: this.toCm(minBC),
      maxCm: this.toCm(maxBC)
    });

    // ── Circle overlay: circumscribed circle ──
    this.drawCircumscribedCircle(ctx, A, B, C, sideAB, sideBC, sideCA, area);

    this.lastGeo = { type: 'triangle', sides: [cmAB, cmBC, cmCA], area: areaCm };
  }

  /**
   * SINGLE HAND MODE: show distances between key fingertips
   * Also detect pinch → circle with pinch diameter
   */
  drawSingleHandMode(handData, ctx) {
    const lms = handData.landmarks;
    const tips = [
      { idx: 4,  label: 'Thumb',  color: '#00e5ff' },
      { idx: 8,  label: 'Index',  color: '#ffab00' },
      { idx: 12, label: 'Middle', color: '#00e676' },
      { idx: 16, label: 'Ring',   color: '#bf00ff' },
      { idx: 20, label: 'Pinky',  color: '#ff1744' },
    ];

    const screenPts = tips.map(t => ({
      ...t,
      p: this.toScreen(lms[t.idx])
    }));

    // Draw points
    screenPts.forEach(sp => {
      ctx.beginPath();
      ctx.arc(sp.p.x, sp.p.y, 6, 0, Math.PI * 2);
      ctx.fillStyle = sp.color;
      ctx.shadowColor = sp.color;
      ctx.shadowBlur = 10;
      ctx.fill();
      ctx.shadowBlur = 0;

      ctx.font = "10px 'Share Tech Mono', monospace";
      ctx.fillStyle = sp.color;
      ctx.textAlign = 'center';
      ctx.fillText(sp.label, sp.p.x, sp.p.y - 12);
    });

    // Draw distance lines between consecutive tips
    const infoLines = [];
    for (let i = 0; i < screenPts.length; i++) {
      for (let j = i + 1; j < screenPts.length; j++) {
        const a = screenPts[i], b = screenPts[j];
        const d = this.dist(a.p, b.p);
        const cm = this.toCm(d);

        // Only draw lines for adjacent or important pairs
        if (j - i === 1 || (i === 0 && j === 1)) {
          ctx.strokeStyle = 'rgba(0, 229, 255, 0.3)';
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(a.p.x, a.p.y);
          ctx.lineTo(b.p.x, b.p.y);
          ctx.stroke();
          ctx.setLineDash([]);

          this.drawEdgeLabel(ctx, a.p, b.p, `${cm}`, 'rgba(0, 229, 255, 0.7)');
        }

        if (j - i === 1) {
          infoLines.push({ label: `${a.label}↔${b.label}`, value: `${cm} cm`, color: a.color });
        }
      }
    }

    // Thumb-Index distance = pinch detection → circle
    const thumbIdx = this.dist(screenPts[0].p, screenPts[1].p);
    const pinchCm = this.toCm(thumbIdx);
    if (thumbIdx < 80) {
      // Draw circle with diameter = pinch distance
      const cx = (screenPts[0].p.x + screenPts[1].p.x) / 2;
      const cy = (screenPts[0].p.y + screenPts[1].p.y) / 2;
      const radius = thumbIdx / 2;
      const radiusCm = this.toCm(radius);
      const circumference = (2 * Math.PI * +radiusCm).toFixed(1);
      const circleArea = (Math.PI * radiusCm * radiusCm).toFixed(1);

      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.strokeStyle = '#ffab00';
      ctx.lineWidth = 2;
      ctx.shadowColor = '#ffab00';
      ctx.shadowBlur = 10;
      ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.fillStyle = 'rgba(255, 171, 0, 0.05)';
      ctx.fill();

      // Radius line
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + radius, cy);
      ctx.stroke();
      ctx.setLineDash([]);

      // Center dot
      ctx.beginPath();
      ctx.arc(cx, cy, 3, 0, Math.PI * 2);
      ctx.fillStyle = '#ffab00';
      ctx.fill();

      // Labels
      ctx.font = "11px 'Share Tech Mono', monospace";
      ctx.fillStyle = '#ffab00';
      ctx.textAlign = 'left';
      ctx.fillText(`r = ${radiusCm} cm`, cx + radius + 8, cy + 4);

      infoLines.push(
        { label: 'CIRCLE DETECTED', value: '', color: '#ffab00', isTitle: true },
        { label: 'Diameter', value: `${pinchCm} cm`, color: '#ffab00' },
        { label: 'Radius', value: `${radiusCm} cm`, color: '#ffab00' },
        { label: 'Circumference', value: `${circumference} cm`, color: '#ffab00' },
        { label: 'Area', value: `${circleArea} cm²`, color: '#ffab00' },
      );
    }

    // Info box
    this.drawInfoBox(ctx, [
      { label: 'HAND MEASUREMENTS', value: '', color: '#00e5ff', isTitle: true },
      ...infoLines
    ]);

    this.lastGeo = { type: 'single', distances: infoLines };
  }

  // ── Drawing helpers ──

  drawEdgeLabel(ctx, a, b, text, color) {
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    const angle = Math.atan2(b.y - a.y, b.x - a.x);

    // Offset perpendicular to the line
    const ox = -Math.sin(angle) * 18;
    const oy = Math.cos(angle) * 18;

    ctx.font = "bold 13px 'Share Tech Mono', monospace";
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    // Background pill
    const w = ctx.measureText(text).width + 12;
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.beginPath();
    ctx.roundRect(mx + ox - w/2, my + oy - 10, w, 20, 4);
    ctx.fill();

    ctx.fillStyle = color;
    ctx.fillText(text, mx + ox, my + oy);
  }

  drawAngleArc(ctx, P1, vertex, P2, angleDegStr, color) {
    const angle1 = Math.atan2(P1.y - vertex.y, P1.x - vertex.x);
    const angle2 = Math.atan2(P2.y - vertex.y, P2.x - vertex.x);
    const r = 25;

    ctx.beginPath();
    ctx.arc(vertex.x, vertex.y, r, angle1, angle2, false);
    ctx.strokeStyle = color + '66';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Label
    const midAngle = (angle1 + angle2) / 2;
    const lx = vertex.x + Math.cos(midAngle) * (r + 14);
    const ly = vertex.y + Math.sin(midAngle) * (r + 14);
    ctx.font = "10px 'Share Tech Mono', monospace";
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.fillText(`${angleDegStr}°`, lx, ly);
  }

  drawInfoBox(ctx, items) {
    const isMobile = this.canvas.width < 768;
    const isLandscape = this.canvas.width > this.canvas.height;
    const boxW = 210;
    const x = this.canvas.width - boxW - (isMobile ? 10 : 20);
    const y = isMobile ? (isLandscape ? 60 : 140) : 70;
    const lineH = 20;
    const boxH = items.length * lineH + 20;

    ctx.fillStyle = 'rgba(4, 10, 24, 0.88)';
    ctx.strokeStyle = 'rgba(0, 180, 255, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(x, y, 210, boxH, 6);
    ctx.fill();
    ctx.stroke();

    items.forEach((item, i) => {
      const iy = y + 14 + i * lineH;
      if (item.isTitle) {
        ctx.font = "bold 11px 'Orbitron', sans-serif";
        ctx.fillStyle = item.color;
        ctx.textAlign = 'left';
        ctx.fillText(item.label, x + 10, iy);
      } else {
        ctx.font = "11px 'Share Tech Mono', monospace";
        ctx.fillStyle = '#6a8aaa';
        ctx.textAlign = 'left';
        ctx.fillText(item.label, x + 10, iy);
        ctx.fillStyle = item.color;
        ctx.textAlign = 'right';
        ctx.fillText(item.value, x + 200, iy);
      }
    });
  }

  drawPredictionBox(ctx, data) {
    const isMobile = this.canvas.width < 768;
    const boxW = 210;
    const x = this.canvas.width - boxW - (isMobile ? 10 : 20);
    const y = this.canvas.height - 130 - (isMobile ? 80 : 0);

    ctx.fillStyle = 'rgba(4, 10, 24, 0.88)';
    ctx.strokeStyle = 'rgba(255, 171, 0, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(x, y, 210, 110, 6);
    ctx.fill();
    ctx.stroke();

    ctx.font = "bold 10px 'Orbitron', sans-serif";
    ctx.fillStyle = '#ffab00';
    ctx.textAlign = 'left';
    ctx.fillText('SIDE PREDICTOR', x + 10, y + 16);

    ctx.font = "11px 'Share Tech Mono', monospace";
    ctx.fillStyle = '#6a8aaa';
    ctx.fillText(`Known: ${data.knownSides[0].name}=${data.knownSides[0].cm}`, x + 10, y + 38);
    ctx.fillText(`Known: ${data.knownSides[1].name}=${data.knownSides[1].cm}`, x + 10, y + 56);

    ctx.fillStyle = '#ffab00';
    ctx.fillText(`${data.predictedSide} range:`, x + 10, y + 78);
    ctx.fillStyle = '#00e5ff';
    ctx.fillText(`${data.minCm} — ${data.maxCm} cm`, x + 100, y + 78);

    ctx.fillStyle = '#00e676';
    ctx.fillText(`Actual ${data.predictedSide}: ${data.actualCm} cm`, x + 10, y + 98);
  }

  drawCircumscribedCircle(ctx, A, B, C, a, b, c, area) {
    if (area < 10) return; // degenerate triangle

    // Circumradius R = (a*b*c) / (4*Area)
    const R = (a * b * c) / (4 * area);

    // Circumcenter
    const D = 2 * (A.x * (B.y - C.y) + B.x * (C.y - A.y) + C.x * (A.y - B.y));
    if (Math.abs(D) < 0.001) return;
    const ux = ((A.x*A.x + A.y*A.y) * (B.y - C.y) + (B.x*B.x + B.y*B.y) * (C.y - A.y) + (C.x*C.x + C.y*C.y) * (A.y - B.y)) / D;
    const uy = ((A.x*A.x + A.y*A.y) * (C.x - B.x) + (B.x*B.x + B.y*B.y) * (A.x - C.x) + (C.x*C.x + C.y*C.y) * (B.x - A.x)) / D;

    ctx.beginPath();
    ctx.arc(ux, uy, R, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(191, 0, 255, 0.25)';
    ctx.lineWidth = 1;
    ctx.setLineDash([6, 6]);
    ctx.stroke();
    ctx.setLineDash([]);

    // Center dot
    ctx.beginPath();
    ctx.arc(ux, uy, 3, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(191, 0, 255, 0.5)';
    ctx.fill();

    // Label
    ctx.font = "9px 'Share Tech Mono', monospace";
    ctx.fillStyle = 'rgba(191, 0, 255, 0.6)';
    ctx.textAlign = 'center';
    ctx.fillText(`R = ${this.toCm(R)} cm`, ux, uy - 10);
  }

  getLastGeo() {
    return this.lastGeo;
  }
}
