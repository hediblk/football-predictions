# Floodlight forecasts

Floodlight estimates match and season outcomes and compares club strength across European football. These terms describe the football quantities already used by the project.

## Language

**Match forecast**:
Probabilities for a fixture's home win, draw, and away win, together with estimates for goals and scorelines.
_Avoid_: Prediction when a single picked result is meant.

**Season forecast**:
Probabilities for final league positions or tournament stages and the winner, conditional on the available information and fitted team strengths.
_Avoid_: Official final table, guaranteed finish.

**Forecast origin**:
The point in time at which a forecast is made or reconstructed, determining which information can be considered available.
_Avoid_: Results cutoff when the forecast's reference time is meant.

**Results cutoff**:
The latest match kickoff represented among a forecast's included completed results. It can precede the forecast origin.
_Avoid_: Forecast origin, refresh time.

**Club strength rating**:
The expected percentage of available points a club would take against an average European top-flight club on a neutral pitch. It is distinct from the club's league points and its chance of winning a competition.
_Avoid_: Title probability, win probability.

**Forecast history point**:
A dated season forecast retained to show how chances change through the season. A refresh without new results can revise the latest point rather than add another one.

**Weekly ranking snapshot**:
Club strength ratings frozen after the weekend round, normally on Monday, used as a baseline for movement in the current ranking. The current ranking uses live ratings rather than the frozen ratings.
_Avoid_: Current ranking when the movement baseline is meant.

**Retained forecast**:
The last successfully published forecast kept when a competition's refresh fails. Its original forecast time remains meaningful even when other competitions have newer forecasts.
_Avoid_: Fresh forecast, updated forecast.
