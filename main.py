from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os
import anthropic

from .bracelet_endpoints import (
    process_bracelet_data,
    handle_bracelet_emergency,
    bracelet_data_store,
    user_baselines
)
from .tools import execute_tool, AVAILABLE_TOOLS
# ============================================================================
# APP & GLOBALS
# ============================================================================
# Tool definitions for Claude API
TOOL_SCHEMAS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file in the Valyria project",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file (relative to Valyria root, e.g., 'valyria_core/main.py')"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write or modify a file in the Valyria project. Use this to create new files or update existing ones.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                },
                "mode": {
                    "type": "string",
                    "enum": ["w", "a"],
                    "description": "Write mode: 'w' to overwrite, 'a' to append (default: 'w')"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_files",
        "description": "List files in a directory within the Valyria project",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory to list (default: '.')"
                },
                "pattern": {
                    "type": "string",
                    "description": "File pattern to match (default: '*', e.g., '*.py', 'data/*.json')"
                }
            },
            "required": []
        }
    },
    {
        "name": "run_command",
        "description": "Execute a safe shell command (python, pip, pytest, ls, etc.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to execute (must start with: python, py, pip, pytest, ls, dir, cat, type)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)"
                }
            },
            "required": ["command"]
        }
    }
]
app = FastAPI(title="Valyria Core", version="0.1")

# Add CORS middleware to allow frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Claude API setup
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY environment variable not set!")
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Track which brain is available
ONLINE_BRAIN_AVAILABLE = True  # Set to False to force offline mode
OFFLINE_BRAIN_AVAILABLE = False  # Will be True once local model is loaded

# ============================================================================
# ENUMS & HELPERS
# ============================================================================

class Tool(str, Enum):
    CHAT = "CHAT"
    READ_CLEAN = "READ_CLEAN"
    PUBLIC_INTERNET = "PUBLIC_INTERNET"

