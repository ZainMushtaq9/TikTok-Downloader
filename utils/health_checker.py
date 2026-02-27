import threading
import time

# Simple mock health checker since we don't have a background worker yet
PLATFORM_HEALTH = {
    'youtube': 'ok',
    'tiktok': 'ok',
    'instagram': 'ok',
    'facebook': 'ok',
    'twitter': 'ok'
}

def get_platform_health():
    return PLATFORM_HEALTH

# In a full production scenario, a background thread would test urls for each platform
# and update this dict.
