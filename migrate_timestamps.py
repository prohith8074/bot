from app.config.database import get_database
from pymongo import UpdateOne
from bson.objectid import ObjectId
import time

def fix_feedback_timestamps():
    db = get_database()
    print("running migration...")
    
    # Find docs missing createdAt
    missing = list(db.feedback.find({"createdAt": {"$exists": False}}))
    print(f"Found {len(missing)} documents missing createdAt")
    
    ops = []
    for doc in missing:
        # Use updatedAt if available, else derive from _id (best approximation)
        new_date = doc.get("updatedAt")
        if not new_date:
            new_date = doc["_id"].generation_time
            # Adjust for timezone if needed, but generation_time is UTC. 
            # Ideally we want IST but consistent ordering is key.
        
        ops.append(UpdateOne(
            {"_id": doc["_id"]},
            {"$set": {"createdAt": new_date}}
        ))
    
    if ops:
        res = db.feedback.bulk_write(ops)
        print(f"Matched: {res.matched_count}, Modified: {res.modified_count}")
    else:
        print("No updates needed")

if __name__ == "__main__":
    fix_feedback_timestamps()