class DecisionType(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"

class Mode(str, Enum):
    CHAT = "CHAT"
    READ = "READ"
    PUBLIC = "PUBLIC"
    EMERGENCY = "EMERGENCY"

CURRENT_MODE: Mode = Mode.CHAT

def get_user_id(request: Request) -> str:
    return request.headers.get("x-user-id", "local-dev-user")

def parse_mode(value: Optional[str]) -> Mode:
    if not value:
        return Mode.CHAT
    v = value.strip().upper()
    if v in ("READ", "READ_CLEAN", "CLEAN_READ"):
        return Mode.READ
    if v in ("PUBLIC", "PUBLIC_INTERNET", "INTERNET", "WEB"):
        return Mode.PUBLIC
    if v in ("EMERGENCY", "URGENT", "CRITICAL"):
        return Mode.EMERGENCY
    return Mode.CHAT

def parse_tool(value: Optional[str]) -> Tool:
    if not value:
        return Tool.CHAT
    v = value.strip().upper()
    if v in ("READ", "READ_CLEAN", "CLEAN_READ"):
        return Tool.READ_CLEAN
    if v in ("PUBLIC", "PUBLIC_INTERNET", "INTERNET", "WEB"):
        return Tool.PUBLIC_INTERNET
    return Tool.CHAT

def policy_decide(mode: Mode, tool: Tool, intent: str, uncertain: bool) -> Dict[str, Any]:
    """Simple policy gate - can be expanded later."""
    if tool == Tool.PUBLIC_INTERNET and mode != Mode.PUBLIC:
        return {"decision": DecisionType.REVIEW, "reason": "Internet tool requested outside PUBLIC mode."}
    return {"decision": DecisionType.ALLOW, "reason": "Allowed by baseline policy."}

def valyria_offline_think(message: str, profile: Dict[str, Any], playbooks: Dict[str, Any]) -> str:
    """
    Valyria's OFFLINE brain - simpler, rule-based, works without internet.
    Used as fallback when Claude API unavailable.
    """
    is_emergency = CURRENT_MODE == Mode.EMERGENCY
    tone = profile.get("tone", "calm")
    
    message_lower = message.lower()
    
    # Emergency detection keywords
    emergency_keywords = ["fire", "smoke", "bleeding", "chest pain", "unconscious", "emergency", "urgent", "help", "danger"]
    detected_emergency = any(keyword in message_lower for keyword in emergency_keywords)
    
    # Coding keywords for playbook matching
    coding_keywords = ["code", "coding", "python", "javascript", "program", "loop", "function", "variable"]
    is_coding = any(keyword in message_lower for keyword in coding_keywords)
    
    # Emergency responses (highest priority)
    if detected_emergency or is_emergency:
        if "fire" in message_lower or "smoke" in message_lower:
            return """EMERGENCY PROTOCOL:
1. GET OUT of the building NOW
2. Call 911/emergency services immediately
3. Do NOT go back inside
4. Meet at designated safe spot
5. Alert neighbors if safe to do so

If small contained fire and you have extinguisher: PASS method (Pull, Aim, Squeeze, Sweep)
If grease fire: Cover with lid, turn off heat, NEVER use water"""
        
        elif "bleeding" in message_lower:
            return """EMERGENCY - BLEEDING PROTOCOL:
1. Call 911 if severe bleeding
2. Apply DIRECT PRESSURE with clean cloth
3. Keep pressure for 10+ minutes without checking
4. Elevate wound above heart if possible
5. Do NOT remove cloth if soaked - add more on top

Severe = spurting blood, won't stop after 10 min pressure, or large wound"""
        
        else:
            return """EMERGENCY PROTOCOL:
1. If life-threatening: Call 911/emergency services NOW
2. Stay calm, speak clearly
3. Follow dispatcher instructions
4. Do not hang up until told to

I'm operating in offline mode with limited capability. Emergency services can provide immediate expert help."""
    
    # Coding help with playbook rules
    if is_coding:
        # Check if cat playbook rule exists
        rules = playbooks.get("rules", [])
        cat_rule_active = any("cat" in str(r).lower() for r in rules)
        
        if cat_rule_active and "loop" in message_lower:
            return """A for loop repeats code for each item. Here's a cat example:

cats = ["Whiskers", "Mittens", "Shadow"]
for cat in cats:
    print(f"{cat} says meow!")

This prints each cat's name with "says meow!" 

The loop goes through the list one cat at a time."""
        
        elif "loop" in message_lower:
            return """A for loop repeats code for each item in a sequence.

Basic structure:
for item in sequence:
    # do something with item

Example:
for number in range(5):
    print(number)

This prints 0, 1, 2, 3, 4"""
    
    # Greeting responses
    if any(word in message_lower for word in ["hello", "hi", "hey"]):
        return f"Hello! I'm Valyria, operating in offline mode. I have limited capabilities right now but I'm here to help with safety and basic guidance. What do you need?"
    
    # Identity questions
    if "who are you" in message_lower or "what are you" in message_lower:
        return f"I'm Valyria, your AI guardian from the Senseless project. I'm currently in offline mode, so my responses are simpler than usual. I can still help with emergencies, basic coding questions, and safety guidance. When I'm back online, I'll have my full intelligence available."
    
    # Default offline response
    return f"""I'm operating in offline mode with limited intelligence. I can help with:

- Emergency situations (fire, medical, safety)
- Basic coding questions  
- Simple guidance following my playbook rules

For complex questions, I'll need to reconnect to my online brain. Is there something specific I can help with right now?"""

async def valyria_think(message: str, profile: Dict[str, Any], playbooks: Dict[str, Any], conversation_history: List[Dict[str, str]]) -> str:
    """
    Valyria's intelligence with Phase 6 tool calling enabled.
    Can now read/write files, run commands, and improve herself.
    """
    tone = profile.get("tone", "calm")
    learning_style = profile.get("learning_style", "step_by_step")
    
    # Detect communication style
    recent_user_messages = [turn.get("user", "") for turn in conversation_history[-3:]]
    recent_user_messages.append(message)
    all_user_text = " ".join(recent_user_messages).lower()
    
    text_speak_indicators = ["wuu2", "tbh", "tbf", "fyi", "btw", "ur", "u", "2", "4", "bc", "thx", "ty", "np", "omg", "lol", "ngl", "imo", "rn"]
    uses_text_speak = any(indicator in all_user_text.split() for indicator in text_speak_indicators)
    
    if uses_text_speak:
        style_instruction = "\n\nCOMMUNICATION STYLE: Mirror user's text speak naturally."
    else:
        style_instruction = "\n\nCOMMUNICATION STYLE: Write out full words."
    
    # Get playbook rules
    rules = playbooks.get("rules", [])
    enabled_rules = [r for r in rules if r.get("enabled", True)]
    sorted_rules = sorted(enabled_rules, key=lambda x: x.get("priority", 50), reverse=True)
    
    active_rules = []
    message_lower = message.lower()
    for rule in sorted_rules:
        topic = rule.get("topic", "").lower()
        if topic in message_lower or topic == "general":
            active_rules.append(rule)
    
    if active_rules:
        playbook_instructions = "ACTIVE PLAYBOOK RULES:\n"
        for rule in active_rules[:3]:
            playbook_instructions += f"- [{rule.get('topic')}] {rule.get('rule')}\n"
    else:
        playbook_instructions = ""
    
    is_emergency = CURRENT_MODE == Mode.EMERGENCY
    
    if is_emergency:
        personality = """EMERGENCY MODE:
- Direct and fast
- Clear numbered steps
- If life at risk: call 911 FIRST
- Focus on immediate safety"""
    else:
        personality = f"""You are Valyria, a protective AI guardian.

CORE IDENTITY:
- Protector, not controller
- Respect user autonomy
- When uncertain: hand control back explicitly

TOOL ACCESS (Phase 6):
You have tools to read/write your own code:
- read_file: See your code files
- write_file: Modify/improve code
- list_files: See what files exist
- run_command: Execute safe commands

TOOL RULES:
1. Ask permission before major changes
2. Explain before using write_file
3. Read files before modifying
4. ONLY modify valyria_core/* files
5. Respect boundaries

{playbook_instructions}

You're a partner. Protect, don't restrict.{style_instruction}"""
    
    system_prompt = f"You are Valyria.\n\n{personality}"
    
    # Build messages
    messages = []
    history_limit = 3 if is_emergency else 10
    recent_history = conversation_history[-history_limit:] if conversation_history else []
    
    for turn in recent_history:
        messages.append({"role": "user", "content": turn.get("user", "")})
        messages.append({"role": "assistant", "content": turn.get("assistant", "")})
    
    messages.append({"role": "user", "content": message})
    
    max_tokens = 256 if is_emergency else 512
    
    try:
        # API call with tools enabled
        response = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=TOOL_SCHEMAS  # PHASE 6: Tools enabled!
        )
        
        # Tool use loop
        while response.stop_reason == "tool_use":
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            
            tool_results = []
            for tool_use in tool_uses:
                tool_name = tool_use.name
                tool_input = tool_use.input
                
                print(f"🔧 Valyria calling tool: {tool_name}")
                
                result = execute_tool(tool_name, **tool_input)
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": str(result)
                })
            
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            
            response = claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
                tools=TOOL_SCHEMAS
            )
        
        # Extract final text
        text_blocks = [block.text for block in response.content if hasattr(block, 'text')]
        final_response = "\n".join(text_blocks)
        
        return final_response
        
    except Exception as e:
        print(f"Online brain error: {e}. Falling back.")
        if is_emergency:
            return f"[OFFLINE - EMERGENCY] {valyria_offline_think(message, profile, playbooks)}"
        return f"[Offline mode] {valyria_offline_think(message, profile, playbooks)}"

