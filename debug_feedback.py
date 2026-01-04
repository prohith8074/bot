from app.config.database import get_database
from datetime import datetime, timedelta
import pprint

db = get_database()

# Get today's range
now = datetime.utcnow() + timedelta(hours=5, minutes=30)
start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

print(f"Querying from {start_of_day} to {now}")

pipeline = [
    {"$match": {
        "createdAt": {"$gte": start_of_day},
        "feedback": {"$nin": ["incomplete", "Pending", "no feedback", "No feedback", "no", "No"]},
         "$or": [{"conversationStatus": {"$exists": False}}, {"conversationStatus": {"$ne": "incomplete"}}]
    }},
    {"$project": {
        "sessionId": 1,
        "agentType": 1,
        "feedback": 1,
        "createdAt": 1,
        "conversationStatus": 1
    }}
]

results = list(db.feedback.aggregate(pipeline))
print(f"Found {len(results)} records matching criteria")
for r in results:
    pprint.pprint(r)

# Check distinct sessions
distinct_sessions = set(r.get('sessionId') for r in results)
print(f"Distinct Sessions: {len(distinct_sessions)}")
