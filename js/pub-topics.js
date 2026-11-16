/* pub-topics.js — publication counts on the filter buttons and an
   area-proportional topic diagram (Euler/Venn) built from the
   data-category attributes of the .pub-item list. Clicking a circle
   applies the same filter as the matching button. */
(function () {
  var items = Array.prototype.slice.call(document.querySelectorAll('.pub-item'));
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.filter-btn'));
  if (!items.length || !buttons.length) return;

  var catsOf = items.map(function (it) {
    return (it.dataset.category || '').split(/\s+/).filter(Boolean);
  });

  /* ---- counts on buttons ---- */
  var counts = {};
  catsOf.forEach(function (cs) { cs.forEach(function (c) { counts[c] = (counts[c] || 0) + 1; }); });
  buttons.forEach(function (b) {
    var n = b.dataset.filter === 'all' ? items.length : (counts[b.dataset.filter] || 0);
    var span = document.createElement('span');
    span.className = 'filter-count';
    span.textContent = n;
    b.appendChild(span);
  });

  /* ---- diagram ---- */
  var host = document.getElementById('topicVenn');
  if (!host || typeof venn === 'undefined' || typeof d3 === 'undefined') return;

  var labels = {};
  buttons.forEach(function (b) {
    if (b.dataset.filter !== 'all') labels[b.dataset.filter] = b.firstChild.textContent.trim();
  });
  var keys = Object.keys(labels).filter(function (k) { return counts[k]; });

  // Every subset of categories that some paper belongs to, with the number
  // of papers that carry all categories in that subset.
  var sizes = {};
  catsOf.forEach(function (cs) {
    cs = cs.filter(function (c) { return labels[c]; }).sort();
    var n = cs.length;
    for (var mask = 1; mask < (1 << n); mask++) {
      var sub = [];
      for (var i = 0; i < n; i++) if (mask & (1 << i)) sub.push(cs[i]);
      var id = sub.join('|');
      sizes[id] = (sizes[id] || 0) + 1;
    }
  });
  var data = Object.keys(sizes).map(function (id) {
    return { sets: id.split('|'), size: sizes[id] };
  });

  // Wong (2011) colors that read on a dark background, plus dash patterns
  // so circles are distinguishable without color.
  var COLORS = ['#56B4E9', '#E69F00', '#009E73', '#CC79A7', '#F0E442', '#D55E00', '#BBBBBB'];
  var DASHES = ['none', '8 4', '2 4', '10 4 2 4', '4 4', '12 3', '1 3'];
  var style = {};
  keys.forEach(function (k, i) { style[k] = { color: COLORS[i % 7], dash: DASHES[i % 7] }; });

  // Shorter circle labels for phone widths.
  var SHORT = {
    'ai-rs': 'AI & Remote Sensing', 'comp-geo': 'Comp. Geosciences', 'co2': 'CO₂ Storage',
    'thermo': 'Chem. & Thermo', 'shale': 'Shale', 'hydrogen': 'Hydrogen', 'other': 'Other'
  };

  function draw() {
    host.innerHTML = '';
    var w = Math.min(host.clientWidth || 640, 860);
    var name = function (k) { return (w < 500 && SHORT[k]) || labels[k]; };
    var h = Math.round(w * (w < 500 ? 0.95 : 0.72));
    var chart = venn.VennDiagram().width(w).height(h).padding(w < 500 ? 20 : 30)
      .fontSize(w < 500 ? '12px' : '14px');
    var div = d3.select(host).datum(data).call(chart);

    div.selectAll('g').each(function (d) {
      var g = d3.select(this);
      if (d.sets.length === 1) {
        var s = style[d.sets[0]];
        g.attr('class', 'venn-set').attr('role', 'button').attr('tabindex', 0)
          .attr('aria-label', labels[d.sets[0]] + ': ' + d.size + ' papers. Show these papers.');
        g.select('path').style('fill', s.color).style('fill-opacity', 0.18)
          .style('stroke', s.color).style('stroke-width', 2.5).style('stroke-dasharray', s.dash);
        g.select('text').text(null).style('fill', '#e6edf3').style('font-weight', 700)
          .style('paint-order', 'stroke').style('stroke', '#161b22')
          .style('stroke-width', '4px').style('stroke-linejoin', 'round');
        var t = g.select('text');
        t.append('tspan').attr('x', t.attr('x')).text(name(d.sets[0]));
        t.append('tspan').attr('x', t.attr('x')).attr('dy', '1.2em').style('fill', s.color)
          .text(d.size);
      } else {
        g.select('path').style('fill-opacity', 0).style('stroke-opacity', 0);
        g.select('text').text(null);
      }
    });

    // Tooltip-like title for every region, including overlaps.
    div.selectAll('g').append('title').text(function (d) {
      return d.sets.map(function (k) { return labels[k]; }).join(' + ') + ': ' + d.size +
        (d.size === 1 ? ' paper' : ' papers');
    });

    function pick(d) {
      if (d.sets.length !== 1) return;
      var b = buttons.filter(function (x) { return x.dataset.filter === d.sets[0]; })[0];
      if (b) { b.click(); b.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    }
    div.selectAll('g.venn-set')
      .on('click', pick)
      .on('keydown', function (d) {
        var e = d3.event;
        if (e && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); pick(d); }
      })
      .on('mouseover', function () { d3.select(this).select('path').style('fill-opacity', 0.32); })
      .on('mouseout', function () { d3.select(this).select('path').style('fill-opacity', 0.18); });
  }

  draw();
  var last = host.clientWidth, timer;
  window.addEventListener('resize', function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      if (Math.abs(host.clientWidth - last) > 40) { last = host.clientWidth; draw(); }
    }, 200);
  });
})();
