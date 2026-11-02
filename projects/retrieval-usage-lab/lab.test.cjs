const test = require("node:test");
const assert = require("node:assert/strict");
const { vectorStats, rankingMetrics, rrf } = require("./lab.js");

function near(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-10, `${actual} differs from ${expected}`);
}

test("vector direction, scale and normalization match the lesson examples", () => {
  near(vectorStats([1, 0], [3, 4]).cosine, 0.6);
  near(vectorStats([1, 0], [6, 8]).cosine, 0.6);
  near(vectorStats([1, 0], [0, 1]).cosine, 0);
  near(vectorStats([1, 0], [-1, 0]).cosine, -1);
  const normalized = vectorStats([1, 0], [0.6, 0.8]);
  near(normalized.dot, normalized.cosine);
  near(normalized.distance ** 2, 2 - 2 * normalized.cosine);
});

test("cosine and raw dot product can rank the same documents differently", () => {
  const a = vectorStats([1, 0], [0.8, 0.6]);
  const b = vectorStats([1, 0], [2, 2]);
  assert.ok(a.cosine > b.cosine);
  assert.ok(a.dot < b.dot);
});

test("the vector display distinguishes undefined cosine from orthogonality", () => {
  assert.equal(vectorStats([1, 0], [0, 0]).cosine, null);
  assert.equal(vectorStats([1, 0], [0, 1]).cosine, 0);
  assert.throws(() => vectorStats([], []), TypeError);
  assert.throws(() => vectorStats([1], [1, 0]), RangeError);
  assert.throws(() => vectorStats([1, 0], [NaN, 1]), TypeError);
  assert.throws(() => vectorStats([1, 0], [Infinity, 1]), TypeError);
});

test("ranking metrics match the worked table at K of 1, 3 and 5", () => {
  const ranking = ["A", "B", "C", "D", "E"];
  const relevant = ["B", "D"];
  assert.deepEqual(rankingMetrics(ranking, relevant, 1), {
    hits: 0,
    recall: 0,
    precision: 0,
    rr: 0,
    firstRank: null,
  });
  const three = rankingMetrics(ranking, relevant, 3);
  near(three.recall, 0.5);
  near(three.precision, 1 / 3);
  near(three.rr, 0.5);
  const five = rankingMetrics(ranking, relevant, 5);
  near(five.recall, 1);
  near(five.precision, 0.4);
  near(five.rr, 0.5);
});

test("finding another relevant document can change recall without changing RR", () => {
  const before = rankingMetrics(["A", "B", "C", "D"], ["B", "D"], 3);
  const after = rankingMetrics(["A", "B", "D", "C"], ["B", "D"], 3);
  assert.ok(after.recall > before.recall);
  assert.equal(after.rr, before.rr);
});

test("precision keeps K as denominator for short or empty results", () => {
  near(rankingMetrics(["B"], ["B"], 3).precision, 1 / 3);
  assert.equal(rankingMetrics([], ["B"], 3).rr, 0);
  assert.deepEqual(rankingMetrics(["A"], [], 3), {
    hits: 0,
    recall: null,
    precision: 0,
    rr: null,
    firstRank: null,
  });
});

test("invalid K and duplicate IDs cannot inflate the displayed metrics", () => {
  assert.throws(() => rankingMetrics(["A", "A"], ["A"], 2), TypeError);
  assert.throws(() => rankingMetrics(["A"], ["A", "A"], 2), TypeError);
  for (const k of [0, -1, 1.5]) assert.throws(() => rankingMetrics(["A"], ["A"], k), RangeError);
});

test("RRF matches hand calculation, missing-source contributions and ID tie order", () => {
  const rankings = [
    ["A", "B", "C", "D", "E"],
    ["D", "B", "C", "A", "F"],
  ];
  const result = rrf(rankings, 1);
  assert.deepEqual(
    result.map((entry) => entry.id),
    ["A", "D", "B", "C", "E", "F"],
  );
  near(result.find((entry) => entry.id === "A").score, 0.7);
  assert.deepEqual(result.find((entry) => entry.id === "E").contributions, [1 / 6, 0]);
  assert.deepEqual(result.find((entry) => entry.id === "F").ranks, [null, 5]);
  assert.equal(rrf(rankings, 60)[0].id, "B");
});

test("RRF rejects duplicate entries within a source and invalid constants", () => {
  assert.throws(() => rrf([["A", "A"]], 1), TypeError);
  for (const c of [0, -1, Infinity, NaN]) assert.throws(() => rrf([["A"]], c), RangeError);
  assert.deepEqual(rrf([[], []], 1), []);
});
