  const SIDES = ["home", "draw", "away"];
  const LEAGUE_ORDER = { PL: "E0", PD: "SP1", BL1: "D1", SA: "I1", FL1: "F1" };
  const PICKS = new Set(["model_favourite", "market_favourite", "edge", "disagreement", ...SIDES]);
  const FIELDS = new Set(["p", "edge", "gap", "price", "xg_diff", "xg_total", "elo_agrees", "rating_gap", "stakes"]);
  const OPS = new Set([">=", ">", "<=", "<", "==", "!=", "between"]);
  const METHODS = new Set(["flat", "fraction", "probability", "edge", "kelly", "to_win"]);
  const BOOKS = new Set(["avg", "max", "bet365", "pinnacle", "betfair", "betfair_exchange", "betvictor", "betway", "paddypower", "skybet", "betfred", "bwin", "williamhill", "ladbrokes", "interwetten", "1xbet", "betmgm"]);
  const BOOK_ALIASES = { average: "avg", best: "max" };
  const LEAGUES = new Set(Object.keys(LEAGUE_ORDER));

  function fail(message) { throw new Error(message); }
  function finite(value) { return typeof value === "number" && Number.isFinite(value); }
  function date(value) {
    const d = new Date(value);
    return Number.isFinite(d.getTime()) ? d : null;
  }
  function utcDay(value) {
    const d = date(value);
    return d ? d.toISOString().slice(0, 10) : null;
  }
  function numbers(triple, label) {
    if (!Array.isArray(triple) || triple.length !== 3 || triple.some((x) => !finite(x) || x < 0 || x > 1)) fail(`Invalid ${label} probabilities`);
    const total = triple.reduce((a, b) => a + b, 0);
    if (!(total > 0) || Math.abs(total - 1) > 1e-3) fail(`Invalid ${label} probabilities`);
    return triple.map((x) => x / total);
  }
  function decodeSeason(file) {
    if (!file || typeof file !== "object" || file.version !== 1 || !file.columns || typeof file.columns !== "object") fail("Invalid season file");
    const columns = file.columns;
    const names = Object.keys(columns);
    if (!names.length || !Array.isArray(columns.comp)) fail("Season file has no column rows");
    const length = columns.comp.length;
    if (!Number.isInteger(Number(file.season))) fail("Invalid season year");
    if (names.some((name) => !Array.isArray(columns[name]) || columns[name].length !== length)) fail("Season columns must have equal lengths");
    const rows = [];
    for (let i = 0; i < length; i += 1) {
      const score = columns.score?.[i];
      const prices = columns.prices?.[i] || {};
      const row = {
        id: columns.id?.[i] ?? null, comp: columns.comp[i], season: Number(file.season),
        kickoff: columns.kickoff?.[i], home: columns.home?.[i], away: columns.away?.[i],
        home_id: columns.home_id?.[i] ?? null, away_id: columns.away_id?.[i] ?? null,
        home_key: columns.home_key?.[i] ?? null, away_key: columns.away_key?.[i] ?? null,
        matchday: columns.matchday?.[i] ?? null, forecast: columns.forecast?.[i], at: columns.at?.[i],
        score: Array.isArray(score) ? score.slice() : score ?? null,
        xg: columns.xg?.[i] ?? null, p: columns.p?.[i], elo: columns.elo?.[i] ?? null,
        exp: columns.exp?.[i] ?? null, stakes: columns.stakes?.[i] ?? null,
        rating_gap: columns.rating_gap?.[i] ?? null, prices
      };
      if (!LEAGUES.has(row.comp) || !["replayed", "published"].includes(row.forecast) || !date(row.kickoff) || !date(row.at) || date(row.at) >= date(row.kickoff)) fail(`Invalid fixture row ${i}`);
      row.p = numbers(row.p, "forecast");
      if (row.elo != null) row.elo = numbers(row.elo, "Elo");
      if (!Array.isArray(row.score) || row.score.length !== 2 || row.score.some((x) => !Number.isInteger(x) || x < 0)) fail(`Invalid score row ${i}`);
      if ([row.home_id, row.away_id].some((id) => id != null && (!Number.isInteger(id) || id <= 0))) fail(`Invalid team ID row ${i}`);
      if (row.matchday != null && (!Number.isInteger(row.matchday) || row.matchday < 1)) fail(`Invalid matchday row ${i}`);
      if (!prices || typeof prices !== "object" || Array.isArray(prices)) fail(`Invalid prices row ${i}`);
      rows.push(row);
    }
    return rows;
  }
  function validateDecodedRows(rows) {
    if (!Array.isArray(rows)) fail("Expected decoded rows");
    return rows.map((source, index) => {
      if (!source || typeof source !== "object" || !LEAGUES.has(source.comp) || !Number.isInteger(source.season) || !["replayed", "published"].includes(source.forecast)) fail(`Invalid decoded row ${index}`);
      const kickoff = date(source.kickoff), at = date(source.at);
      if (!kickoff || !at || at >= kickoff || typeof source.home !== "string" || typeof source.away !== "string") fail(`Invalid decoded row ${index}`);
      const p = numbers(source.p, "forecast"), elo = source.elo == null ? null : numbers(source.elo, "Elo");
      if (!Array.isArray(source.score) || source.score.length !== 2 || source.score.some((x) => !Number.isInteger(x) || x < 0)) fail(`Invalid decoded score row ${index}`);
      if ([source.home_id, source.away_id].some((id) => id != null && (!Number.isInteger(id) || id <= 0))) fail(`Invalid decoded team ID row ${index}`);
      if (source.matchday != null && (!Number.isInteger(source.matchday) || source.matchday < 1)) fail(`Invalid decoded matchday row ${index}`);
      if (source.prices != null && (typeof source.prices !== "object" || Array.isArray(source.prices))) fail(`Invalid decoded prices row ${index}`);
      if (source.exp != null && (!Array.isArray(source.exp) || source.exp.length !== 2 || source.exp.some((x) => !finite(x) || x < 0))) fail(`Invalid decoded expected-goals row ${index}`);
      if (source.xg != null && (!Array.isArray(source.xg) || source.xg.length !== 2 || source.xg.some((x) => !finite(x) || x < 0))) fail(`Invalid decoded xG row ${index}`);
      if (source.rating_gap != null && !finite(source.rating_gap)) fail(`Invalid decoded rating gap row ${index}`);
      if (source.stakes != null && typeof source.stakes !== "boolean") fail(`Invalid decoded Stakes row ${index}`);
      return { ...source, p, elo, prices: source.prices || {} };
    });
  }
  function normalizeStrategy(input) {
    if (!input || typeof input !== "object" || Array.isArray(input)) fail("Strategy must be an object");
    if (input.v !== undefined && input.v !== 1) fail("Unsupported strategy version");
    const universe = input.universe || {};
    const market = input.market ?? "1x2";
    if (market !== "1x2") fail("Unsupported market");
    const bookRaw = input.execution?.book ?? "bet365";
    const book = BOOK_ALIASES[bookRaw] || bookRaw;
    if (!BOOKS.has(book)) fail("Invalid price book");
    const timing = input.execution?.timing ?? "pre";
    if (!["pre", "close"].includes(timing)) fail("Invalid price timing");
    const pickRaw = input.rule?.pick ?? "model_favourite";
    const pick = ({ model: "model_favourite", market: "market_favourite" })[pickRaw] || pickRaw;
    if (!PICKS.has(pick)) fail("Invalid selection rule");
    const conditions = input.rule?.conditions ?? [];
    if (!Array.isArray(conditions)) fail("Conditions must be an array");
    const cleanConditions = conditions.map((c) => {
      if (!c || !FIELDS.has(c.field) || !OPS.has(c.op)) fail("Unsupported condition field or operator");
      const value = c.value;
      if (c.op === "between") {
        if (!Array.isArray(value) || value.length !== 2 || value.some((v) => !finite(v)) || value[0] > value[1]) fail("Invalid between condition");
      } else if (c.field === "elo_agrees" || c.field === "stakes") {
        if (typeof value !== "boolean") fail(`Invalid ${c.field} condition`);
      } else if (!finite(value)) fail("Condition value must be finite");
      return { field: c.field, op: c.op, value: Array.isArray(value) ? value.slice() : value };
    });
    const comps = list(universe.comps, (x) => { if (!LEAGUES.has(x)) fail("Invalid competition"); return x; });
    const seasons = list(universe.seasons, (x) => { const n = Number(x); if (!Number.isInteger(n)) fail("Invalid season"); return n; });
    const include = list(universe.include, idValue), exclude = list(universe.exclude, idValue);
    const venue = universe.venue ?? "any";
    if (!new Set(["any", "home", "away"]).has(venue)) fail("Invalid venue");
    const teamSide = universe.team_side ?? false;
    if (typeof teamSide !== "boolean") fail("Invalid team_side filter");
    let matchdays = universe.matchdays ?? [];
    if (!Array.isArray(matchdays) || (matchdays.length && (matchdays.length !== 2 || matchdays.some((x) => !Number.isInteger(x) || x < 1 || x > 38) || matchdays[0] > matchdays[1]))) fail("Invalid matchday range");
    let months = list(universe.months, (x) => { if (!Number.isInteger(x) || x < 1 || x > 12) fail("Invalid month"); return x; });
    let weekdays = universe.weekdays ?? [];
    if (universe.weekday !== undefined) weekdays = universe.weekday === "midweek" ? [1, 2, 3] : universe.weekday;
    weekdays = list(weekdays, (x) => { if (!Number.isInteger(x) || x < 0 || x > 6) fail("Invalid weekday"); return x; });
    const forecast = universe.forecast ?? "replayed";
    if (!new Set(["replayed", "published"]).has(forecast)) fail("Invalid forecast kind");
    const method = input.stake?.method ?? "flat";
    if (!METHODS.has(method)) fail("Invalid staking method");
    const unit = input.stake?.unit ?? 1;
    const fraction = input.stake?.fraction ?? (method === "kelly" ? 0.25 : 0.01);
    const cap = input.stake?.cap ?? 0.03;
    const dailyCap = input.stake?.daily_cap ?? 1;
    const trust = input.stake?.trust ?? 1;
    const base = input.stake?.base ?? "start_of_day";
    const bankroll = input.bankroll ?? 100;
    if (![unit, fraction, cap, dailyCap, trust, bankroll].every(finite) || unit <= 0 || fraction <= 0 || fraction > 1 || cap <= 0 || cap > 1 || dailyCap <= 0 || dailyCap > 1 || trust < 0 || trust > 1 || bankroll <= 0 || base !== "start_of_day") fail("Invalid staking or bankroll value");
    const bands = input.stake?.bands ?? null;
    if (method === "probability" && bands !== null && (!Array.isArray(bands) || bands.some((b) => !b || !finite(b.min) || !finite(b.max) || !finite(b.stake) || b.min < 0 || b.max > 1 || b.min > b.max || b.stake < 0))) fail("Invalid probability bands");
    const commission = input.execution?.commission ?? 0;
    if (!finite(commission) || commission < 0 || commission >= 1) fail("Invalid commission");
    if ((teamSide || venue !== "any") && !include.length) fail("Venue and team-side filters require an included team");
    if (forecast === "published" && timing === "pre") fail("Published forecasts support closing prices only");
    return {
      v: 1,
      universe: { comps, seasons, include, exclude, venue, team_side: teamSide, matchdays: Array.isArray(matchdays) ? matchdays.slice() : [], months, weekdays, forecast },
      market: "1x2", rule: { pick, conditions: cleanConditions },
      stake: { method, unit, fraction, cap, daily_cap: dailyCap, trust, base, bands: bands ? bands.map((b) => ({ min: b.min, max: b.max, stake: b.stake })) : null },
      execution: { book, timing, commission: input.execution?.commission ?? (book === "betfair_exchange" ? 0.02 : 0) }, bankroll
    };
  }
  function list(value, clean) { if (value == null) return []; if (!Array.isArray(value)) fail("Expected a list"); return [...new Set(value.map(clean))]; }
  function idValue(value) { const n = Number(value); if (!Number.isInteger(n) || n <= 0) fail("Invalid team ID"); return n; }
  function encodeStrategy(strategy) { return `#backtest/${encodeURIComponent(JSON.stringify(normalizeStrategy(strategy)))}`; }
  function decodeStrategy(hash) {
    const match = String(hash).match(/(?:^#?backtest\/)(.+)$/);
    if (!match) fail("Invalid backtest URL state");
    try { return normalizeStrategy(JSON.parse(decodeURIComponent(match[1]))); } catch (error) { fail(`Invalid backtest URL state: ${error.message}`); }
  }
  function marketPrices(row, strategy) {
    if (row.forecast === "published" && strategy.execution.timing !== "close") return null;
    const pair = row.prices?.[strategy.execution.book]?.[strategy.execution.timing];
    if (!Array.isArray(pair) || pair.length !== 3 || pair.some((x) => !finite(x) || x <= 1)) return null;
    return pair;
  }
  function argmax(values) { let best = 0; for (let i = 1; i < values.length; i += 1) if (values[i] > values[best]) best = i; return best; }
  function priceBand(price) { return price < 1.5 ? "1-1.5" : price < 2 ? "1.5-2" : price < 3 ? "2-3" : price < 5 ? "3-5" : "5+"; }
  function normalizedName(name) { return String(name ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]/g, ""); }
  function result(row) { return row.score[0] > row.score[1] ? 0 : row.score[0] === row.score[1] ? 1 : 2; }
  function selectedTeam(row, side) { return side === 0 ? row.home_id : side === 2 ? row.away_id : null; }
  function universeMatch(row, u) {
    if (u.comps.length && !u.comps.includes(row.comp)) return false;
    if (u.seasons.length && !u.seasons.includes(row.season)) return false;
    if (row.forecast !== u.forecast) return false;
    const teamIds = [row.home_id, row.away_id].filter((x) => x != null).map(Number);
    if (u.include.length && !u.include.some((id) => teamIds.includes(id))) return false;
    if (u.exclude.some((id) => teamIds.includes(id))) return false;
    if (u.venue !== "any" && u.include.length && !u.include.some((id) => (u.venue === "home" ? row.home_id : row.away_id) === id)) return false;
    const kickoff = date(row.kickoff);
    if (!kickoff) return false;
    const month = kickoff.getUTCMonth() + 1;
    const weekday = (kickoff.getUTCDay() + 6) % 7;
    if (u.months.length && !u.months.includes(month)) return false;
    if (u.weekdays.length && !u.weekdays.includes(weekday)) return false;
    if (u.matchdays.length && !(u.matchdays[0] === 1 && u.matchdays[1] === 38) && (!Number.isInteger(row.matchday) || row.matchday < u.matchdays[0] || row.matchday > u.matchdays[1])) return false;
    return true;
  }
  function conditionValue(field, row, bet, prices, probabilities) {
    const { side, price, probability, edge } = bet;
    if (field === "p") return probability;
    if (field === "edge") return edge;
    if (field === "price") return price;
    if (field === "gap") {
      const marketP = (1 / prices[side]) / prices.reduce((sum, p) => sum + 1 / p, 0);
      return probabilities[side] - marketP;
    }
    if (field === "xg_diff") {
      if (!Array.isArray(row.exp) || row.exp.length !== 2 || row.exp.some((x) => !finite(x))) return null;
      return side === 0 ? row.exp[0] - row.exp[1] : side === 2 ? row.exp[1] - row.exp[0] : Math.abs(row.exp[0] - row.exp[1]);
    }
    if (field === "xg_total") return Array.isArray(row.exp) && row.exp.length === 2 && row.exp.every(finite) ? row.exp[0] + row.exp[1] : null;
    if (field === "elo_agrees") return row.elo == null ? null : argmax(row.elo) === side;
    if (field === "rating_gap") return !finite(row.rating_gap) ? null : side === 0 ? row.rating_gap : side === 2 ? -row.rating_gap : Math.abs(row.rating_gap);
    if (field === "stakes") return typeof row.stakes === "boolean" ? row.stakes : null;
    return null;
  }
  function passes(value, condition) {
    if (value == null) return false;
    const v = condition.value;
    switch (condition.op) {
      case ">=": return value >= v; case ">": return value > v; case "<=": return value <= v;
      case "<": return value < v; case "==": return value === v; case "!=": return value !== v;
      case "between": return value >= v[0] && value <= v[1]; default: return false;
    }
  }
  function bootstrapValue(seed, counter) {
    let state = (seed + Math.imul(counter, 0x6d2b79f5)) >>> 0;
    let bits = Math.imul(state ^ (state >>> 15), state | 1);
    bits ^= bits + Math.imul(bits ^ (bits >>> 7), bits | 61);
    bits ^= bits >>> 14;
    return (bits >>> 0) / 4294967296;
  }
  function percentile(values, q) {
    const sorted = values.slice().sort((a, b) => a - b);
    if (!sorted.length) return null;
    const position = (sorted.length - 1) * q, lower = Math.floor(position), fraction = position - lower;
    return sorted[lower] * (1 - fraction) + sorted[Math.min(lower + 1, sorted.length - 1)] * fraction;
  }
  function summarize(bets, options) {
    const staked = bets.reduce((sum, bet) => sum + bet.stake, 0);
    const profit = bets.reduce((sum, bet) => sum + bet.profit, 0);
    const byDay = new Map();
    for (const bet of bets) {
      const totals = byDay.get(bet.day) || [0, 0];
      totals[0] += bet.stake; totals[1] += bet.profit; byDay.set(bet.day, totals);
    }
    const days = [...byDay.keys()].sort();
    const daily = days.map((day) => byDay.get(day));
    let roiLow = null, roiHigh = null;
    if (days.length > 1 && staked > 0) {
      const samples = [];
      for (let i = 0; i < options.bootstrap; i += 1) {
        let sampledStake = 0, sampledProfit = 0;
        for (let j = 0; j < days.length; j += 1) {
          const index = Math.floor(bootstrapValue(options.seed >>> 0, i * days.length + j + 1) * days.length);
          sampledStake += daily[index][0]; sampledProfit += daily[index][1];
        }
        samples.push(sampledProfit / sampledStake);
      }
      roiLow = percentile(samples, 0.025); roiHigh = percentile(samples, 0.975);
    }
    let drawdown = 0, longest = 0;
    const seasons = [...new Set(bets.map((bet) => bet.season))].sort((a, b) => a - b);
    for (const season of seasons) {
      const rows = bets.filter((bet) => bet.season === season);
      const byDay = new Map();
      for (const bet of rows) byDay.set(bet.day, (byDay.get(bet.day) || 0) + bet.profit);
      let balance = 0, high = 0, run = 0;
      for (const day of [...byDay.keys()].sort()) { balance += byDay.get(day); high = Math.max(high, balance); drawdown = Math.max(drawdown, high - balance); }
      for (const bet of rows) { run = bet.won ? 0 : run + 1; longest = Math.max(longest, run); }
    }
    const clvBets = bets.filter((bet) => finite(bet.closing_price));
    return {
      bets: bets.length, staked, profit, roi: staked ? profit / staked : null,
      roi_low: roiLow, roi_high: roiHigh, clusters: days.length,
      strike_rate: bets.length ? bets.filter((bet) => bet.won).length / bets.length : null,
      implied_strike_rate: bets.length ? bets.reduce((sum, bet) => sum + 1 / bet.price, 0) / bets.length : null,
      average_price: bets.length ? bets.reduce((sum, bet) => sum + bet.price, 0) / bets.length : null,
      mean_edge: bets.length ? bets.reduce((sum, bet) => sum + bet.edge, 0) / bets.length : null,
      clv_bets: clvBets.length, clv: clvBets.length ? clvBets.reduce((sum, bet) => sum + bet.price / bet.closing_price - 1, 0) / clvBets.length : null,
      max_drawdown_units: drawdown, longest_losing_run: longest
    };
  }
  function stakeBets(selected, strategy) {
    const s = strategy.stake, bankroll = strategy.bankroll;
    const sorted = selected.slice().sort((a, b) => a.season - b.season || a.bet_day.localeCompare(b.bet_day) || compareRows(a, b));
    if (!new Set(["fraction", "kelly"]).has(s.method)) return sorted.map((bet) => ({ ...bet, stake: unitStake(bet, s) })).filter((bet) => bet.stake > 0);
    const stakes = new Array(sorted.length).fill(0);
    let season = null, balance = bankroll, settledAt = null;
    for (let index = 0; index < sorted.length;) {
      const batchDay = sorted[index].bet_day, batchSeason = sorted[index].season;
      let end = index + 1;
      while (end < sorted.length && sorted[end].bet_day === batchDay && sorted[end].season === batchSeason) end += 1;
      if (batchSeason !== season) { season = batchSeason; balance = bankroll; settledAt = null; }
      if (settledAt && settledAt > new Date(`${batchDay}T00:00:00Z`)) fail("Overlapping unsettled betting batches need explicit reserved-cash settlement");
      const group = sorted.slice(index, end);
      const fractions = group.map((bet) => s.method === "fraction" ? Math.min(s.fraction, s.cap) : (bet.trusted_probability * bet.effective_price - 1) > 0 ? Math.min(s.cap, s.fraction * (bet.trusted_probability * bet.effective_price - 1) / (bet.effective_price - 1)) : 0);
      const total = fractions.reduce((a, b) => a + b, 0), scale = Math.min(1, s.daily_cap / Math.max(total, Number.EPSILON));
      const stakesForBatch = fractions.map((value) => balance * value * scale);
      group.forEach((bet, i) => { stakes[index + i] = stakesForBatch[i]; });
      const batchProfit = group.reduce((sum, bet, i) => sum + stakesForBatch[i] * bet.return, 0);
      balance = Math.max(0, balance + batchProfit);
      const lastDay = utcDay(Math.max(...group.map((bet) => date(bet.kickoff).getTime())));
      settledAt = new Date(`${lastDay}T00:00:00Z`);
      settledAt.setUTCDate(settledAt.getUTCDate() + 1);
      index = end;
    }
    return sorted.map((bet, i) => ({ ...bet, stake: stakes[i] })).filter((bet) => bet.stake > 0).sort(compareRows);
  }
  function unitStake(bet, s) {
    if (s.method === "flat") return s.unit;
    if (s.method === "probability") {
      if (!s.bands) return s.unit * bet.probability / 0.5;
      const band = s.bands.find((b) => bet.probability >= b.min && bet.probability <= b.max);
      return band ? band.stake : 0;
    }
    if (s.method === "edge") return s.unit * Math.max(0, bet.edge) / 0.05;
    if (s.method === "to_win") return s.unit / (bet.effective_price - 1);
    return 0;
  }
  function compareRows(a, b) {
    return date(a.kickoff).getTime() - date(b.kickoff).getTime() || String(LEAGUE_ORDER[a.comp]).localeCompare(String(LEAGUE_ORDER[b.comp])) || String(a.home_key || normalizedName(a.home)).localeCompare(String(b.home_key || normalizedName(b.home)));
  }
  function runBacktest(filesOrRows, strategyInput, options = {}) {
    const strategy = normalizeStrategy(strategyInput);
    const opts = { bootstrap: options.bootstrap ?? 2000, seed: options.seed ?? 7 };
    if (!Number.isInteger(opts.bootstrap) || opts.bootstrap < 1 || !Number.isInteger(opts.seed) || opts.seed < 0 || opts.seed >= 2 ** 32) fail("Invalid bootstrap options");
    const source = Array.isArray(filesOrRows) ? filesOrRows : [filesOrRows];
    const decodedRows = Array.isArray(filesOrRows) && (!filesOrRows.length || filesOrRows[0]?.comp);
    const rows = validateDecodedRows(decodedRows ? filesOrRows : source.flatMap((value) => Array.isArray(value) ? value : value?.columns ? decodeSeason(value) : fail("Expected season files or decoded rows")));
    const coverage = { input_rows: rows.length, universe_matches: 0, fully_priced_matches: 0, condition_exclusions: 0, selection_exclusions: 0, zero_stakes: 0, missing_price_voids: 0, bets: 0 };
    const selected = [];
    const u = strategy.universe;
    for (const row of rows) {
      if (!universeMatch(row, u)) continue;
      coverage.universe_matches += 1;
      const prices = marketPrices(row, strategy);
      if (!prices) { coverage.missing_price_voids += 1; continue; }
      coverage.fully_priced_matches += 1;
      let probabilities = numbers(row.p, "forecast");
      const marketProbabilities = prices.map((price) => 1 / price);
      const marketTotal = marketProbabilities.reduce((a, b) => a + b, 0);
      const trustedProbability = (p, i) => strategy.stake.trust * p + (1 - strategy.stake.trust) * marketProbabilities[i] / marketTotal;
      const effectivePrices = prices.map((price) => 1 + (price - 1) * (1 - strategy.execution.commission));
      const edges = probabilities.map((p, i) => p * effectivePrices[i] - 1);
      const model = argmax(probabilities), market = argmax(prices.map((price) => 1 / price));
      let side = strategy.rule.pick === "model_favourite" ? model : strategy.rule.pick === "market_favourite" ? market : strategy.rule.pick === "disagreement" ? (model !== market ? model : null) : strategy.rule.pick === "edge" ? argmax(edges) : SIDES.indexOf(strategy.rule.pick);
      if (side == null) { coverage.selection_exclusions += 1; continue; }
      if (u.team_side && !u.include.includes(Number(selectedTeam(row, side)))) { coverage.selection_exclusions += 1; continue; }
      const effectiveProbability = trustedProbability(probabilities[side], side);
      const bet = {
        id: row.id, comp: row.comp, season: row.season, kickoff: row.kickoff, home: row.home, away: row.away,
        home_id: row.home_id, away_id: row.away_id, home_key: row.home_key, away_key: row.away_key, matchday: row.matchday, at: row.at,
        day: utcDay(row.kickoff), bet_day: strategy.execution.timing === "pre" ? utcDay(row.at) : utcDay(row.kickoff),
        selection: SIDES[side], side, price: prices[side], closing_price: strategy.execution.timing === "pre" && finite(row.prices?.[strategy.execution.book]?.close?.[side]) && row.prices[strategy.execution.book].close[side] > 1 ? row.prices[strategy.execution.book].close[side] : null,
        probability: probabilities[side], trusted_probability: effectiveProbability, edge: probabilities[side] * effectivePrices[side] - 1, effective_price: effectivePrices[side],
        won: result(row) === side, return: result(row) === side ? effectivePrices[side] - 1 : -1, profit: 0, stake: 0,
        score: row.score.slice(), xg: row.xg, exp: row.exp, rating_gap: row.rating_gap, stakes_tag: row.stakes
      };
      const checks = strategy.rule.conditions.every((condition) => passes(conditionValue(condition.field, row, { side, price: prices[side], probability: probabilities[side], edge: edges[side] }, prices, probabilities), condition));
      if (!checks) { coverage.condition_exclusions += 1; continue; }
      selected.push(bet);
    }
    const stakedBets = stakeBets(selected, strategy);
    coverage.zero_stakes = selected.length - stakedBets.length;
    coverage.bets = stakedBets.length;
    for (const bet of stakedBets) bet.profit = bet.stake * bet.return;
    const summary = summarize(stakedBets, opts);
    return {
      strategy, coverage, summary, bets: stakedBets, bankroll: bankrollPath(stakedBets, strategy.bankroll),
      breakdowns: options.breakdowns === false ? [] : breakdown(stakedBets, opts)
    };
  }
  function bankrollPath(bets, initial) {
    const seasons = [...new Set(bets.map((bet) => bet.season))].sort((a, b) => a - b);
    return seasons.flatMap((season) => {
      let balance = initial;
      return [{ season, day: null, bankroll: balance }, ...[...new Set(bets.filter((bet) => bet.season === season).map((bet) => bet.day))].sort().map((day) => {
        balance += bets.filter((bet) => bet.season === season && bet.day === day).reduce((sum, bet) => sum + bet.profit, 0);
        return { season, day, bankroll: balance };
      })];
    });
  }
  function breakdown(bets, options) {
    const groups = {};
    function add(kind, value, bet) { const key = `${kind}:${value}`; (groups[key] ||= { dimension: kind, value: String(value), bets: [] }).bets.push(bet); }
    for (const bet of bets) {
      add("season", bet.season, bet); add("competition", bet.comp, bet);
      if (bet.home) add("team", bet.home, bet);
      if (bet.away) add("team", bet.away, bet);
      add("price_band", priceBand(bet.price), bet); add("month", Number(bet.day.slice(5, 7)), bet);
    }
    return Object.values(groups).map((group) => ({ dimension: group.dimension, value: group.value, ...summarize(group.bets, options) }));
  }
  export { decodeSeason, normalizeStrategy, runBacktest, encodeStrategy, decodeStrategy };
