import { runBacktest } from "./backtest-engine.js";

self.onmessage = ({ data: { files, strategy } }) => {
  try {
    const result = runBacktest(files, strategy);
    self.postMessage({ progress: "Calculating market-favourite reference…" });
    const reference = runBacktest(files, {
      ...strategy, rule: { pick: "market_favourite", conditions: [] },
      universe: { ...strategy.universe, team_side: false },
      stake: { method: "flat", unit: strategy.stake.unit },
    }, { breakdowns: false });
    self.postMessage({ result, reference });
  } catch (error) {
    self.postMessage({ error: error.message });
  }
};
