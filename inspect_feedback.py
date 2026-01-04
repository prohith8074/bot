"""
Direct MongoDB Inspection Script
Run this to see the actual state of Feedback records
"""
import os
from pymongo import MongoClient
from dotenv import load_dotenv
import pprint

load_dotenv()

mongo_uri = os.getenv("Mongodb_Connection_String") or os.getenv("MONGODB_URI")
print(f"Connecting to MongoDB...")

client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
db = client["Star_Health_Whatsapp_bot"]

print("\n=== FEEDBACK COLLECTION SAMPLE ===")
# Get a few recent documents
docs = list(db.feedback.find().sort("_id", -1).limit(5))

for i, doc in enumerate(docs):
    print(f"\n--- Document {i+1} ---")
    print(f"  _id: {doc.get('_id')}")
    print(f"  _id timestamp: {doc.get('_id').generation_time if doc.get('_id') else 'N/A'}")
    print(f"  createdAt: {doc.get('createdAt', 'MISSING')}")
    print(f"  updatedAt: {doc.get('updatedAt', 'MISSING')}")
    print(f"  timestamp: {doc.get('timestamp', 'MISSING')}")
    print(f"  sessionId: {doc.get('sessionId', 'MISSING')}")
    print(f"  agentType: {doc.get('agentType', 'MISSING')}")
    print(f"  feedback: {doc.get('feedback', 'MISSING')}")

print("\n=== STATISTICS ===")
total = db.feedback.count_documents({})
with_created = db.feedback.count_documents({"createdAt": {"$exists": True}})
without_created = db.feedback.count_documents({"createdAt": {"$exists": False}})
print(f"Total documents: {total}")
print(f"With createdAt: {with_created}")
print(f"Without createdAt: {without_created}")

# Check date distribution
print("\n=== DATE DISTRIBUTION (from ObjectId) ===")
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from collections import defaultdict

date_counts = defaultdict(int)
for doc in db.feedback.find():
    try:
        ts = doc["_id"].generation_time
        date_str = ts.strftime("%Y-%m-%d")
        date_counts[date_str] += 1
    except:
        pass

for d in sorted(date_counts.keys()):
    print(f"  {d}: {date_counts[d]} records")
