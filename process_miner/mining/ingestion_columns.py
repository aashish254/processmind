"""Column-name registry shared by the ingestion agent and the log miner.

Covers common header spellings from SAP / ServiceNow / Jira / Camunda exports.
"""

CASE_ID_COLUMNS = {"case_id", "case", "case id", "caseid", "case:id", "case:concept:name"}
ACTIVITY_COLUMNS = {"activity", "concept:name", "activity name", "task", "event", "activity_name"}
TIMESTAMP_COLUMNS = {"timestamp", "time", "complete time", "end time", "start time", "time:timestamp"}
RESOURCE_COLUMNS = {"resource", "user", "org:resource", "resource id", "agent", "assigned"}
LIFECYCLE_COLUMNS = {"lifecycle", "concept:instance", "event type", "status", "activity status"}

LOG_COLUMNS = {
    "case_id": CASE_ID_COLUMNS,
    "activity": ACTIVITY_COLUMNS,
    "timestamp": TIMESTAMP_COLUMNS,
    "resource": RESOURCE_COLUMNS,
    "lifecycle": LIFECYCLE_COLUMNS,
}
