import time

# Simple in-memory dict for rate limiting
# Key: IP address, Value: [timestamp_first_request, request_count]
# Production apps should use Redis for this.
_rate_limits = {}

def check_rate_limit(ip: str, limit_per_hour: int) -> tuple:
    """
    Check if the given IP has exceeded the hourly download limit.
    Returns (is_allowed: bool, retry_after_seconds: int)
    """
    now = time.time()
    
    # Clean up old records periodically
    if random.random() < 0.05:
        _cleanup(now)
        
    if ip not in _rate_limits:
        _rate_limits[ip] = [now, 1]
        return True, 0
        
    first_request, count = _rate_limits[ip]
    
    # Reset if over an hour old
    if now - first_request > 3600:
        _rate_limits[ip] = [now, 1]
        return True, 0
        
    if count >= limit_per_hour:
        retry_after = 3600 - int(now - first_request)
        return False, retry_after
        
    _rate_limits[ip][1] += 1
    return True, 0

def _cleanup(now):
    global _rate_limits
    # Remove older than 1 hour
    _rate_limits = {ip: data for ip, data in _rate_limits.items() if now - data[0] <= 3600}
    
import random # For periodic cleanup probability