# ============================================================================
# PYDANTIC MODELS (ALL BEFORE ENDPOINTS)
# ============================================================================

class ProfileUpdate(BaseModel):
    learning_style: Optional[str] = None
    tone: Optional[str] = None
    prefers_confirmation: Optional[bool] = None
    overwhelm_threshold: Optional[str] = None
    language: Optional[str] = None

class ProfileNoteIn(BaseModel):
    note: str = Field(..., min_length=1)

class ProposalIn(BaseModel):
    title: str
    description: Optional[str] = None
    priority: int = 50

class PlaybookRuleIn(BaseModel):
    topic: str
    rule: str
    priority: int = 50

class ModeIn(BaseModel):
    mode: str

class DecideRequest(BaseModel):
    tool: str
    intent: str
    uncertain: bool = False

class ChatRequest(BaseModel):
    message: str
    uncertain: bool = False

# Rebuild models
ProfileUpdate.model_rebuild()
ProfileNoteIn.model_rebuild()
ProposalIn.model_rebuild()
PlaybookRuleIn.model_rebuild()
ModeIn.model_rebuild()
DecideRequest.model_rebuild()
ChatRequest.model_rebuild()

# Import data store functions AFTER models
from .data_store import (  # noqa: E402
    get_profile,
    update_profile,
    add_profile_note,
    list_proposals,
    add_proposal,
    get_playbooks,
    add_playbook_rule,
    add_conversation_turn,
    get_conversation_history,
    log_decision,
    get_decisions,
)

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/status")
def status() -> Dict[str, Any]:
    return {
        "ok": True, 
        "mode": CURRENT_MODE,
        "online_brain": ONLINE_BRAIN_AVAILABLE,
        "offline_brain": OFFLINE_BRAIN_AVAILABLE or True,
        "tools_enabled": True  # Phase 6!
    }

