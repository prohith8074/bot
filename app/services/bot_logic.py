import re
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from app.config.logging_config import get_logger
from datetime import datetime

load_dotenv()

logger = get_logger(__name__)

class BotLogic:
    """Deterministic bot logic - NO LLM, static responses"""
    
    def __init__(self):
        # 🔒 ENTERPRISE: Use centralized database connection
        from app.config.database import get_database, is_mongodb_ready
        
        if not is_mongodb_ready():
            logger.warning("⚠️ MongoDB not ready during BotLogic init - will retry on first request")
            self.db = None
            self.available = False
        else:
            try:
                self.db = get_database()
                self.available = True
                logger.info("✅ BotLogic connected to shared MongoDB")
            except Exception as e:
                logger.error(f"❌ BotLogic DB connection failed: {e}")
                self.db = None
                self.available = False

        if self.available and self.db is not None:
            self.agents = self.db.agents
            self.users = self.db.users
            self.prompts = self.db["Prompts"]
            
            # Log available collections for debugging
            try:
                collections = self.db.list_collection_names()
                logger.debug(f"📚 BotLogic collections: {collections}")
            except: pass
        else:
            self.agents = None
            self.users = None
            self.prompts = None
            
        logger.info("BotLogic initialized")
        
    def _get_onboarding_messages(self) -> dict:
        """Load configurable onboarding messages"""
        defaults = {
            "greetingMessage": "Hi 👋 Please enter your Agent Code.",
            "menuMessage": "Welcome {agent_name}! Please select an option:\n1. Product Recommendation\n2. Sales Pitch",
            "invalidCodeMessage": "❌ Invalid agent code. Please try again with a valid code.",
            "authFailedMessage": "❌ Authentication failed. The phone number associated with this agent code doesn't match your number. Please try again with a valid agent code.",
            "invalidOptionMessage": "Please select option 1 (Product Recommendation) or option 2 (Sales Pitch).",
        }
        
        if not self.available or self.prompts is None:
            return defaults
            
        try:
            cfg = self.prompts.find_one({"agentType": "onboarding"})
            if cfg:
                for key, value in defaults.items():
                    defaults[key] = cfg.get(key, value)
        except Exception:
            pass
            
        return defaults

    async def process_message(self, message: str, session_id: str, current_state: dict, phone_number: str = None):
        # ... validation ...
        # (keeping existing structure, just ensuring self.available check is robust)
        pass 

    # Note: Logic inside process_message for agent lookup needs to be updated in the separate replacement chunk or I need to copy the whole function. 
    # I will do partial replace of __init__ first, then the specific lookup logic.
    
    # Wait, the tool instruction said "Remove local MongoClient init... Optimize search loop". 
    # I should do this in targeted chunks if possible, or one big chunk if they overlap.
    # Lines 12-88 cover __init__.
    # Lines 188-210 cover the lookup.
    
    # I will start with __init__.
    pass
    
    def _get_onboarding_messages(self) -> dict:
        """
        Load configurable onboarding / authentication messages from the
        Prompts collection (agentType='onboarding'), with sensible defaults.
        """
        defaults = {
            "greetingMessage": "Hi 👋 Please enter your Agent Code.",
            "menuMessage": "Welcome {agent_name}! Please select an option:\n1. Product Recommendation\n2. Sales Pitch",
            "invalidCodeMessage": "❌ Invalid agent code. Please try again with a valid code.",
            "authFailedMessage": "❌ Authentication failed. The phone number associated with this agent code doesn't match your number. Please try again with a valid agent code.",
            "invalidOptionMessage": "Please select option 1 (Product Recommendation) or option 2 (Sales Pitch).",
        }
        
        # Cache check
        current_time = datetime.now().timestamp()
        if hasattr(self, "_onboarding_cache") and self._onboarding_cache:
            cache_age = current_time - self._onboarding_cache_time
            if cache_age < 300:  # 5 minutes TTL
                return self._onboarding_cache.copy()
        
        # If DB or prompts collection is not available, use defaults
        if not getattr(self, "available", False) or getattr(self, "prompts", None) is None:
            return defaults
        
        try:
            cfg = self.prompts.find_one({"agentType": "onboarding"})
        except Exception as e:
            logger.warning(f"⚠️ Could not load onboarding messages from Prompts: {e}")
            cfg = None
        
        if not cfg:
            return defaults
        
        merged = {}
        for key, value in defaults.items():
            merged[key] = cfg.get(key, value)
            
        # Update cache
        self._onboarding_cache = merged
        self._onboarding_cache_time = current_time
        
        return merged
    
    
    def _ensure_connection(self):
        """Lazy reconnection if initial connection failed"""
        if self.available:
            return True
        
        # Try to reconnect
        try:
            from app.config.database import get_database, is_mongodb_ready
            if is_mongodb_ready():
                self.db = get_database()
                self.agents = self.db.agents
                self.users = self.db.users
                self.prompts = self.db["Prompts"]
                self.available = True
                logger.info("✅ BotLogic re-connected to MongoDB")
                return True
        except Exception:
            pass
        return False

    async def process_message(self, message: str, session_id: str, current_state: dict, phone_number: str = None):
        """
        Process message through deterministic state machine
        
        States:
        - greeting: Initial state, waiting for agent code
        - code_entered: Agent code validated, waiting for option selection
        - agent_active: Lyzr agent is handling conversation
        
        Args:
            message: User message text
            session_id: Session identifier
            current_state: Current conversation state
            phone_number: User's phone number (for validation)
        """
        self._ensure_connection()
        
        logger.debug(f"🔄 Bot Logic - Processing message")
        logger.debug(f"   Session: {session_id}")
        logger.debug(f"   Message: {message}")
        logger.debug(f"   Phone Number: {phone_number}")
        logger.debug(f"   Current State: {current_state}")
        
        state = current_state.get("state", "greeting")
        message_lower = message.strip().lower()
        
        logger.info(f"📍 Current State: {state}")
        
        # State: Greeting - waiting for agent code
        if state == "greeting":
            logger.info(f"👋 State: GREETING - Waiting for agent code")
            messages = self._get_onboarding_messages()
            
            # Check if user sent "Hi" or similar greeting
            if message_lower in ["hi", "hello", "hey", "hi there"]:
                logger.info(f"👋 User greeted, greeting back and asking for agent code")
                return {
                    "response": messages["greetingMessage"],
                    "new_state": {"state": "greeting"},
                    "agent_active": False
                }
            
            # Check if message looks like an agent code
            # More flexible pattern to match various code formats
            if re.match(r'^[A-Z]{2,}\d{2,}$', message.upper()) or re.match(r'^[A-Z]+\d+$', message.upper()):
                agent_code = message.upper()
                logger.info(f"🔍 Validating agent code: {agent_code}")
                
                # Check if DB is available before querying
                if not self.available or self.agents is None:
                    logger.warning(f"⚠️ MongoDB not available, accepting code without validation")
                    return {
                        "response": messages["menuMessage"].format(
                            agent_name=agent_code,
                            agent_code=agent_code
                        ),
                        "new_state": {
                            "state": "code_entered",
                            "username": agent_code,
                            "agent_code": agent_code
                        },
                        "username": agent_code,
                        "agent_code": agent_code,
                        "agent_active": False
                    }
                
                # Try multiple query patterns to find the agent and validate phone number
                logger.debug(f"   Querying agents collection for: {agent_code}")
                logger.debug(f"   User phone number: {phone_number}")
                
                # First try: exact match with agent_code and is_active
                agent = self.agents.find_one({
                    "agent_code": agent_code,
                    "is_active": True
                })
                
                # If not found, try without is_active filter
                if not agent:
                    logger.debug(f"   Not found with is_active=True, trying without filter...")
                    agent = self.agents.find_one({
                        "agent_code": agent_code
                    })
                
                # If still not found, try case-insensitive search using MongoDB Regex (SCALABLE)
                if not agent:
                    logger.debug(f"   Not found with exact match, trying case-insensitive regex...")
                    # 🔒 ENTERPRISE: Use regex for case-insensitive search instead of loading all agents
                    agent = self.agents.find_one({
                        "agent_code": {"$regex": f"^{re.escape(agent_code)}$", "$options": "i"}
                    })
                
                # Log query result
                if agent:
                    logger.info(f"✅ Agent found!")
                    logger.info(f"   Agent Code: {agent.get('agent_code')}")
                    logger.info(f"   Agent Name: {agent.get('agent_name')}")
                    logger.info(f"   Is Active: {agent.get('is_active')}")
                    logger.debug(f"   Full Agent Data: {agent}")
                    
                    # NOW VALIDATE PHONE NUMBER
                    if phone_number:
                        agent_phone = agent.get("mobile_number") or agent.get("phone_number") or agent.get("contact_number")
                        logger.info(f"🔐 AUTHENTICATING USER")
                        logger.info(f"   User Phone: {phone_number}")
                        logger.info(f"   Agent Phone: {agent_phone}")
                        
                        # Normalize phone numbers for comparison (remove special chars)
                        user_phone_normalized = re.sub(r'\D', '', str(phone_number)) if phone_number else ""
                        agent_phone_normalized = re.sub(r'\D', '', str(agent_phone)) if agent_phone else ""
                        
                        logger.debug(f"   User Phone Normalized: {user_phone_normalized}")
                        logger.debug(f"   Agent Phone Normalized: {agent_phone_normalized}")
                        
                        if agent_phone_normalized and user_phone_normalized == agent_phone_normalized:
                            logger.info(f"✅ AUTHENTICATION SUCCESSFUL - Phone numbers match!")
                            return {
                                "response": messages["menuMessage"].format(
                                    agent_name=agent.get('agent_name', 'Agent'),
                                    agent_code=agent_code
                                ),
                                "new_state": {
                                    "state": "code_entered",
                                    "username": agent.get('agent_name', agent_code),
                                    "agent_code": agent_code,
                                    "authenticated": True
                                },
                                "username": agent.get('agent_name', agent_code),
                                "agent_code": agent_code,
                                "agent_name": agent.get('agent_name'),
                                "agent_active": False
                            }
                        else:
                            logger.warning(f"❌ AUTHENTICATION FAILED - Phone number does not match!")
                            if not agent_phone_normalized:
                                logger.warning(f"   No phone number registered for this agent code")
                            return {
                                "response": messages["authFailedMessage"],
                                "new_state": {"state": "greeting"},
                                "agent_active": False
                            }
                    else:
                        logger.warning(f"⚠️ No phone number available for validation, accepting code")
                        return {
                            "response": messages["menuMessage"].format(
                                agent_name=agent.get('agent_name', 'Agent'),
                                agent_code=agent_code
                            ),
                            "new_state": {
                                "state": "code_entered",
                                "username": agent.get('agent_name', agent_code),
                                "agent_code": agent_code
                            },
                            "username": agent.get('agent_name', agent_code),
                            "agent_code": agent_code,
                            "agent_name": agent.get('agent_name'),
                            "agent_active": False
                        }
                else:
                    logger.warning(f"❌ Agent not found for code: {agent_code}")
                    # Log all agent codes for debugging
                    try:
                        all_codes = [a.get("agent_code") for a in self.agents.find({}, {"agent_code": 1})]
                        logger.debug(f"   Available agent codes in DB: {all_codes}")
                    except Exception as e:
                        logger.error(f"   Error fetching agent codes: {e}")
                    
                    return {
                        "response": messages["invalidCodeMessage"],
                        "new_state": {"state": "greeting"},
                        "agent_active": False
                    }
                if agent:
                    logger.info(f"✅ Agent code validated: {agent_code}")
                    logger.info(f"   Agent Name: {agent.get('agent_name', 'N/A')}")
                    logger.info(f"   Agent Data: {agent}")
                    
                    # Use agent name from database, or create username
                    agent_name = agent.get("agent_name", "Agent")
                    username = agent_name  # Use agent name as username
                    logger.info(f"👤 User: {username}")
                    
                    # Save/update user in MongoDB
                    self.users.update_one(
                        {"agentCode": agent_code},
                        {"$set": {
                            "username": username,
                            "agentCode": agent_code,
                            "agentName": agent_name,
                            "email": agent.get("email"),
                            "phoneNumber": agent.get("phone_number")
                        }},
                        upsert=True
                    )
                    logger.debug(f"💾 User record updated in MongoDB")
                    
                    response = {
                        "response": f"Welcome {username}.\nPlease choose an option:\n1️⃣ Product Recommendation\n2️⃣ Sales Pitch",
                        "new_state": {
                            "state": "code_entered",
                            "username": username,
                            "agent_code": agent_code,
                            "agent_name": agent_name,
                            "agent_data": {
                                "email": agent.get("email"),
                                "phone_number": agent.get("phone_number"),
                                "role": agent.get("role")
                            }
                        },
                        "agent_active": False
                    }
                    logger.info(f"✅ Transitioning to: code_entered")
                    return response
                else:
                    logger.warning(f"❌ Invalid agent code: {agent_code}")
                    return {
                        "response": messages["invalidCodeMessage"],
                        "new_state": {"state": "greeting"},
                        "agent_active": False
                    }
            else:
                # Not a valid code format, ask again
                logger.info(f"⚠️ Invalid code format: {message}")
                return {
                    "response": messages["invalidCodeMessage"],
                    "new_state": {"state": "greeting"},
                    "agent_active": False
                }
        
        # State: Code entered - waiting for option selection
        elif state == "code_entered":
            logger.info(f"📋 State: CODE_ENTERED - Waiting for option selection")
            username = current_state.get("username")
            agent_code = current_state.get("agent_code")
            logger.debug(f"   Username: {username}, Agent Code: {agent_code}")
            messages = self._get_onboarding_messages()
            
            # Check for option selection
            if message_lower in ["1", "option 1", "product recommendation", "product"]:
                logger.info(f"✅ Option 1 selected: Product Recommendation")
                return {
                    "response": "Connecting to Product Recommendation Agent...",
                    "new_state": {
                        **current_state,
                        "state": "agent_active",
                        "agent_type": "product_recommendation"
                    },
                    "agent_active": True,
                    "agent_type": "product_recommendation",
                    "username": username,
                    "agent_code": agent_code
                }
            elif message_lower in ["2", "option 2", "sales pitch", "sales"]:
                logger.info(f"✅ Option 2 selected: Sales Pitch")
                return {
                    "response": "Connecting to Sales Pitch Agent...",
                    "new_state": {
                        **current_state,
                        "state": "agent_active",
                        "agent_type": "sales_pitch"
                    },
                    "agent_active": True,
                    "agent_type": "sales_pitch",
                    "username": username,
                    "agent_code": agent_code
                }
            else:
                logger.warning(f"⚠️ Invalid option selected: {message}")
                return {
                    "response": messages["invalidOptionMessage"],
                    "new_state": current_state,
                    "agent_active": False
                }
        
        # State: Agent active - pass to Lyzr
        elif state == "agent_active":
            logger.info(f"🤖 State: AGENT_ACTIVE - Checking for switch command")
            
            username = current_state.get("username")
            agent_code = current_state.get("agent_code")
            current_agent_type = current_state.get("agent_type")
            messages = self._get_onboarding_messages()
            
            # Check for switch commands
            message_lower = message.strip().lower()
            # 🔒 FIX: Removed "1", "2", "option 1" etc. to avoid hijacking agent questions
            switch_to_product = message_lower in ["switch to product", "product recommendation", "switch to product recommendation"]
            switch_to_sales = message_lower in ["switch to sales", "sales pitch", "switch to sales pitch"]
            back_to_menu = message_lower in ["menu", "back", "options", "switch", "main menu"]
            
            if back_to_menu:
                logger.info(f"🔄 User requested menu/back - checking conversation status and restarting onboarding")
                
                # Check if feedback exists for this session
                has_feedback = False
                agent_type_for_incomplete = current_state.get("agent_type")
                feedback_text = ""
                try:
                    # 🔒 FIX: Use self.db check instead of self.mongo_client (which isn't preserved)
                    if self.db is not None:
                        feedback_collection = self.db.feedback
                        existing_feedback = feedback_collection.find_one({"sessionId": session_id})
                        
                        if existing_feedback:
                            feedback_text = existing_feedback.get("feedback", "")
                            has_feedback = feedback_text and feedback_text.strip() != "" and feedback_text != "Pending" and feedback_text != "incomplete"
                            logger.info(f"   Feedback exists: {has_feedback}")
                            logger.info(f"   Feedback status: {feedback_text[:50] if feedback_text else 'N/A'}...")
                            
                            # Update conversation status based on feedback
                            if has_feedback:
                                # User has provided actual feedback - mark as completed
                                feedback_collection.update_one(
                                    {"sessionId": session_id},
                                    {
                                        "$set": {
                                            "conversationStatus": "completed",
                                            "updatedAt": datetime.utcnow()
                                        }
                                    }
                                )
                                logger.info(f"✅ Updated conversation status to 'completed' in feedback collection")
                            else:
                                # No actual feedback yet - mark as incomplete
                                feedback_collection.update_one(
                                    {"sessionId": session_id},
                                    {
                                        "$set": {
                                            "conversationStatus": "incomplete",
                                            "feedback": "incomplete",
                                            "updatedAt": datetime.utcnow()
                                        }
                                    }
                                )
                                logger.info(f"✅ Updated conversation status to 'incomplete' in feedback collection")
                        else:
                            logger.info(f"   No feedback found for session: {session_id}")
                            # This is an incomplete conversation - will be created in chat.py
                except Exception as e:
                    logger.warning(f"⚠️ Could not check feedback status: {e}")
                
                # Mark conversation status for tracking (will be handled in chat.py)
                conversation_status = "complete" if has_feedback else "incomplete"
                logger.info(f"📊 Conversation status: {conversation_status}")
                logger.info(f"   Has Feedback: {has_feedback}")
                logger.info(f"   Agent Type for incomplete tracking: {agent_type_for_incomplete}")
                
                # RESTART ONBOARDING - Return to greeting state (full restart)
                # All onboarding messages will repeat from the beginning
                logger.info(f"🔄 Restarting onboarding process - returning to greeting state")
                return {
                    "response": messages["greetingMessage"],  # Start from beginning
                    "new_state": {
                        "state": "greeting"  # Full restart - clear all previous state
                    },
                    "agent_active": False,
                    "username": username,  # Keep username for event creation
                    "agent_code": agent_code,  # Keep agent_code for event creation
                    "agent_type": agent_type_for_incomplete,  # Keep agent_type for incomplete tracking
                    "conversation_status": conversation_status,  # Track status for logging
                    "has_feedback": has_feedback,  # Pass feedback status to chat.py
                    "session_id": session_id  # Pass session_id for event creation
                }
            
            elif switch_to_product and current_agent_type != "product_recommendation":
                logger.info(f"🔄 Switching from {current_agent_type} to product_recommendation")
                return {
                    "response": "Switching to Product Recommendation Agent...",
                    "new_state": {
                        **current_state,
                        "agent_type": "product_recommendation"
                    },
                    "agent_active": True,
                    "agent_type": "product_recommendation",
                    "username": username,
                    "agent_code": agent_code
                }
            
            elif switch_to_sales and current_agent_type != "sales_pitch":
                logger.info(f"🔄 Switching from {current_agent_type} to sales_pitch")
                return {
                    "response": "Switching to Sales Pitch Agent...",
                    "new_state": {
                        **current_state,
                        "agent_type": "sales_pitch"
                    },
                    "agent_active": True,
                    "agent_type": "sales_pitch",
                    "username": username,
                    "agent_code": agent_code
                }
            
            # Normal message - pass to current agent
            logger.info(f"📤 Passing message to {current_agent_type} agent")
            return {
                "response": "",  # Will be filled by Lyzr
                "new_state": current_state,
                "agent_active": True,
                "agent_type": current_agent_type,
                "username": username,
                "agent_code": agent_code
            }
        
        # Default: reset to greeting
        else:
            logger.warning(f"⚠️ Unknown state: {state}, resetting to greeting")
            messages = self._get_onboarding_messages()
            return {
                "response": messages["greetingMessage"],
                "new_state": {"state": "greeting"},
                "agent_active": False
            }

