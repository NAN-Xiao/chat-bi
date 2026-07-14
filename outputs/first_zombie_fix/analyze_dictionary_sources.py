import json
import os
from collections import Counter, defaultdict

import pymysql


INPUT = r"D:\AIWork3\chat-bi\outputs\first_zombie_fix\dictionary_rows.json"
OUTPUT = r"D:\AIWork3\chat-bi\outputs\first_zombie_fix\source_analysis.json"


def parse_json(value):
    if not value:
        return {}
    try:
        result = json.loads(value)
    except Exception:
        return {}
    return result if isinstance(result, dict) else {}


rows = json.load(open(INPUT, encoding="utf-8"))
current_event = None
entries = []
for excel_row, row in enumerate(rows[1:], start=2):
    if row[0]:
        current_event = str(row[0]).strip()
    if current_event and row[5]:
        entries.append({
            "excel_row": excel_row,
            "event": current_event,
            "source": str(row[4]).strip() if row[4] else "",
            "property": str(row[5]).strip(),
        })

by_event = defaultdict(list)
for entry in entries:
    by_event[entry["event"]].append(entry)

conn = pymysql.connect(
    host="amv-rj99b7u1o5867h94800000033o.ads.aliyuncs.com",
    port=3306,
    user="dongjinchao",
    password=os.environ["FIRST_ZOMBIE_DB_PASSWORD"],
    database="first_zombie",
    charset="utf8mb4",
    connect_timeout=10,
    read_timeout=45,
    cursorclass=pymysql.cursors.DictCursor,
)

analysis = []
for index, (event, event_entries) in enumerate(sorted(by_event.items()), start=1):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT dt, personal, ext
            FROM `event`
            WHERE dt BETWEEN 20260707 AND 20260713
              AND event = %s
            LIMIT 100
            """,
            (event,),
        )
        sampled_rows = list(cursor.fetchall())

    states = Counter()
    observed_sources = set()
    for row in sampled_rows:
        personal = parse_json(row.get("personal"))
        ext = parse_json(row.get("ext"))
        if personal and not ext:
            states["personal"] += 1
            observed_sources.add("personal")
        elif ext and not personal:
            states["ext"] += 1
            observed_sources.add("ext")
        elif personal and ext:
            states["both"] += 1
            observed_sources.add("both")
        else:
            states["neither"] += 1

    dictionary_sources = sorted({entry["source"] for entry in event_entries if entry["source"]})
    if observed_sources == {"personal"}:
        expected_source = "personal"
    elif observed_sources == {"ext"}:
        expected_source = "ext"
    elif not observed_sources:
        expected_source = None
    else:
        expected_source = "conflict"

    wrong_rows = []
    if expected_source in {"personal", "ext"}:
        wrong_rows = [
            entry["excel_row"]
            for entry in event_entries
            if entry["source"] and entry["source"] != expected_source
        ]

    analysis.append({
        "event": event,
        "dictionary_rows": len(event_entries),
        "dictionary_sources": dictionary_sources,
        "sample_rows": len(sampled_rows),
        "sample_states": dict(states),
        "observed_sources": sorted(observed_sources),
        "expected_source": expected_source,
        "wrong_rows": wrong_rows,
    })
    print(f"{index}/{len(by_event)}\t{event}\tsample={len(sampled_rows)}\tstates={dict(states)}\texpected={expected_source}", flush=True)

conn.close()
json.dump(analysis, open(OUTPUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

fixed_candidates = [item for item in analysis if item["wrong_rows"]]
print("SUMMARY")
print("EVENTS", len(analysis))
print("WITH_SAMPLE", sum(1 for item in analysis if item["sample_rows"]))
print("PERSONAL_ONLY", sum(1 for item in analysis if item["expected_source"] == "personal"))
print("EXT_ONLY", sum(1 for item in analysis if item["expected_source"] == "ext"))
print("CONFLICT", sum(1 for item in analysis if item["expected_source"] == "conflict"))
print("NO_EVIDENCE", sum(1 for item in analysis if item["expected_source"] is None))
print("WRONG_EVENTS", len(fixed_candidates))
print("WRONG_ROWS", sum(len(item["wrong_rows"]) for item in fixed_candidates))
for item in fixed_candidates:
    print(f"FIX_CANDIDATE\t{item['event']}\trows={item['wrong_rows']}\texpected={item['expected_source']}")
