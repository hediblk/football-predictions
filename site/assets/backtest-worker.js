import { normalizeStrategy, runBacktest } from "./backtest-engine.js";

self.onmessage = ({ data: { files, strategy, comparisons = [] } }) => {
  try {
    const result = runBacktest(files, strategy);
    self.postMessage({ progress: "Calculating market-favourite reference…" });
    const reference = runBacktest(files, {
      ...strategy, rule: { pick: "market_favourite", conditions: [] },
      universe: { ...strategy.universe, team_side: false },
      stake: { method: "flat", unit: strategy.stake.unit },
    }, { breakdowns: false });
    const compared = comparisons.map(({ name, strategy: input }, index) => {
      self.postMessage({ progress: `Comparing saved strategy ${index + 1} of ${comparisons.length}…` });
      const normalized = normalizeStrategy(input);
      return { name, strategy: normalized, result: runBacktest(files, normalized) };
    });
    self.postMessage({ result, reference, comparisons: compared });
  } catch (error) {
    self.postMessage({ error: error.message });
  }
};
