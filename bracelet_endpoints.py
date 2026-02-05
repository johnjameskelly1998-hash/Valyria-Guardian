"""
Bracelet API Endpoints for Valyria
Handles sensor data, emergency detection, and energy state tracking
Based on BRACELET_SPEC.md
"""

from fastapi import HTTPException
from typing import Dict, Any, List
from datetime import datetime

# Global storage for bracelet data (in production, use database)
bracelet_data_store: Dict[str, Dict[str, Any]] = {}
user_baselines: Dict[str, Dict[str, float]] = {}


# ============================================================================
# EMERGENCY DETECTION LOGIC
# ============================================================================

def determine_energy_state(bpm: float, temp_c: float, intensity: float, activity: str) -> str:
    """
    Determine user's energy state based on sensor readings.
    States: calm, active, stressed, anxious, emergency
    """
    # Emergency: Override everything if critical conditions
    if bpm > 160 or bpm < 45:
        return "emergency"
    if temp_c > 38.0 or temp_c < 30.0:
        return "emergency"
    
    # Anxious: High HR, cold sweat, restless motion
    if bpm > 120 and temp_c < 31.0 and intensity > 2:
        return "anxious"
    
    # Stressed: Elevated HR, variable temp, agitated
    if 100 <= bpm <= 120 and intensity > 3:
        return "stressed"
    
    # Active: Elevated HR, motion elevated, temp slightly up
    if 80 <= bpm <= 100 and intensity > 1:
        return "active"
    
    # Calm: Normal HR, normal temp, minimal motion (default)
    if 60 <= bpm <= 80 and intensity < 1:
        return "calm"
    
    # Running: High activity but controlled
    if activity == "running":
        return "active"
    
    # Default to calm if no other state matches
    return "calm"


def process_bracelet_data(data: Dict[str, Any]) -> tuple[List[Dict[str, Any]], str]:
    """
    Process bracelet sensor data and return alerts + energy state.
    Returns: (alerts, energy_state)
    """
    sensors = data.get('sensors', {})
    heart_rate = sensors.get('heart_rate', {})
    temperature = sensors.get('temperature', {})
    motion = sensors.get('motion', {})
    
    # Extract values
    bpm = heart_rate.get('bpm', 70)
    hrv = heart_rate.get('hrv', 50)
    temp_c = temperature.get('celsius', 33.0)
    activity = motion.get('activity', 'unknown')
    fall_detected = motion.get('fall_detected', False)
    intensity = motion.get('intensity', 0)
    
    alerts = []
    
    # ========================================================================
    # EMERGENCY DETECTION (from BRACELET_SPEC.md)
    # ========================================================================
    
    # 1. Panic Detection
    # Triggers: HR >130 BPM + temp drop >2°C (cold sweat) + elevated motion
    if bpm > 130 and temp_c < 31.0 and intensity > 3:
        alerts.append({
            'type': 'PANIC',
            'severity': 'HIGH',
            'trigger': {
                'heart_rate': bpm,
                'temperature': temp_c,
                'motion_intensity': intensity
            },
            'message': 'Panic attack detected - elevated HR, cold sweat, agitated movement'
        })
    
    # 2. Fall Detection
    # Triggers: Sudden acceleration >8G + stillness
    if fall_detected:
        alerts.append({
            'type': 'FALL',
            'severity': 'HIGH',
            'trigger': {
                'fall_detected': True,
                'activity': activity
            },
            'message': 'Fall detected - immediate response needed'
        })
    
    # 3. Medical Emergency - Heart Rate
    # Triggers: HR <45 or >160 BPM sustained
    if bpm < 45 or bpm > 160:
        alerts.append({
            'type': 'MEDICAL',
            'severity': 'CRITICAL',
            'trigger': {
                'heart_rate': bpm
            },
            'message': f'Critical heart rate: {bpm} BPM'
        })
    
    # 4. Medical Emergency - Temperature
    # Triggers: Fever (>38°C) or Hypothermia (<30°C)
    if temp_c > 38.0:
        alerts.append({
            'type': 'MEDICAL',
            'severity': 'HIGH',
            'trigger': {
                'temperature': temp_c
            },
            'message': f'Fever detected: {temp_c}°C'
        })
    elif temp_c < 30.0:
        alerts.append({
            'type': 'MEDICAL',
            'severity': 'HIGH',
            'trigger': {
                'temperature': temp_c
            },
            'message': f'Hypothermia risk: {temp_c}°C'
        })
    
    # 5. Heart Rate Variability - Cardiac Event Indicator
    # Low HRV can indicate cardiac stress
    if hrv < 20 and bpm > 100:
        alerts.append({
            'type': 'MEDICAL',
            'severity': 'MEDIUM',
            'trigger': {
                'hrv': hrv,
                'heart_rate': bpm
            },
            'message': 'Low heart rate variability - possible cardiac stress'
        })
    
    # Determine energy state
    energy_state = determine_energy_state(bpm, temp_c, intensity, activity)
    
    return alerts, energy_state


