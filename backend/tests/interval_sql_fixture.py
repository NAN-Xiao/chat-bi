"""Interval pairs expose the event row that owns their starting date."""


def interval_sql(mode="adjacent", *, wrong_date=False):
    if mode == "different":
        pairs = """starts AS (SELECT * FROM events WHERE action='open'),
ends AS (SELECT * FROM events WHERE action='close'),
ranked_pairs AS (
    SELECT s.entity_id, s.event_day AS start_date, e.event_day AS end_date,
           s.occurred_at AS start_time, e.occurred_at AS end_time,
           ROW_NUMBER() OVER (PARTITION BY e.entity_id,e.event_id ORDER BY s.occurred_at DESC) AS pair_rank
    FROM ends e JOIN starts s ON s.entity_id=e.entity_id AND s.occurred_at<=e.occurred_at
), paired AS (
    SELECT entity_id, {date} AS interval_date, start_time,end_time FROM ranked_pairs WHERE pair_rank=1
)""".format(date="end_date" if wrong_date else "start_date")
    elif mode in {"lag", "lead"}:
        window = "OVER (PARTITION BY entity_id ORDER BY occurred_at,event_id)"
        if mode == "lag":
            start, end = f"LAG(occurred_at) {window}", "occurred_at"
            date = "event_day" if wrong_date else f"LAG(event_day) {window}"
        else:
            start, end = "occurred_at", f"LEAD(occurred_at) {window}"
            date = f"LEAD(event_day) {window}" if wrong_date else "event_day"
        pairs = f"paired AS (SELECT entity_id,{date} AS interval_date,{start} AS start_time,{end} AS end_time FROM events)"
    else:
        pairs = """ordered_events AS (
    SELECT *, ROW_NUMBER() OVER(PARTITION BY entity_id ORDER BY occurred_at,event_id) AS position FROM events
), paired AS (
    SELECT curr.entity_id,{date}.event_day AS interval_date,prev.occurred_at AS start_time,curr.occurred_at AS end_time
    FROM ordered_events curr JOIN ordered_events prev ON curr.entity_id=prev.entity_id AND curr.position=prev.position+1
)""".format(date="curr" if wrong_date else "prev")
    return f"""WITH {pairs}, valid_intervals AS (
    SELECT entity_id,interval_date,end_time-start_time AS interval_seconds FROM paired
    WHERE end_time>=start_time AND end_time-start_time<=3600
)
SELECT interval_date,COUNT(DISTINCT entity_id) AS entity_count,COUNT(*) AS interval_count,
       MAX(interval_seconds) AS max_interval_seconds,MIN(interval_seconds) AS min_interval_seconds,
       AVG(interval_seconds) AS avg_interval_seconds,
       APPROX_PERCENTILE(interval_seconds,0.75) AS p75_interval_seconds,
       APPROX_PERCENTILE(interval_seconds,0.5) AS median_interval_seconds,
       APPROX_PERCENTILE(interval_seconds,0.25) AS p25_interval_seconds
FROM valid_intervals GROUP BY interval_date"""
