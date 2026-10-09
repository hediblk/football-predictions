## Footbal standings prediction
I tried implementeting a football standings prediction pipeline, which consists in using current table standings and already played matches to simulate the rest of the season and get probabilities of final positions for each team.

![Prediction output](pred.jpg)

### Pipeline:
Current pipeline uses a [Dixon-Coles model](https://urazakgul.github.io/datafc-blog/posts/en/post3/better-predictions-for-football-matches-how-does-the-dixon-coles-model-work.html) to predict match outcome probabilities along with elo ratings, then simulates the rest of the season with those probabilities using Monte Carlo. Model inputs are data from already played matches (score, goals) and optionally bookmaker odds for upcoming games (still trying to get better odds datasets for free).

I mainly focused on the La Liga's current season but the code is easily adaptable to other leagues as long as the same type of data is available.


You can either run the whole pipeline using CLI, or run the Jupyter notebook to see the step-by-step process and final table output.

### Next steps:
- Add more features to the model (xG, some sort of mulitplier for injuries/suspensions)
- Support cups like UCL, where there is a league phase then a knockout phase which requires a different simulation system