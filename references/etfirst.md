# ETFirst Reference

## Required CLI

This skill expects an `etfirst` executable available on `PATH`.

The generator calls:

```powershell
etfirst --json index-base list-etf --type 2 --page-no 1 --page-size 100
```

It then paginates until all rows are fetched.

## Local Auth

Configure ETFirst locally using the user's own authorized key or account. Never put an ETFirst key in:

- `SKILL.md`;
- bundled scripts;
- Git commits;
- public GitHub repositories;
- generated HTML reports.

## Network Environment

When running behind a proxy, the generator sets:

```text
NO_PROXY=etfapp.euler.southernfund.com,121.35.255.74
no_proxy=etfapp.euler.southernfund.com,121.35.255.74
PYTHONIOENCODING=utf-8
```

## Expected Row Fields

The script reads these ETFirst ETF row fields when present:

- `prodCd`: product code;
- `prodName`: product short name;
- `managementCompany`: fund company;
- `clasName`: category;
- `ast`: ETF scale in 100 million CNY;
- `astChgRto`: daily scale change ratio;
- `netInflow`: net inflow in 100 million CNY;
- `traval`: turnover amount in CNY;
- `yield`: daily return;
- `yieldDate`: latest trading date in `YYYYMMDD`, used as the actual report date when present;
- `astDate` or `dataDate`: scale data date in `YYYYMMDD`, used when `yieldDate` is unavailable.

Missing numeric fields default to `0.0`; missing category defaults to `其他`; missing manager defaults to `未披露`.

These fields describe the actual dataset; they do not determine the request cutoff. For `今日`/`今天` reports, pass the previous calendar day with `--target-data-date` and reject any dataset newer than that cutoff. On non-trading target dates, use the latest completed trading day no later than the cutoff and label the report with that actual data date.