def handle_bracelet_emergency(alerts: List[Dict[str, Any]], data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle emergency alerts from bracelet.
    Returns emergency response actions.
    """
    device_id = data.get('device_id', 'unknown')
    user_id = data.get('user_id', 'unknown')
    
    emergency_response = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'device_id': device_id,
        'user_id': user_id,
        'alerts': alerts,
        'actions_taken': []
    }
    
    for alert in alerts:
        alert_type = alert['type']
        
        if alert_type == 'PANIC':
            # Panic protocol - ask user if they're okay
            emergency_response['actions_taken'].append(
                "Valyria entering emergency mode - asking user status"
            )
            # TODO: Trigger Valyria emergency conversation mode
            
        elif alert_type == 'FALL':
            # Fall protocol - immediate response needed
            emergency_response['actions_taken'].append(
                "Fall detected - initiating immediate response protocol"
            )
            # TODO: Start 30-second response timer
            
        elif alert_type == 'MEDICAL':
            # Medical emergency - assess severity
            severity = alert['severity']
            emergency_response['actions_taken'].append(
                f"Medical emergency detected - starting assessment (severity: {severity})"
            )
            # TODO: Trigger medical assessment conversation
    
    # Log emergency
    print(f"🚨 EMERGENCY RESPONSE: {emergency_response}")
    
    return emergency_response


# ============================================================================
# FASTAPI ENDPOINTS (Add these to main.py)
# ============================================================================

"""
ADD THESE ENDPOINTS TO YOUR main.py FILE:

from bracelet_endpoints import (
    process_bracelet_data,
    handle_bracelet_emergency,
    bracelet_data_store,
    user_baselines
)

@app.post("/bracelet/data")
async def receive_bracelet_data(data: Dict[str, Any]):
    '''Receive sensor data from bracelet'''
    try:
        # Validate required fields
        if not data or 'device_id' not in data or 'sensors' not in data:
            raise HTTPException(status_code=400, detail="Invalid data format")
        
        device_id = data['device_id']
        user_id = data.get('user_id', 'unknown')
        
        # Store the data
        bracelet_data_store[device_id] = {
            'last_update': datetime.utcnow(),
            'data': data
        }
        
        # Process for emergencies and energy state
        alerts, energy_state = process_bracelet_data(data)
        
        # Log the processing
        print(f"[Bracelet {device_id}] Energy state: {energy_state}")
        if alerts:
            print(f"[Bracelet {device_id}] ⚠️ ALERTS: {[a['type'] for a in alerts]}")
        
        response = {
            'status': 'received',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'energy_state': energy_state,
            'alerts_triggered': len(alerts)
        }
        
        # If there are alerts, trigger emergency response
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
        
        # Store registration (in production, use database)
        bracelet_data_store[device_id] = {
            'user_id': user_id,
            'serial_number': serial_number,
            'registered_at': datetime.utcnow().isoformat() + 'Z',
            'status': 'active',
            'last_update': None,
            'data': None
        }
        
        # Initialize user baseline if needed
        if user_id not in user_baselines:
            user_baselines[user_id] = {
                'resting_heart_rate': 70,  # Will be calibrated from actual data
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
    # TODO: Implement historical data retrieval from database
    # For now, return current data only
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
"""

# ============================================================================
# NOTES FOR INTEGRATION
# ============================================================================

"""
INTEGRATION STEPS:

1. Save this file as 'bracelet_endpoints.py' in your valyria_core/ folder

2. In main.py, add at the top:
   from bracelet_endpoints import (
       process_bracelet_data,
       handle_bracelet_emergency,
       bracelet_data_store,
       user_baselines
   )

3. Copy the 4 endpoint functions from the docstring above into main.py:
   - @app.post("/bracelet/data")
   - @app.post("/bracelet/register")
   - @app.get("/bracelet/status/{device_id}")
   - @app.get("/bracelet/history/{user_id}")

4. Restart your server:
   py -m uvicorn valyria_core.main:app --reload

5. Test with bracelet_simulator.py:
   python bracelet_simulator.py
   Select scenario 3 (panic attack)

6. Verify emergency detection works by checking terminal output
"""