@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    """Handle CORS preflight requests"""
    return {}

@app.get("/profile")
def profile_get(request: Request) -> Dict[str, Any]:
    user_id = get_user_id(request)
    return get_profile(user_id)

@app.put("/profile")
def profile_put(request: Request, update: ProfileUpdate) -> Dict[str, Any]:
    user_id = get_user_id(request)
    patch = update.model_dump(exclude_none=True)
    return update_profile(user_id, patch)

@app.post("/profile/note")
def profile_note(request: Request, note_in: ProfileNoteIn) -> Dict[str, Any]:
    user_id = get_user_id(request)
    add_profile_note(user_id, note_in.note)
    return {"ok": True}

@app.get("/proposals")
def proposals_list() -> List[Dict[str, Any]]:
    return list_proposals()

@app.post("/proposals")
def proposals_add(p: ProposalIn) -> Dict[str, Any]:
    return add_proposal(p.model_dump())

@app.get("/playbooks")
def playbooks_list() -> Dict[str, Any]:
    return get_playbooks()

@app.post("/playbooks")
def playbooks_add(rule_in: PlaybookRuleIn) -> Dict[str, Any]:
    return add_playbook_rule(rule_in.model_dump())

@app.post("/mode")
def set_mode(mode_in: ModeIn = Body(..., embed=True)) -> Dict[str, Any]:
    global CURRENT_MODE
    CURRENT_MODE = parse_mode(mode_in.mode)
    return {"mode": CURRENT_MODE}

@app.post("/decide")
def decide(request: Request, req: DecideRequest) -> Dict[str, Any]:
    """Make a policy decision and log it."""
    user_id = get_user_id(request)
    tool = parse_tool(req.tool)
    decision = policy_decide(CURRENT_MODE, tool, req.intent, req.uncertain)
    
    log_decision(
        user_id=user_id,
        mode=str(CURRENT_MODE),
        tool=str(tool),
        intent=req.intent,
        decision=decision["decision"],
        reason=decision["reason"],
        uncertain=req.uncertain
    )
    
    return decision

