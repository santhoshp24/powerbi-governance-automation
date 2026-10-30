# Power BI report kit

The Python monitor writes four CSVs. This folder holds everything needed to turn them into a
report in Power BI Desktop. **No `.pbix` is shipped:** it is a binary only Desktop can write, and
this kit was not opened in Desktop from this repo, so treat the M and DAX as untested until you
have checked them against the numbers below.

## 1. Generate the data

```bash
python run.py                       # synthetic tenant -> output/powerbi/*.csv
```

| Table | Grain | Rows (demo) |
|---|---|---|
| `dim_dataset` | one per dataset, current state | 40 |
| `fact_daily_status` | dataset x day, state the rules gave that morning | 1,200 (40 x 30) |
| `fact_refresh_attempt` | one per refresh attempt, 45-day window | 1,339 |
| `dim_date` | one per day in the window | 30 |

Daily states come from the same `status.classify` rules used for the live status, evaluated as of
each past day using only the attempts that had happened by then. A test asserts the latest day
equals the live status.

### Real tenant (REST path)

```bash
export POWERBI_TOKEN=...            # a token for a read-only service principal
python run.py --client rest --monitored my_monitored.csv
```

This writes the same four files to `output_real/powerbi/` (git-ignored). The REST client is a
**sketch, untested against a tenant**. History comes from `GET .../datasets/{id}/refreshes`, which
returns only recent attempts, so a real export starts with a short trend and grows as you run it
daily and keep the files. Keep real output out of any public repo.

## 2. Build the model

1. Set a text parameter `DataFolder` to the full path of `output/powerbi`.
2. Create the four queries from `queries.pq`.
3. Create the relationships and measures from `measures.dax` (header comment lists the four relationships).
4. View > Themes > Browse for themes > `theme.json`.

## 3. Pages

**Refresh Monitor**
- Cards: Datasets, Healthy, Stale, Failed, Never Refreshed, Health Rate, Archive Candidates
- Stacked column by `dim_date[date]`, legend `fact_daily_status[state]`, count of datasets (30-day trend)
- Table of `dim_dataset`: name, workspace, owner, state (background colour = `State Colour`), days since refresh. Visual filter: state is not Healthy
- Slicers: workspace, owner, state

**Refresh History**
- Line: Attempt Failure Rate by date
- Column: Avg Refresh Minutes by workspace
- Table of the slowest datasets by average duration

**Archive Candidates**
- Table of `dim_dataset` where `archive_candidate` is true, with owner and last refresh

## 4. Numbers to check against (demo, 2026-10-30)

| Measure | Expected |
|---|---|
| Datasets | 40 |
| Healthy / Stale / Failed / Never refreshed / Not scheduled | 22 / 8 / 3 / 1 / 6 |
| Health Rate | 64.7% (22 / 34) |
| Archive Candidates | 5 |
| Attempts / Failed Attempts | 1,339 / 44 |
| Attempt Failure Rate | 3.3% |
| Avg Refresh Minutes | 13.4 |

If a card disagrees, the model is wrong, not the monitor.

## Notes

- The demo trend is flat at about 3 stale until the last two days, then jumps to 8 stale and 3
  failed: a synthetic "something broke this week" story, not real behaviour.
- Screenshots of your own built report are what make this repo convincing. Add them to
  `docs/` after you build it, from the synthetic data only.
