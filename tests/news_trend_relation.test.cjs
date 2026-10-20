const assert = require("node:assert/strict");
const classify = require("../v2/frontend/news_trend_relation.js");

assert.equal(classify("BULLISH", "BEARISH").relation, "REVERSAL");
assert.equal(classify("BEARISH", "BULLISH").relation, "REVERSAL");
assert.equal(classify("BULLISH", "BULLISH").relation, "CONTINUATION");
assert.equal(classify("BEARISH", "BEARISH").relation, "CONTINUATION");
assert.equal(classify("MIXED", "BULLISH").relation, "NEUTRAL");
assert.equal(classify("NEUTRAL", "BEARISH").active, 1);
assert.equal(classify("BULLISH", null).relation, "UNVERIFIED");
assert.equal(classify("BEARISH", "MIXED").active, null);

console.log("News-to-trend relation cases passed.");
