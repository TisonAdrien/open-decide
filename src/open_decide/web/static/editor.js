/* Visual editor built on vis-network.
 *
 * Design:
 * - The JSON textarea is the source of truth. The canvas is a projection.
 * - "Apply JSON to canvas" parses and renders.
 * - Dragging nodes only changes positions, never the tree.
 * - Structural edits (add node) update the JSON, then re-render.
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  var network = null;
  var nodesDataSet = null;
  var edgesDataSet = null;
  var currentTree = null;
  var nodeSeq = 0;

  function setStatus(msg, isError) {
    var el = $('status');
    el.textContent = msg || '';
    el.classList.toggle('error', Boolean(isError));
  }

  function truncate(str, n) {
    return str.length > n ? str.slice(0, n) + '...' : str;
  }

  function treeToGraph(tree) {
    var nodes = [];
    var edges = [];
    var edgeSeen = {};

    Object.keys(tree.nodes).forEach(function (id) {
      var node = tree.nodes[id];
      var isDecision = node.type === 'decision';
      var label = isDecision
        ? truncate(node.question_type + ' - ' + node.prompt, 50)
        : '\u2192 ' + truncate(node.result, 40);

      nodes.push({
        id: id,
        label: label,
        shape: isDecision ? 'box' : 'ellipse',
        color: isDecision
          ? { background: '#1f2937', border: '#6ea8fe' }
          : { background: '#1f2937', border: '#4ade80' },
        font: { color: '#e6e8ee' }
      });

      if (!isDecision) return;

      node.options.forEach(function (opt) {
        var key = id + '->' + opt.next + ':' + opt.label;
        if (edgeSeen[key]) return;
        edgeSeen[key] = true;
        edges.push({
          id: key,
          from: id,
          to: opt.next,
          label: opt.label,
          arrows: 'to',
          color: { color: '#8b93a7' },
          font: { color: '#8b93a7', size: 11, strokeWidth: 0 }
        });
      });

      if (node.fallback) {
        var fkey = id + '->fallback:' + node.fallback;
        if (!edgeSeen[fkey]) {
          edgeSeen[fkey] = true;
          edges.push({
            id: fkey,
            from: id,
            to: node.fallback,
            label: 'fallback',
            arrows: 'to',
            dashes: true,
            color: { color: '#f87171' },
            font: { color: '#f87171', size: 11, strokeWidth: 0 }
          });
        }
      }
    });

    return { nodes: nodes, edges: edges };
  }

  function render(tree) {
    currentTree = tree;
    var graph = treeToGraph(tree);

    if (nodesDataSet && edgesDataSet) {
      nodesDataSet.clear();
      edgesDataSet.clear();
      nodesDataSet.add(graph.nodes);
      edgesDataSet.add(graph.edges);
      return;
    }

    nodesDataSet = new vis.DataSet(graph.nodes);
    edgesDataSet = new vis.DataSet(graph.edges);

    var data = { nodes: nodesDataSet, edges: edgesDataSet };
    var options = {
      layout: {
        hierarchical: {
          enabled: true,
          direction: 'UD',
          sortMethod: 'directed',
          levelSeparation: 120
        }
      },
      physics: { enabled: false },
      interaction: { dragNodes: true, hover: true },
      nodes: { margin: 12, widthConstraint: { maximum: 220 } },
      edges: {
        smooth: { type: 'cubicBezier', forceDirection: 'vertical', roundness: 0.4 }
      }
    };

    network = new vis.Network($('graph'), data, options);
    network.on('doubleClick', function (params) {
      if (params.nodes && params.nodes.length) {
        onNodeDoubleClick(params.nodes[0]);
      }
    });
  }

  function onNodeDoubleClick(id) {
    if (!currentTree || !currentTree.nodes[id]) return;
    var node = currentTree.nodes[id];

    if (node.type === 'decision') {
      var newPrompt = window.prompt('Prompt for node "' + id + '":', node.prompt);
      if (newPrompt === null) return;
      node.prompt = newPrompt;
    } else {
      var newResult = window.prompt('Result for terminal "' + id + '":', node.result);
      if (newResult === null) return;
      node.result = newResult;
    }

    $('tree').value = JSON.stringify(currentTree, null, 2);
    render(currentTree);
    setStatus('Node updated', false);
  }

  function applyJson() {
    var raw = $('tree').value;
    var parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      setStatus('Invalid JSON: ' + e.message, true);
      return null;
    }
    render(parsed);
    setStatus('Applied', false);
    return parsed;
  }

  function nextNodeId() {
    nodeSeq += 1;
    return 'node_' + Date.now().toString(36) + '_' + nodeSeq;
  }

  function addDecision() {
    var tree = currentTree || applyJson();
    if (!tree) return;
    var id = nextNodeId();
    tree.nodes[id] = {
      id: id,
      type: 'decision',
      question_type: 'choice',
      prompt: 'New question?',
      options: [
        { label: 'a', next: tree.root },
        { label: 'b', next: tree.root }
      ],
      confidence_threshold: 0.5
    };
    $('tree').value = JSON.stringify(tree, null, 2);
    render(tree);
    setStatus('Added decision node ' + id, false);
  }

  function addTerminal() {
    var tree = currentTree || applyJson();
    if (!tree) return;
    var id = nextNodeId();
    tree.nodes[id] = { id: id, type: 'terminal', result: 'new_result' };
    $('tree').value = JSON.stringify(tree, null, 2);
    render(tree);
    setStatus('Added terminal ' + id, false);
  }

  function autoLayout() {
    if (!network) return;
    network.setOptions({
      layout: {
        hierarchical: {
          enabled: true,
          direction: 'UD',
          sortMethod: 'directed',
          levelSeparation: 120
        }
      }
    });
    network.fit();
  }

  async function loadExample() {
    var res = await fetch('/api/examples/ticket_routing');
    if (!res.ok) {
      setStatus('Example not found', true);
      return;
    }
    var tree = await res.json();
    $('tree').value = JSON.stringify(tree, null, 2);
    render(tree);
    setStatus('Example loaded', false);
  }

  document.addEventListener('DOMContentLoaded', function () {
    $('apply').addEventListener('click', applyJson);
    $('add-node').addEventListener('click', addDecision);
    $('add-terminal').addEventListener('click', addTerminal);
    $('auto-layout').addEventListener('click', autoLayout);
    $('load-example').addEventListener('click', loadExample);
  });
})();
