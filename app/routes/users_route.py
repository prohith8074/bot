"""
Users routes - handles the 'agents' collection in MongoDB
This is for managing agents/users, not authentication users (login_details)
"""
from fastapi import APIRouter, HTTPException
from app.config.database import get_database
from app.config.logging_config import get_logger
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from bson import ObjectId

router = APIRouter()
logger = get_logger(__name__)

# Request/Response models that match frontend expectations
class AgentCreateRequest(BaseModel):
    agent_name: str
    agent_code: str
    role: str
    phone_number: str
    email: str

class AgentUpdateRequest(BaseModel):
    agent_name: str
    agent_code: str
    role: str
    phone_number: str
    email: str

def clean_phone_number(phone: str) -> str:
    """
    Clean and format phone number to +91XXXXXXXXXX format.
    
    Examples:
    - "9874563210" -> "+919874563210"
    - "+91 98745 63210" -> "+919874563210"
    - "++91 98745 63210" -> "+919874563210"
    - "+919874563210" -> "+919874563210"
    - "8569742135" -> "+918569742135"
    """
    if not phone:
        return ""
    
    # Remove all non-digit characters
    digits_only = "".join(c for c in phone if c.isdigit())
    
    # If empty after cleaning, return empty
    if not digits_only:
        return ""
    
    # Remove leading 91 if present (we'll add it back with +)
    if digits_only.startswith("91") and len(digits_only) > 10:
        digits_only = digits_only[2:]
    
    # Now we should have 10 digits for Indian mobile
    # Add +91 prefix
    return "+91" + digits_only

def get_agents_collection(db):
    """Helper function to get the agents collection"""
    collection_names = db.list_collection_names()
    if "agents" in collection_names:
        logger.info("📖 Using 'agents' collection")
        return db.agents
    elif "users" in collection_names:
        logger.info("📖 Using 'users' collection (fallback)")
        return db.users
    else:
        # Default to 'agents' as that's where the seed script puts data
        logger.info("📖 Using default 'agents' collection")
        return db.agents

@router.get("")
def get_users():
    """Get all agents from the agents collection"""
    logger.info("📖 Fetching agents list")
    try:
        db = get_database()
        agents_collection = get_agents_collection(db)
        
        agent_docs = agents_collection.find().sort("createdAt", -1)
        users = []
        for doc in agent_docs:
            # Convert ObjectId to string and ensure all fields are present
            user_data = {
                "_id": str(doc["_id"]),
                "agent_name": doc.get("agent_name", ""),
                "agent_code": doc.get("agent_code", ""),
                "role": doc.get("role", ""),
                "phone_number": doc.get("phone_number", ""),
                "email": doc.get("email", ""),
                "createdAt": doc.get("createdAt"),
                "updatedAt": doc.get("updatedAt"),
            }
            users.append(user_data)
        logger.info(f"✅ Retrieved {len(users)} agents from 'agents' collection")
        # Return in the format expected by frontend
        return {"users": users}
    except Exception as error:
        logger.error(f"❌ Error fetching agents: {error}")
        raise HTTPException(status_code=500, detail="Failed to fetch agents")

@router.post("", status_code=201)
def create_user(user: AgentCreateRequest):
    """Create a new agent"""
    logger.info(f"➕ Creating agent: {user.agent_code}")
    try:
        db = get_database()
        agents_collection = get_agents_collection(db)
        
        # Validate all fields are provided
        if not user.agent_name or not user.agent_name.strip():
            raise HTTPException(status_code=400, detail="Agent Name is required")
        if not user.agent_code or not user.agent_code.strip():
            raise HTTPException(status_code=400, detail="Agent Code is required")
        if not user.role or not user.role.strip():
            raise HTTPException(status_code=400, detail="Role is required")
        if not user.phone_number or not user.phone_number.strip():
            raise HTTPException(status_code=400, detail="Phone Number is required")
        if not user.email or not user.email.strip():
            raise HTTPException(status_code=400, detail="Email is required")
        
        # Clean phone number
        cleaned_phone = clean_phone_number(user.phone_number)
        if len(cleaned_phone) < 8: # Basic length check
             raise HTTPException(status_code=400, detail="Invalid phone number format")

        # Check if agent_code already exists
        existing_code = agents_collection.find_one({"agent_code": user.agent_code})
        if existing_code:
            logger.warning(f"⚠️ Agent code {user.agent_code} already exists")
            raise HTTPException(status_code=400, detail=f"Agent code {user.agent_code} already exists")
        
        # Check if phone_number already exists
        existing_phone = agents_collection.find_one({"phone_number": cleaned_phone})
        if existing_phone:
            logger.warning(f"⚠️ Phone number {cleaned_phone} already exists")
            raise HTTPException(status_code=400, detail=f"Phone number {cleaned_phone} already exists")
        
        # Check if email already exists
        existing_email = agents_collection.find_one({"email": user.email.lower()})
        if existing_email:
            logger.warning(f"⚠️ Email {user.email} already exists")
            raise HTTPException(status_code=400, detail=f"Email {user.email} already exists")
        
        # Create agent document matching MongoDB agents collection structure
        agent_doc = {
            "agent_name": user.agent_name.strip(),
            "agent_code": user.agent_code.strip(),
            "role": user.role.strip(),
            "phone_number": cleaned_phone,
            "email": user.email.lower().strip(),
            "createdAt": datetime.now(),
            "updatedAt": datetime.now()
        }
        result = agents_collection.insert_one(agent_doc)
        agent_doc["_id"] = str(result.inserted_id)
        
        # Also create login_details entry so agent appears in Admin Access section
        try:
            from app.routes.auth import hash_password
            login_collection = db.login_details
            existing_login = login_collection.find_one({"email": user.email.lower().strip()})
            if not existing_login:
                login_doc = {
                    "email": user.email.lower().strip(),
                    "password": hash_password("Password@123"),
                    "firstName": user.agent_name.strip().split()[0] if user.agent_name.strip() else "",
                    "lastName": " ".join(user.agent_name.strip().split()[1:]) if len(user.agent_name.strip().split()) > 1 else "",
                    "phone": cleaned_phone,
                    "bio": "",
                    "isAdmin": False,
                    "isActive": True,
                    "twoFactorEnabled": False,
                    "createdAt": datetime.now(),
                    "updatedAt": datetime.now()
                }
                login_collection.insert_one(login_doc)
                logger.info(f"✅ Login account created for agent: {user.email}")
        except Exception as login_error:
            logger.warning(f"⚠️ Failed to create login account for agent {user.email}: {login_error}")
        
        logger.info(f"✅ Agent created: {user.agent_code} ({result.inserted_id})")
        return {"user": agent_doc}
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"❌ Error creating agent: {error}")
        raise HTTPException(status_code=500, detail="Failed to create agent")

