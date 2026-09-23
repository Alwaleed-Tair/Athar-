const EvidenceMap = (() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';

  // Only two edge kinds are deterministic facts (not AI, no threshold).
  // Every other edge is ai_estimated: true with a model-chosen `type`
  // string (e.g. CONTENT_REFERENCE, TIME_CLUSTER) that can't be known in
  // advance, so it always gets the same generic "needs review" styling
  // rather than a fixed per-type color.
  const DETERMINISTIC_STYLE = {
    IDENTICAL_FILE: { colorVar: '--color-danger', dash: '' },
    SAME_DEVICE: { colorVar: '--color-primary', dash: '' },
  };
  const AI_EDGE_STYLE = { colorVar: '--color-warning', dash: '5,4' };

  async function renderTab(caseId) {
    const wrap = document.createElement('div');
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `<h3>${I18n.t('evidenceMap')}</h3><div id="map-container" class="mt-3"><p class="text-muted">…</p></div>`;
    wrap.appendChild(card);

    const container = card.querySelector('#map-container');

    let data;
    try {
      data = await Api.getEvidenceMap(caseId);
    } catch (e) {
      container.innerHTML = `<div class="alert alert-danger">${I18n.t('genericError')}</div>`;
      return wrap;
    }

    container.innerHTML = '';

    if (!data.nodes || data.nodes.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.innerHTML = `<h3>${I18n.t('mapEmptyTitle')}</h3><p>${I18n.t('mapEmptyBody')}</p>`;
      container.appendChild(empty);
      return wrap;
    }

    container.appendChild(buildLegend());

    const hasAiEdges = (data.edges || []).some((e) => e.ai_estimated);
    if (hasAiEdges) {
      const caption = document.createElement('p');
      caption.className = 'text-muted text-xs';
      caption.style.marginBlockEnd = '12px';
      caption.textContent = `⚠ ${I18n.t('aiAutomatedEstimate')}`;
      container.appendChild(caption);
    }

    const banner = buildAiStatusBanner(data);
    if (banner) container.appendChild(banner);

    container.appendChild(buildGraph(data));

    if (data.edges.length === 0 && data.ai_status !== 'DISABLED' && data.ai_status !== 'FAILED') {
      const note = document.createElement('p');
      note.className = 'text-muted text-sm mt-3';
      note.textContent = I18n.t('mapEmptyBody');
      container.appendChild(note);
    }

    return wrap;
  }

  function buildAiStatusBanner(data) {
    if (data.ai_status === 'DISABLED') {
      const div = document.createElement('div');
      div.className = 'alert alert-warning';
      div.textContent = data.ai_message || I18n.t('mapAiDisabledNote');
      return div;
    }
    if (data.ai_status === 'FAILED') {
      const div = document.createElement('div');
      div.className = 'alert alert-danger';
      div.textContent = data.ai_message || I18n.t('mapAiFailedNote');
      return div;
    }
    return null;
  }

  function buildLegend() {
    const legend = document.createElement('div');
    legend.className = 'flex gap-3 text-sm';
    legend.style.flexWrap = 'wrap';
    legend.style.marginBlockEnd = '12px';

    const entries = [
      { label: I18n.t('edgeIdenticalFile'), style: DETERMINISTIC_STYLE.IDENTICAL_FILE },
      { label: I18n.t('edgeSameDevice'), style: DETERMINISTIC_STYLE.SAME_DEVICE },
      { label: I18n.t('edgeAiCorrelation'), style: AI_EDGE_STYLE },
    ];

    entries.forEach(({ label, style }) => {
      const item = document.createElement('span');
      item.className = 'flex gap-2';
      item.style.alignItems = 'center';
      const swatch = document.createElement('span');
      swatch.style.display = 'inline-block';
      swatch.style.width = '16px';
      swatch.style.height = '0';
      swatch.style.borderTop = `2px ${style.dash ? 'dashed' : 'solid'} ${cssVar(style.colorVar)}`;
      item.appendChild(swatch);
      const text = document.createElement('span');
      text.textContent = label;
      item.appendChild(text);
      legend.appendChild(item);
    });

    return legend;
  }

  function edgeStyle(edge) {
    if (!edge.ai_estimated && DETERMINISTIC_STYLE[edge.type]) return DETERMINISTIC_STYLE[edge.type];
    if (edge.ai_estimated) return AI_EDGE_STYLE;
    return { colorVar: '--color-text-muted', dash: '' };
  }

  function edgeTooltip(edge) {
    if (edge.ai_estimated) {
      const typeLabel = humanizeType(edge.type);
      return edge.explanation ? `${typeLabel}\n${edge.explanation}` : typeLabel;
    }
    if (edge.type === 'IDENTICAL_FILE') return I18n.t('edgeIdenticalFile');
    if (edge.type === 'SAME_DEVICE') return I18n.t('edgeSameDevice');
    return humanizeType(edge.type);
  }

  function edgeShortLabel(edge) {
    if (!edge.ai_estimated) {
      if (edge.type === 'IDENTICAL_FILE') return I18n.t('edgeIdenticalFileShort');
      if (edge.type === 'SAME_DEVICE') return I18n.t('edgeSameDeviceShort');
      return humanizeType(edge.type);
    }
    return truncate(edge.explanation || humanizeType(edge.type), 30);
  }

  function humanizeType(type) {
    return (type || '')
      .toLowerCase()
      .split('_')
      .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
      .join(' ');
  }

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
  }

  function buildGraph(data) {
    const { nodes, edges } = data;
    // Landscape viewBox instead of a small fixed square, and no width
    // cap -- the graph now scales up to fill the card's actual width
    // instead of sitting in a small square with empty space around it.
    const width = 900;
    const height = 480;
    const cx = width / 2;
    const cy = height / 2;
    const rx = Math.min(400, 130 + nodes.length * 22); // horizontal radius
    const ry = Math.min(190, 90 + nodes.length * 10); // vertical radius

    const positions = {};
    nodes.forEach((n, i) => {
      // Starting at angle 0 (instead of -90deg) means exactly 2 nodes end
      // up side by side (left/right) instead of stacked top/bottom, which
      // reads better in this card's wide, short layout.
      const angle = (2 * Math.PI * i) / nodes.length;
      positions[n.id] = {
        x: cx + rx * Math.cos(angle),
        y: cy + ry * Math.sin(angle),
      };
    });

    const wrapper = document.createElement('div');
    wrapper.style.overflowX = 'auto';

    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('width', '100%');
    svg.style.maxWidth = '100%';
    svg.style.height = 'auto';
    svg.style.display = 'block';
    svg.style.margin = '0 auto';

    // Draw edges first so nodes render on top
    edges.forEach((e) => {
      const a = positions[e.source];
      const b = positions[e.target];
      if (!a || !b) return;
      const style = edgeStyle(e);
      const line = document.createElementNS(SVG_NS, 'line');
      line.setAttribute('x1', a.x);
      line.setAttribute('y1', a.y);
      line.setAttribute('x2', b.x);
      line.setAttribute('y2', b.y);
      line.setAttribute('stroke', cssVar(style.colorVar));
      line.setAttribute('stroke-width', '2');
      if (style.dash) line.setAttribute('stroke-dasharray', style.dash);
      line.setAttribute('opacity', '0.85');

      const title = document.createElementNS(SVG_NS, 'title');
      title.textContent = edgeTooltip(e);
      line.appendChild(title);

      svg.appendChild(line);

      // Short, always-visible reason (not just on hover) at the edge's
      // midpoint, per feedback that the map needs to show WHY two items
      // are linked without requiring a hover.
      const shortLabel = edgeShortLabel(e);
      if (shortLabel) {
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2;
        const approxWidth = Math.min(shortLabel.length * 5.2 + 8, 160);

        const bg = document.createElementNS(SVG_NS, 'rect');
        bg.setAttribute('x', mx - approxWidth / 2);
        bg.setAttribute('y', my - 8);
        bg.setAttribute('width', approxWidth);
        bg.setAttribute('height', 14);
        bg.setAttribute('rx', 3);
        bg.setAttribute('fill', cssVar('--color-surface'));
        bg.setAttribute('opacity', '0.9');
        svg.appendChild(bg);

        const labelText = document.createElementNS(SVG_NS, 'text');
        labelText.setAttribute('x', mx);
        labelText.setAttribute('y', my + 3);
        labelText.setAttribute('text-anchor', 'middle');
        labelText.setAttribute('font-size', '9');
        labelText.setAttribute('fill', cssVar(style.colorVar));
        labelText.textContent = truncate(shortLabel, 26);
        const labelTitle = document.createElementNS(SVG_NS, 'title');
        labelTitle.textContent = edgeTooltip(e);
        labelText.appendChild(labelTitle);
        svg.appendChild(labelText);
      }
    });

    nodes.forEach((n) => {
      const p = positions[n.id];
      const g = document.createElementNS(SVG_NS, 'g');
      g.style.cursor = 'pointer';

      const circle = document.createElementNS(SVG_NS, 'circle');
      circle.setAttribute('cx', p.x);
      circle.setAttribute('cy', p.y);
      circle.setAttribute('r', '20');
      circle.setAttribute('fill', cssVar('--color-surface'));
      circle.setAttribute('stroke', cssVar('--color-primary'));
      circle.setAttribute('stroke-width', '2');
      g.appendChild(circle);

      const icon = document.createElementNS(SVG_NS, 'text');
      icon.setAttribute('x', p.x);
      icon.setAttribute('y', p.y + 5);
      icon.setAttribute('text-anchor', 'middle');
      icon.setAttribute('font-size', '16');
      icon.textContent = '📄';
      g.appendChild(icon);

      const title = document.createElementNS(SVG_NS, 'title');
      const tooltipLines = [n.filename, `${I18n.t('sha256')}: ${n.sha256.slice(0, 16)}…`];
      if (n.device) tooltipLines.push(n.device);
      title.textContent = tooltipLines.join('\n');
      g.appendChild(title);

      const label = document.createElementNS(SVG_NS, 'text');
      label.setAttribute('x', p.x);
      label.setAttribute('y', p.y + 36);
      label.setAttribute('text-anchor', 'middle');
      label.setAttribute('font-size', '10');
      label.setAttribute('fill', cssVar('--color-text-muted'));
      label.textContent = truncate(n.filename, 16);
      g.appendChild(label);

      g.addEventListener('click', () => Evidence.openInspectModal(n.id));
      svg.appendChild(g);
    });

    wrapper.appendChild(svg);
    return wrapper;
  }

  function truncate(s, n) {
    return s && s.length > n ? s.slice(0, n - 1) + '…' : s;
  }

  return { renderTab };
})();