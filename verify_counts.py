
import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

async def verify_counts():
    uri = os.getenv("MONGODB_URL")
    client = AsyncIOMotorClient(uri)
    db = client.get_database("Star_Health_Whatsapp_bot")
    
    # 1. Total Conversations (Unique Session IDs)
    total_sessions = await db.feedback.distinct("sessionId")
    print(f"Total Unique Sessions (UI 'Total Conversations'): {len(total_sessions)}")
    
    # 2. Completed Conversations (Unique Sessions with feedback NOT pending/incomplete)
    # AND conversationStatus != 'incomplete'
    completed_pipeline = [
        {"$match": {
            "feedback": {"$nin": ["Pending", "incomplete", "no feedback", "No feedback", "no", "No"]},
            "$or": [{"conversationStatus": {"$exists": False}}, {"conversationStatus": {"$ne": "incomplete"}}]
        }},
        {"$group": {"_id": "$sessionId"}},
        {"$count": "count"}
    ]
    completed_res = await db.feedback.aggregate(completed_pipeline).to_list(None)
    completed_count = completed_res[0]['count'] if completed_res else 0
    print(f"Completed Conversations: {completed_count}")

    # 3. Incomplete Conversations
    # Logic: Unique sessions where (status is incomplete OR feedback is pending/incomplete)
    incomplete_ids = await db.feedback.distinct("sessionId", {
        "$or": [
            {"conversationStatus": "incomplete"},
            {"feedback": "incomplete"},
            {"feedback": "Pending"}
        ]
    })
    print(f"Incomplete Conversations: {len(incomplete_ids)}")
    
    # 4. Feedback Count (Total feedback received - similar to completed usually, but let's check exact logic)
    # The dashboard service uses count_documents for feedback where feedback != Pending.
    # But wait, my fix changed it to distinct session IDs for feedback? 
    # Let's check the code I viewed earlier. 
    # Oops, I should double check logic. 
    # Logic from dashboard.py or service... I recall fixing 'fetch_feedback' to use distinct.
    
    feedback_ids = await db.feedback.distinct("sessionId", {
        "feedback": {"$nin": ["Pending", "incomplete", "no feedback"]}
    })
    print(f"Total Feedback Received (Unique): {len(feedback_ids)}")

    # 5. Check the specific duplicate session provided by user: 020d62aa-4652-41f2-b8fd-bae2d38c8e57
    dup_cursor = db.feedback.find({"sessionId": "020d62aa-4652-41f2-b8fd-bae2d38c8e57"})
    dup_docs = await dup_cursor.to_list(None)
    print(f"\nChecking specific session '020d...': Found {len(dup_docs)} documents.")
    print("Dashboard should count this as 1 conversation.")

if __name__ == "__main__":
    asyncio.run(verify_counts())
