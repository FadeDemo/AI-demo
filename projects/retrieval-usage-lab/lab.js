"use strict";

function assertVector(vector) {
  if (
    !Array.isArray(vector) ||
    vector.length === 0 ||
    !vector.every((value) => typeof value === "number" && Number.isFinite(value))
  ) {
    throw new TypeError("Vectors must contain finite numbers.");
  }
}

function vectorStats(query, documentVector) {
  assertVector(query);
  assertVector(documentVector);
  if (query.length !== documentVector.length) throw new RangeError("Vector dimensions must match.");
  const queryNorm = Math.hypot(...query);
  const documentNorm = Math.hypot(...documentVector);
  const dot = query.reduce((total, value, index) => total + value * documentVector[index], 0);
  const distance = Math.hypot(...query.map((value, index) => value - documentVector[index]));
  const cosine = queryNorm === 0 || documentNorm === 0 ? null : dot / queryNorm / documentNorm;
  return { dot, cosine, distance };
}

function assertIds(ids) {
  if (
    !Array.isArray(ids) ||
    !ids.every((id) => typeof id === "string" && id.length > 0) ||
    new Set(ids).size !== ids.length
  ) {
    throw new TypeError("Document IDs must be nonempty and unique.");
  }
}

function rankingMetrics(ranking, relevant, k) {
  assertIds(ranking);
  assertIds(relevant);
  if (!Number.isInteger(k) || k <= 0) throw new RangeError("K must be a positive integer.");
  const relevantIds = new Set(relevant);
  const top = ranking.slice(0, k);
  const hits = top.filter((id) => relevantIds.has(id)).length;
  const firstIndex = top.findIndex((id) => relevantIds.has(id));
  return {
    hits,
    recall: relevant.length === 0 ? null : hits / relevant.length,
    precision: hits / k,
    rr: relevant.length === 0 ? null : firstIndex < 0 ? 0 : 1 / (firstIndex + 1),
    firstRank: firstIndex < 0 ? null : firstIndex + 1,
  };
}

function rrf(rankings, c) {
  if (!Array.isArray(rankings)) throw new TypeError("Rankings must be an array.");
  if (!Number.isFinite(c) || c <= 0) throw new RangeError("C must be positive and finite.");
  const scores = new Map();
  rankings.forEach((ranking, source) => {
    assertIds(ranking);
    ranking.forEach((id, index) => {
      if (!scores.has(id))
        scores.set(id, {
          id,
          contributions: rankings.map(() => 0),
          ranks: rankings.map(() => null),
          score: 0,
        });
      const entry = scores.get(id);
      entry.ranks[source] = index + 1;
      entry.contributions[source] = 1 / (c + index + 1);
      entry.score += entry.contributions[source];
    });
  });
  return [...scores.values()].sort(
    (a, b) => b.score - a.score || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  );
}

