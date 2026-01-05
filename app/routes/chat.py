from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from app.services.bot_logic import BotLogic
from app.services.lyzr_service import LyzrService
# from app.services.redis_service import RedisService  # COMMENTED OUT - Using Lyzr built-in context
from app.services.session_service import SessionService
from app.services.dashboard_service import DashboardService
from app.services.chat_storage import ChatStorage
from app.config.logging_config import get_logger
import uuid
from datetime import datetime

router = APIRouter()
logger = get_logger(__name__)

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str

bot_logic = BotLogic()
lyzr_service = LyzrService()
# redis_service = RedisService()  # COMMENTED OUT
session_service = SessionService()
dashboard_service = DashboardService()
chat_storage = ChatStorage()

@router.post("/chat", response_model=ChatResponse)
async def handle_chat(request: ChatRequest):
    logger.info("=" * 60)
    logger.info(f"📥 INCOMING CHAT REQUEST")
    logger.info(f"   Message: {request.message}")
    logger.info(f"   Session ID: {request.session_id or 'NEW'}")
    logger.info("=" * 60)
    
    try:
        # Get or create session (using in-memory session service)
        session_id = request.session_id or await session_service.get_or_create_session()
        logger.info(f"✅ Session ID: {session_id}")
        
        # Get current state (from in-memory storage)
        state = await session_service.get_session_state(session_id)
        logger.debug(f"📊 Current State: {state}")
        
        # Check if session has expired
        is_expired = await session_service.is_session_expired(session_id)
        if is_expired:
            logger.warning(f"⏰ Session has expired - treating as new session start")
            # Don't reset session, just warn and continue
            # The user would need to provide agent code again
        
        # Process message through bot logic
        logger.info(f"🤖 Processing message through bot logic...")
        result = await bot_logic.process_message(
            message=request.message,
            session_id=session_id,
            current_state=state
        )
        logger.info(f"✅ Bot Logic Result:")
        logger.info(f"   State: {result['new_state'].get('state')}")
        logger.info(f"   Agent Active: {result.get('agent_active')}")
        logger.info(f"   Agent Type: {result.get('agent_type', 'N/A')}")
        logger.info(f"   Conversation Status: {result.get('conversation_status', 'N/A')}")
        logger.info(f"   Has Feedback: {result.get('has_feedback', 'N/A')}")
        logger.info(f"   Username: {result.get('username', 'N/A')}")
        logger.info(f"   Agent Code: {result.get('agent_code', 'N/A')}")
        logger.info(f"   Response: {result['response'][:100]}...")
        logger.info(f"   Full result keys: {list(result.keys())}")
        
        # Handle conversation tracking when user types menu/back
        conversation_status_value = result.get("conversation_status")
        logger.info(f"🔍 Checking conversation_status: '{conversation_status_value}' (type: {type(conversation_status_value)}, truthy: {bool(conversation_status_value)})")
        logger.info(f"   Result dictionary contains conversation_status: {'conversation_status' in result}")
        
        # Check for conversation status (incomplete or complete)
        if conversation_status_value in ["incomplete", "complete"]:
            logger.info(f"✅ Conversation status found: {conversation_status_value}")
            conversation_status = result.get("conversation_status")
            has_feedback = result.get("has_feedback", False)
            username = result.get("username") or state.get("username")
            agent_code = result.get("agent_code") or state.get("agent_code")
            # Use agent_type_for_incomplete from bot logic if available, otherwise use state
            agent_type = result.get("agent_type_for_incomplete") or result.get("agent_type") or state.get("agent_type")
            
            logger.info(f"📊 Handling conversation end - Status: {conversation_status}")
            logger.info(f"   Username: {username}, Agent Code: {agent_code}, Agent Type: {agent_type}")
            logger.info(f"   Has Feedback: {has_feedback}, Session ID: {session_id}")
            
            try:
                if has_feedback:
                    # If feedback exists, ensure session_end event is created (conversation complete)
                    logger.info(f"📝 Creating session_end event (conversation complete)")
                    await dashboard_service.create_session_end_event(
                        session_id=session_id,
                        username=username,
                        agent_code=agent_code
                    )
                    logger.info(f"✅ Session end event created (conversation complete)")
                    logger.info(f"   Event Type: session_end")
                else:
                    # Create incomplete conversation event and save to Feedback collection
                    logger.info(f"📝 Creating incomplete_conversation event (no feedback provided)")
                    logger.info(f"   Session: {session_id}")
                    logger.info(f"   User: {username}")
                    logger.info(f"   Agent: {agent_code}")
                    logger.info(f"   Agent Type: {agent_type}")
                    
                    await dashboard_service.create_incomplete_conversation_event(
                        session_id=session_id,
                        username=username,
                        agent_code=agent_code,
                        agent_type=agent_type
                    )
                    logger.info(f"✅ Incomplete conversation event created and saved to Feedback collection")
                    logger.info(f"   Event Type: incomplete_conversation")
                    logger.info(f"🔄 Dashboard should update via WebSocket with new incomplete conversation count")
            except Exception as e:
                logger.error(f"❌ Error creating conversation end event: {e}", exc_info=True)
                logger.error(f"   Status: {conversation_status}")
                logger.error(f"   Has Feedback: {has_feedback}")
                raise
        else:
            if result.get("conversation_status") is None:
                logger.warning(f"⚠️ No conversation_status in result - conversation tracking skipped")
                logger.warning(f"   Available keys in result: {list(result.keys())}")
            else:
                logger.warning(f"⚠️ Conversation status is not 'incomplete' or 'complete': '{conversation_status_value}'")
        
        # Update session state (in-memory)
        await session_service.update_session_state(session_id, result["new_state"])
        logger.debug(f"💾 Session state updated in memory")
        
        # Save user message to MongoDB
        try:
            await chat_storage.save_message(
                session_id=session_id,
                role="user",
                message=request.message,
                username=result.get("username"),
                agent_code=result.get("agent_code"),
                agent_name=result.get("agent_name"),
                state=result["new_state"].get("state")
            )
        except Exception as e:
            logger.error(f"❌ Failed to save user message: {e}")
        
        # Track conversation start - Create session event when agent code is validated
        if result["new_state"].get("state") == "code_entered" and result.get("username") and result.get("agent_code"):
            logger.info(f"🆕 Conversation started - Agent code validated")
            try:
                await dashboard_service.create_session_event(
                    result.get("username"),
                    result.get("agent_code")
                )
                logger.info(f"✅ Session event created in dashboard")
            except Exception as e:
                logger.error(f"❌ Failed to create session event: {e}")
        
        # If agent is active, get response from Lyzr
        if result.get("agent_active"):
            logger.info(f"🚀 Agent is active - routing to Lyzr")
            
            # Log username and code when user selects Product Recommendation or Sales Pitch
            username = result.get('username', 'N/A')
            agent_code = result.get('agent_code', 'N/A')
            
            if result.get("agent_type") in ("product_recommendation", "sales_pitch"):
                logger.info("=" * 70)
                logger.info(f"👤 USER SELECTED: {result['agent_type'].upper().replace('_', ' ')}")
                logger.info(f"   Username: {username}")
                logger.info(f"   Agent Code: {agent_code}")
                logger.info(f"   Session ID: {session_id}")
                logger.info(f"   Timestamp: {datetime.utcnow().isoformat()}")
                logger.info("=" * 70)
            
            # Fetch customized agent configuration if it exists
            custom_role = None
            custom_goal = None
            custom_instructions = None
            
            try:
                from app.services.customized_agent_service import CustomizedAgentService
                customized_agent_service = CustomizedAgentService()
                
                customized_agent = await customized_agent_service.get_customized_agent(
                    session_id=session_id,
                    agent_type=result["agent_type"]
                )
                
                if customized_agent:
                    custom_role = customized_agent.get("role")
                    custom_goal = customized_agent.get("goal")
                    custom_instructions = customized_agent.get("instructions")
                    logger.info(f"✨ Customized agent configuration found and will be used:")
                    logger.info(f"   Role: {custom_role[:100] if custom_role else 'N/A'}...")
                    logger.info(f"   Goal: {custom_goal[:100] if custom_goal else 'N/A'}...")
                    logger.info(f"   Instructions: {custom_instructions[:100] if custom_instructions else 'N/A'}...")
                else:
                    logger.info(f"📌 Using default agent configuration (no customization found)")
            except Exception as e:
                logger.warning(f"⚠️ Could not fetch customized agent config: {e}")
            
            # Track agent selection
            logger.info(f"🔗 Calling Lyzr Agent: {result['agent_type']}")
            logger.info(f"   Username: {username}")
            logger.info(f"   Agent Code: {agent_code}")
            
            # Get agent ID based on configuration (customized or default)
            agent_id = await lyzr_service.get_agent_id(result["agent_type"])
            
            # Clean username - remove trailing numbers (e.g. "Rohith 1" -> "Rohith")
            cleaned_username = username
            if username and username != 'N/A':
                import re
                cleaned_username = re.sub(r'\s+\d+$', '', username)
                logger.info(f"🧹 Cleaned username: '{username}' -> '{cleaned_username}'")

            # Prepare message to send to Lyzr - include only username (not agent code)
            # Prepare message to send to Lyzr
            # LOGIC CHANGE: Only send "User: {username}" for the FIRST message to the agent.
            # Subsequent messages should be just the user's text to reduce latency/tokens and avoid repetition.
            
            # Check if we have already sent the initial message for this agent session
            first_message_sent = state.get("first_message_sent", False)
            current_agent_type = result.get("agent_type")
            previous_agent_type = state.get("previous_agent_type")
            
            # If agent type changed, reset first_message_sent
            if current_agent_type != previous_agent_type:
                first_message_sent = False
                
            message_to_send = request.message
            
            # Only prepend username if this is the FIRST message to this agent
            if not first_message_sent and result.get("agent_type") in ("product_recommendation", "sales_pitch") and username != 'N/A':
                # Prepend only username to the message (agent code is not sent to Lyzr)
                message_to_send = f"User: {cleaned_username}\n\n{request.message}"
                logger.info(f"📤 FIRST MESSAGE: Including username '{cleaned_username}'")
                logger.info(f"   Enhanced message: {message_to_send[:150]}...")
                
                # Update state to mark first message as sent
                result["new_state"]["first_message_sent"] = True
                result["new_state"]["previous_agent_type"] = current_agent_type
                # We need to update the session state immediately to reflect this change
                await session_service.update_session_state(session_id, result["new_state"])
            else:
                logger.info(f"📤 SUBSEQUENT MESSAGE: Sending raw user text only")
            
            # Use get_agent_response with custom prompts
            try:
                agent_response = await lyzr_service.get_agent_response(
                    session_id=session_id,
                    agent_type=result["agent_type"],
                    message=message_to_send,
                    username=cleaned_username if username != 'N/A' else None,
                    agent_code=result.get('agent_code'),
                    custom_role=custom_role,
                    custom_goal=custom_goal,
                    custom_instructions=custom_instructions
                )
                
                logger.info(f"✅ Lyzr Agent Response Received:")
                logger.info(f"   Type: {type(agent_response)}")
                
                # Handle response (could be dict, list, or string)
                if isinstance(agent_response, dict):
                    # Check if this is an error response
                    if agent_response.get("status") == "failed" or "error" in agent_response:
                        # Use user-friendly message if available, otherwise use error message
                        response_text = agent_response.get("user_message") or agent_response.get("error", "An error occurred. Please try again.")
                        logger.error(f"❌ Lyzr Agent Error Response:")
                        logger.error(f"   Error: {agent_response.get('error', 'Unknown error')}")
                        logger.error(f"   Status Code: {agent_response.get('status_code', 'N/A')}")
                        logger.error(f"   User Message: {response_text}")
                    else:
                        # Normal response dict - convert to string
                        response_text = str(agent_response)
                elif isinstance(agent_response, list):
                    response_text = str(agent_response)
                else:
                    response_text = str(agent_response)
                
                logger.info(f"   Length: {len(response_text)} characters")
                logger.info(f"   Preview: {response_text[:150]}...")
                
                result["response"] = response_text
                
                # Save agent response to MongoDB
                try:
                    # Get Lyzr session ID for this session and agent type
                    from app.services.lyzr_service import get_lyzr_session_id
                    lyzr_session_id = get_lyzr_session_id(session_id, result["agent_type"])
                    
                    await chat_storage.save_message(
                        session_id=session_id,
                        role="agent",
                        message=response_text,
                        username=result.get("username"),
                        agent_code=result.get("agent_code"),
                        agent_name=result.get("agent_name"),
                        agent_type=result["agent_type"],
                        state=result["new_state"].get("state"),
                        lyzr_session_id=lyzr_session_id
                    )
                    logger.info(f"✅ Agent response saved to MongoDB")
                    if lyzr_session_id:
                        logger.debug(f"   Lyzr Session ID: {lyzr_session_id[:12]}...")
                except Exception as e:
                    logger.error(f"❌ Failed to save agent response: {e}")
                
                # Create dashboard event for agent completion
                try:
                    if result["agent_type"] == "product_recommendation":
                        logger.info(f"📊 Creating product recommendation event in dashboard")
                        await dashboard_service.create_recommendation_event(session_id)
                    elif result["agent_type"] == "sales_pitch":
                        logger.info(f"📊 Creating sales pitch event in dashboard")
                        await dashboard_service.create_sales_pitch_event(session_id)
                    logger.info(f"✅ Dashboard event created for agent type: {result['agent_type']}")
                except Exception as e:
                    logger.error(f"❌ Failed to create dashboard event: {e}")
                    
            except Exception as e:
                logger.error(f"❌ Error calling Lyzr agent: {e}", exc_info=True)
                result["response"] = f"Sorry, I encountered an error. Please try again."
        else:
            # Save bot response to MongoDB
            try:
                await chat_storage.save_message(
                    session_id=session_id,
                    role="bot",
                    message=result["response"],
                    username=result.get("username"),
                    agent_code=result.get("agent_code"),
                    agent_name=result.get("agent_name"),
                    state=result["new_state"].get("state")
                )
                logger.info(f"✅ Bot response saved to MongoDB")
            except Exception as e:
                logger.error(f"❌ Failed to save bot response: {e}")
        
        # Update session metadata (in-memory)
        if result.get("username"):
            metadata = {
                "username": result.get("username"),
                "agent_code": result.get("agent_code"),
                "agent_type": result.get("agent_type"),
                "state": result["new_state"].get("state")
            }
            await session_service.set_session_metadata(session_id, metadata)
            logger.debug(f"💾 Session metadata updated")
        
        logger.info("=" * 60)
        logger.info(f"📤 OUTGOING CHAT RESPONSE")
        logger.info(f"   Session ID: {session_id}")
        logger.info(f"   Response Length: {len(result['response'])} characters")
        logger.info("=" * 60)
        
        return ChatResponse(response=result["response"], session_id=session_id)
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ ERROR in chat endpoint")
        logger.error(f"   Error: {str(e)}")
        logger.error(f"   Session ID: {session_id if 'session_id' in locals() else 'N/A'}")
        logger.error("=" * 60, exc_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

