from app.config.database import get_database
import pprint

db = get_database()

print("One record sample:")
# Find one record to see structure
doc = db.feedback.find_one()
pprint.pprint(doc)

print("\nChecking for documents missing 'createdAt':")
missing_created_at = list(db.feedback.find({"createdAt": {"$exists": False}}))
print(f"Found {len(missing_created_at)} documents missing 'createdAt'")

if missing_created_at:
    print("Sample missing createdAt:")
    pprint.pprint(missing_created_at[0])

print("\nChecking for documents with 'createdAt':")
has_created_at = list(db.feedback.find({"createdAt": {"$exists": True}}).limit(2))
for d in has_created_at:
    print(f"ID: {d.get('_id')}, CreatedAt: {d.get('createdAt')}")
