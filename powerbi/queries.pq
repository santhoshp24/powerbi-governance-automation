// Paste each block into Power BI Desktop: Home > Transform data > New Source > Blank Query > Advanced Editor.
// Set the one parameter first: Manage parameters > New > Name: DataFolder, Type: Text,
// Current value: the full path to output/powerbi (for example C:\govmon\output\powerbi).
// Untested in Power BI Desktop from this repo; the CSV schema they read is covered by unit tests.

// ---------- dim_dataset ----------
let
    Source = Csv.Document(File.Contents(DataFolder & "\dim_dataset.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"dataset_id", type text}, {"name", type text}, {"workspace", type text}, {"owner_email", type text},
        {"scheduled", type logical}, {"monitored", type logical}, {"archive_candidate", type logical},
        {"state", type text}, {"days_since_refresh", type number}}, "en-US"),
    WithRefresh = Table.TransformColumnTypes(Typed, {{"last_refresh_utc", type datetime}}, "en-US")
in
    WithRefresh

// ---------- fact_daily_status ----------
let
    Source = Csv.Document(File.Contents(DataFolder & "\fact_daily_status.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"date", type date}, {"dataset_id", type text}, {"state", type text}, {"days_since_refresh", type number}}, "en-US")
in
    Typed

// ---------- fact_refresh_attempt ----------
let
    Source = Csv.Document(File.Contents(DataFolder & "\fact_refresh_attempt.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"dataset_id", type text}, {"date", type date}, {"start_utc", type datetime}, {"end_utc", type datetime},
        {"duration_min", type number}, {"status", type text}}, "en-US")
in
    Typed

// ---------- dim_date ----------
let
    Source = Csv.Document(File.Contents(DataFolder & "\dim_date.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"date", type date}, {"year", Int64.Type}, {"month", Int64.Type}, {"month_name", type text},
        {"day_of_week", type text}, {"is_latest", type logical}}, "en-US")
in
    Typed
