(function (root, factory) {
  const classify = factory();
  if (typeof module === "object" && module.exports) module.exports = classify;
  if (root) root.classifyNewsTrendRelation = classify;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  // impact and trend are directional context labels, never probability estimates.
  return function classifyNewsTrendRelation(impact, trend) {
    if (!["BULLISH", "BEARISH"].includes(impact)) {
      return { label: "Neutral / no clear impact", tone: "blue", active: 1, relation: "NEUTRAL" };
    }
    if (!["BULLISH", "BEARISH"].includes(trend)) {
      return {
        label: (impact === "BULLISH" ? "Potential positive" : "Potential negative") + " · trend unverified",
        tone: impact === "BULLISH" ? "green" : "red",
        active: null,
        relation: "UNVERIFIED",
      };
    }
    const reversal = impact !== trend;
    return {
      label: reversal ? "Supports reversal" : "Supports continuation",
      tone: impact === "BULLISH" ? "green" : "red",
      active: reversal ? 0 : 2,
      relation: reversal ? "REVERSAL" : "CONTINUATION",
    };
  };
});