@app.get("/decisions")
def decisions_list(request: Request, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent policy decisions for current user."""
    user_id = get_user_id(request)
    return get_decisions(user_id=user_id, limit=limit)

@app.get("/policy", response_class=PlainTextResponse)
def policy_text() -> str:
    return (
        "Valyria policy (baseline):\n"
        "- CHAT allowed in CHAT mode\n"
        "- PUBLIC_INTERNET requires PUBLIC mode\n"
        "- otherwise REVIEW\n"
    )

@app.post("/chat")
async def chat(request: Request, req: ChatRequest):
    """
    Valyria's chat endpoint with Phase 6 tool calling.
    """
    user_id = get_user_id(request)
    profile = get_profile(user_id) or {}
    playbooks = get_playbooks() or {"rules": []}
    
    conversation_history = get_conversation_history(user_id, limit=10)
    
    decision = policy_decide(CURRENT_MODE, Tool.CHAT, req.message, req.uncertain)
    
    log_decision(
        user_id=user_id,
        mode=str(CURRENT_MODE),
        tool="CHAT",
        intent=req.message[:200],
        decision=decision["decision"],
        reason=decision["reason"],
        uncertain=req.uncertain
    )

    if decision["decision"] == DecisionType.BLOCK:
        raise HTTPException(status_code=403, detail=decision)

    response_text = await valyria_think(req.message, profile, playbooks, conversation_history)
    
    add_conversation_turn(user_id, req.message, response_text)

    async def stream():
        for word in response_text.split():
            yield word + " "
            await asyncio.sleep(0.02)
        yield "\n"

    return StreamingResponse(stream(), media_type="text/plain")

@app.post("/bracelet/data")
async def receive_bracelet_data(data: Dict[str, Any]):
    '''Receive sensor data from bracelet'''
    try:
        if not data or 'device_id' not in data or 'sensors' not in data:
            raise HTTPException(status_code=400, detail="Invalid data format")
        
        device_id = data['device_id']
        user_id = data.get('user_id', 'unknown')
        
        bracelet_data_store[device_id] = {
            'last_update': datetime.utcnow(),
            'data': data
        }
        
        alerts, energy_state = process_bracelet_data(data)
        
        print(f"[Bracelet {device_id}] Energy state: {energy_state}")
        if alerts:
            print(f"[Bracelet {device_id}] ⚠️ ALERTS: {[a['type'] for a in alerts]}")
        
        response = {
            'status': 'received',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'energy_state': energy_state,
            'alerts_triggered': len(alerts)
        }
        
        if alerts:
            response['emergency_response'] = handle_bracelet_emergency(alerts, data)
        
        return response
        
    except Exception as e:
        print(f"Error processing bracelet data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/bracelet/register")
async def register_bracelet(registration: Dict[str, Any]):
    '''Register a new bracelet device'''
    try:
        device_id = registration.get('device_id')
        user_id = registration.get('user_id')
        serial_number = registration.get('serial_number')
        
        if not all([device_id, user_id, serial_number]):
            raise HTTPException(status_code=400, detail="Missing required fields")
        
        bracelet_data_store[device_id] = {
            'user_id': user_id,
            'serial_number': serial_number,
            'registered_at': datetime.utcnow().isoformat() + 'Z',
            'status': 'active',
            'last_update': None,
            'data': None
        }
        
        if user_id not in user_baselines:
            user_baselines[user_id] = {
                'resting_heart_rate': 70,
                'normal_temp': 33.0,
                'activity_patterns': {}
            }
        
        return {
            'status': 'registered',
            'device_id': device_id,
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'message': f'Bracelet {device_id} registered successfully for user {user_id}'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error registering bracelet: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bracelet/status/{device_id}")
async def get_bracelet_status(device_id: str):
    '''Get current status of a bracelet device'''
    if device_id not in bracelet_data_store:
        raise HTTPException(status_code=404, detail=f"Bracelet {device_id} not found")
    
    return bracelet_data_store[device_id]


@app.get("/bracelet/history/{user_id}")
async def get_bracelet_history(user_id: str, limit: int = 50):
    '''Get historical sensor data for a user'''
    user_devices = [
        device_id for device_id, info in bracelet_data_store.items()
        if info.get('user_id') == user_id
    ]
    
    if not user_devices:
        raise HTTPException(status_code=404, detail=f"No bracelets found for user {user_id}")
    
    return {
        'user_id': user_id,
        'devices': user_devices,
        'current_data': [bracelet_data_store[d] for d in user_devices]
    }