function setupLab() {
  const byId = (id) => document.getElementById(id);
  const number = (value) =>
    value === null ? "无定义" : (Math.abs(value) < 0.00005 ? 0 : value).toFixed(4);
  const angleInput = byId("angle");
  const lengthInput = byId("length");
  const normalizeInput = byId("normalize");
  const board = byId("vector-board");

  function drawVectors(vector) {
    const width = Math.max(board.clientWidth, 240);
    const height = 280;
    const originX = width / 2;
    const originY = height - 50;
    const unit = Math.min((width - 64) / 5.6, (height - 90) / 2.6);
    const x = (value) => originX + value * unit;
    const y = (value) => originY - value * unit;
    const grid = [-2, -1, 0, 1, 2]
      .map(
        (tick) =>
          `<line class="grid" x1="${x(tick)}" y1="22" x2="${x(tick)}" y2="${originY}" />${tick === 0 ? "" : `<text x="${x(tick)}" y="${originY + 18}" text-anchor="middle">${tick}</text>`}`,
      )
      .join("");
    const documentArrow =
      Math.hypot(...vector) === 0
        ? `<circle cx="${originX}" cy="${originY}" r="4" fill="#176c51" />`
        : `<line x1="${originX}" y1="${originY}" x2="${x(vector[0])}" y2="${y(vector[1])}" stroke="#176c51" stroke-width="3" stroke-dasharray="7 4" marker-end="url(#document-arrow)" />`;
    byId("vector-plot").setAttribute("viewBox", `0 0 ${width} ${height}`);
    byId("vector-plot").innerHTML = `
      <title id="vector-plot-title">问题向量与文档向量</title>
      <desc id="vector-plot-desc">q 为 [1, 0]，d 为 [${number(vector[0])}, ${number(vector[1])}]。两根箭头都从原点出发，使用相同坐标比例。</desc>
      <defs>
        <marker id="query-arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto"><path d="M 0 0 L 10 5 L 0 10 Z" fill="#345bc3" /></marker>
        <marker id="document-arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto"><path d="M 0 0 L 10 5 L 0 10 Z" fill="#176c51" /></marker>
      </defs>
      ${grid}
      <line class="axis" x1="15" y1="${originY}" x2="${width - 15}" y2="${originY}" />
      <line class="axis" x1="${originX}" y1="15" x2="${originX}" y2="${originY + 8}" />
      <text x="${width - 16}" y="${originY - 8}" text-anchor="end">x</text>
      <text x="${originX + 9}" y="20">y</text>
      <text x="${originX - 8}" y="${originY + 18}" text-anchor="end">0</text>
      <line x1="${originX}" y1="${originY}" x2="${x(1)}" y2="${originY}" stroke="#345bc3" stroke-width="4" marker-end="url(#query-arrow)" />
      ${documentArrow}
      <text class="vector-label" x="${x(1)}" y="${originY + 39}" text-anchor="middle">q [1, 0]</text>
      <text class="vector-label" x="${x(vector[0]) + (vector[0] < 0 ? -7 : 7)}" y="${y(vector[1]) - 14}" text-anchor="${vector[0] < 0 ? "end" : "start"}">d</text>`;
  }

  function updateVectors() {
    const angle = Number(angleInput.value);
    const length = Number(lengthInput.value);
    const effectiveLength = normalizeInput.checked && length > 0 ? 1 : length;
    const radians = (angle * Math.PI) / 180;
    const vector = [effectiveLength * Math.cos(radians), effectiveLength * Math.sin(radians)];
    const stats = vectorStats([1, 0], vector);
    byId("angle-value").textContent = `${angle}°`;
    byId("length-value").textContent = length.toFixed(2);
    byId("cosine-value").textContent = number(stats.cosine);
    byId("dot-value").textContent = number(stats.dot);
    byId("distance-value").textContent = number(stats.distance);
    byId("vector-detail").textContent =
      length === 0
        ? "零向量没有方向，无法归一化，余弦无定义。点积为 0，不能用它代替余弦。"
        : `当前参与计算的 d 为 [${number(vector[0])}, ${number(vector[1])}]，长度为 ${effectiveLength.toFixed(2)}。${normalizeInput.checked ? "已先归一化，q 也为单位长度，因此点积与余弦相同。" : "余弦比较方向，点积还受到长度影响。"}`;
    drawVectors(vector);
  }

  [angleInput, lengthInput, normalizeInput].forEach((input) =>
    input.addEventListener("input", updateVectors),
  );
  byId("reset-vectors").addEventListener("click", () => {
    angleInput.value = "60";
    lengthInput.value = "1";
    normalizeInput.checked = false;
    updateVectors();
  });
  new ResizeObserver(updateVectors).observe(board);
  updateVectors();

  const documents = [
    { id: "d1", title: "虚拟环境", relevant: false },
    { id: "d2", title: "超时与有限重试", relevant: true },
    { id: "d3", title: "日志级别", relevant: false },
    { id: "d4", title: "记录重试尝试", relevant: true },
    { id: "d5", title: "Schema 验证", relevant: false },
  ];
  let order = documents.map((entry) => entry.id);
  const list = byId("ranking-list");

  function updateRanking() {
    const k = Number(byId("top-k").value);
    const answerable = byId("answer-case").value === "answerable";
    const relevant = answerable ? ["d2", "d4"] : [];
    const stats = rankingMetrics(order, relevant, k);
    byId("k-value").textContent = `K = ${k}`;
    list.innerHTML = order
      .map((id, index) => {
        const entry = documents.find((item) => item.id === id);
        return `<li data-included="${index < k}"><span class="rank-position">${index + 1}</span><div><div class="document-title">${entry.id} · ${entry.title}</div><div class="document-meta">${answerable && entry.relevant ? "相关" : "无关"} · ${index < k ? "计入前 K 篇" : "排在前 K 篇以外"}</div></div><div class="move-buttons"><button type="button" data-doc="${id}" data-direction="-1" aria-label="将 ${id} 上移一位" ${index === 0 ? "disabled" : ""}>上移</button><button type="button" data-doc="${id}" data-direction="1" aria-label="将 ${id} 下移一位" ${index === order.length - 1 ? "disabled" : ""}>下移</button></div></li>`;
      })
      .join("");
    ["recall", "precision", "rr"].forEach((key) => {
      const name = { recall: "Recall", precision: "Precision", rr: "RR" }[key];
      byId(`${key}-label`).textContent = `${name}@${k}`;
      byId(`${key}-value`).textContent = stats[key] === null ? "不适用" : number(stats[key]);
    });
    if (answerable) {
      byId("ranking-detail").textContent =
        `前 ${k} 篇命中 ${stats.hits} 篇相关资料。${stats.firstRank === null ? "前 K 篇没有相关资料。" : `第一篇相关资料位于第 ${stats.firstRank}。`}`;
      byId("ranking-formula").textContent =
        `Recall = ${stats.hits} / 2，Precision = ${stats.hits} / ${k}，RR = ${stats.firstRank === null ? "0" : `1 / ${stats.firstRank}`}`;
      byId("case-detail").textContent =
        "这里只计算一个问题的 RR。多个有答案问题分别计算后取平均，才得到 MRR。";
    } else {
      byId("ranking-detail").textContent =
        "另一个教学问题是“怎样配置扫描仪的纸张尺寸”。这批资料没有相应依据，相关集合为空，列表仍可返回内容。";
      byId("ranking-formula").textContent =
        `相关文档数为 0，Recall 与 RR 不适用。Precision = 0 / ${k}。`;
      byId("case-detail").textContent =
        "按本课约定，无答案问题单独报告，三项均不计入有答案问题的均值。返回一份排名不能证明程序已经检测出无答案。";
    }
  }

  list.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-doc]");
    if (!button || button.disabled) return;
    const id = button.dataset.doc;
    const direction = Number(button.dataset.direction);
    const oldIndex = order.indexOf(id);
    const newIndex = oldIndex + direction;
    if (newIndex < 0 || newIndex >= order.length) return;
    [order[oldIndex], order[newIndex]] = [order[newIndex], order[oldIndex]];
    updateRanking();
    const same = list.querySelector(`button[data-doc="${id}"][data-direction="${direction}"]`);
    const fallback = list.querySelector(`button[data-doc="${id}"]:not(:disabled)`);
    (same && !same.disabled ? same : fallback)?.focus();
  });
  byId("top-k").addEventListener("input", updateRanking);
  byId("answer-case").addEventListener("change", updateRanking);
  byId("reset-ranking").addEventListener("click", () => {
    order = documents.map((entry) => entry.id);
    byId("top-k").value = "3";
    byId("answer-case").value = "answerable";
    updateRanking();
  });
  updateRanking();

  function updateFusion() {
    const c = Number(byId("rrf-c").value);
    const result = rrf(
      [
        ["A", "B", "C", "D", "E"],
        ["D", "B", "C", "A", "F"],
      ],
      c,
    );
    byId("c-value").textContent = String(c);
    byId("fusion-body").innerHTML = result
      .map(
        (entry, index) =>
          `<tr${index === 0 ? ' class="fusion-first"' : ""}><th scope="row">${entry.id}</th>${entry.contributions.map((value, source) => `<td>${entry.ranks[source] === null ? "缺席 · 0" : `第 ${entry.ranks[source]} · ${value.toFixed(6)}`}</td>`).join("")}<td>${entry.score.toFixed(6)}</td></tr>`,
      )
      .join("");
    byId("fusion-order").textContent =
      `c 为 ${c}，融合顺序为 ${result.map((entry) => entry.id).join("、")}。`;
  }
  byId("rrf-c").addEventListener("input", updateFusion);
  updateFusion();
}

if (typeof module !== "undefined" && module.exports)
  module.exports = { vectorStats, rankingMetrics, rrf };
if (typeof document !== "undefined") setupLab();
