# Architecture

## What this replaces

Two PowerShell runbooks, run by hand, that exported dataset, report and refresh facts to CSV files which people copied into a semantic model. It worked, but it depended on a person, produced no alerts, and the "is anything broken?" answer lived in someone's head.

## The automated flow

```
Scheduled pipeline (daily)
  1. Collect      notebook calls the Power BI REST API with a read-only service principal
  2. Assess       status rules -> DailyRefreshStatus.csv (fixed name) + dated copy -> Lakehouse
  3. Refresh      intermediate semantic model -> usage dashboard model (in that order)
  4. Notify       owner emails for stale datasets (from the pipeline) and a snapshot of the
                  Refresh Monitor page (native report subscription)
  On failure at any step: failure-notification email
```

### Decisions and why

| Decision | Reason |
|---|---|
| **Notebook in the same platform workspace** instead of hosting the runbooks in a separate automation service | One less service to own, runs next to the data, no extra hosting approvals |
| **Lakehouse as the source** for the semantic model instead of a file share | The notebook writes once; no copy/paste step, no file-name drift. The model reads a table or a fixed file name |
| **Fixed output file name** (`DailyRefreshStatus.csv`) plus a dated copy | The downstream model's source expects one name. The dated copy keeps history without breaking that contract |
| **Read-only service principal** with Member access on the monitored workspaces | The job only needs to read. Least privilege makes the approval and the audit conversation easy |
| **Owner emails from the pipeline** instead of a no-code alerting tool | The logic (monitored-only, grouped per owner, test mode) is easier to review and version in code |
| **Native report subscription** for the Refresh Monitor snapshot | A flow that exported the page to PDF failed on the table visual even though a manual export and a native subscription rendered it fine. The native route was reliable |
| **Refresh order: intermediate model, then usage model** | The usage model depends on the intermediate one; refreshing out of order shows yesterday's data |
| **Secrets in a vault, rotated** | A client secret in notebook code or a config file is the first thing an audit finds |

### Alert design

- **Only monitored datasets trigger owner emails.** "Monitored" means used by an active dashboard in the navigation hub or the usage model. Emailing every scanned dataset teaches people to ignore the emails.
- **One email per owner**, listing all of their datasets.
- **Test mode first.** Every email goes to one test recipient with a `[TEST - intended for ...]` subject prefix, so the whole flow runs against real data with no one else receiving anything. Live mode removes the prefix and adds extra recipients.
- **Grace period.** "Stale" means older than the threshold plus a few hours, so a daily refresh that drifts by minutes does not flap between healthy and stale.
- **Unscheduled datasets are never "stale".** There is nothing for them to be late for. They are reported separately, and a long-abandoned one becomes an archive candidate.
- **Unknown owners route to a governance mailbox** instead of being dropped.

### Archive review

Datasets with no refresh for six months or more are flagged as archive **candidates**. The pipeline does not archive anything. The process is: flag, confirm with the developer, then remove the app audiences. Archived items are excluded from usage metrics so adoption numbers are not diluted by dead content.

## Data modelling lessons

- **Join datasets by GUID, never by name.** Names repeat across workspaces, and dev/test copies silently multiply rows.
- **Datasets with no row-level security roles need explicit "No RLS" placeholder rows**, or they vanish from audit outputs.
- **Security-group members must be expanded** or user counts are undercounted.
- **Pre-format dates before exporting CSV.** The default follows the machine's regional settings.
- **Tokens expire (about an hour).** Check expiry before long loops.
- **Thin reports that share a semantic model are not separate content.** Count the model once.
- **Per-audience app membership has no supported admin API path.** Plan adoption metrics around what the APIs actually return.

## What is not in this repo

The real pipeline's workspace names, tenant setup, the audit queries against real RLS roles, report pages and email templates. This repo contains the rules as tested code on a synthetic tenant, and the design reasoning.