@router.put("/{user_id}")
def update_user(user_id: str, user: AgentUpdateRequest):
    """Update an agent"""
    logger.info(f"✏️ Updating agent: {user_id}")
    try:
        db = get_database()
        agents_collection = get_agents_collection(db)
        
        # Validate ObjectId
        try:
            object_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid agent ID")
        
        # Check if agent exists
        existing = agents_collection.find_one({"_id": object_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Validate all fields are provided
        if not user.agent_name or not user.agent_name.strip():
            raise HTTPException(status_code=400, detail="Agent Name is required")
        if not user.agent_code or not user.agent_code.strip():
            raise HTTPException(status_code=400, detail="Agent Code is required")
        if not user.role or not user.role.strip():
            raise HTTPException(status_code=400, detail="Role is required")
        if not user.phone_number or not user.phone_number.strip():
            raise HTTPException(status_code=400, detail="Phone Number is required")
        if not user.email or not user.email.strip():
            raise HTTPException(status_code=400, detail="Email is required")
            
        # Clean phone number
        cleaned_phone = clean_phone_number(user.phone_number)
        if len(cleaned_phone) < 8:
             raise HTTPException(status_code=400, detail="Invalid phone number format")
        
        # Check if new agent_code conflicts with existing (excluding current agent)
        if user.agent_code.strip() != existing.get("agent_code", ""):
            conflict_code = agents_collection.find_one({"agent_code": user.agent_code.strip()})
            if conflict_code and str(conflict_code["_id"]) != user_id:
                raise HTTPException(status_code=400, detail=f"Agent code {user.agent_code} already exists")
        
        # Check if new phone_number conflicts with existing (excluding current agent)
        if cleaned_phone != existing.get("phone_number", ""):
            conflict_phone = agents_collection.find_one({"phone_number": cleaned_phone})
            if conflict_phone and str(conflict_phone["_id"]) != user_id:
                raise HTTPException(status_code=400, detail=f"Phone number {cleaned_phone} already exists")
        
        # Check if new email conflicts with existing (excluding current agent)
        if user.email.lower().strip() != existing.get("email", "").lower():
            conflict_email = agents_collection.find_one({"email": user.email.lower().strip()})
            if conflict_email and str(conflict_email["_id"]) != user_id:
                raise HTTPException(status_code=400, detail=f"Email {user.email} already exists")
        
        # Build update document
        update_data = {
            "agent_name": user.agent_name.strip(),
            "agent_code": user.agent_code.strip(),
            "role": user.role.strip(),
            "phone_number": cleaned_phone,
            "email": user.email.lower().strip(),
            "updatedAt": datetime.now()
        }
        
        # Update the agent
        result = agents_collection.update_one(
            {"_id": object_id},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            logger.warning(f"⚠️ No changes made to agent {user_id}")
        
        # Fetch updated agent
        updated_agent = agents_collection.find_one({"_id": object_id})
        updated_agent["_id"] = str(updated_agent["_id"])
        
        logger.info(f"✅ Agent updated: {user_id}")
        return {"user": updated_agent}
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"❌ Error updating agent: {error}")
        raise HTTPException(status_code=500, detail="Failed to update agent")

@router.delete("/{user_id}")
def delete_user(user_id: str):
    """Delete an agent"""
    logger.info(f"🗑️ Deleting agent: {user_id}")
    try:
        db = get_database()
        agents_collection = get_agents_collection(db)
        
        # Validate ObjectId
        try:
            object_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid agent ID")
        
        # Check if agent exists
        existing = agents_collection.find_one({"_id": object_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Delete the agent
        agent_email = existing.get("email")
        result = agents_collection.delete_one({"_id": object_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # 🗑️ Cascading Delete: Also remove from login_details
        if agent_email:
            try:
                login_collection = db.login_details
                login_del_result = login_collection.delete_one({"email": agent_email.lower().strip()})
                if login_del_result.deleted_count > 0:
                    logger.info(f"✅ Associated login account deleted for: {agent_email}")
            except Exception as login_del_error:
                logger.warning(f"⚠️ Failed to delete associated login account: {login_del_error}")
        
        logger.info(f"✅ Agent deleted: {user_id}")
        return {"message": "Agent deleted successfully"}
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"❌ Error deleting agent: {error}")
        raise HTTPException(status_code=500, detail="Failed to delete agent")




