#!/usr/bin/env python3
"""
Configuration file for getproxy.py
Modify these settings to control proxy collection behavior
"""

# ===================== JSON ROTATOR SETTINGS =====================
# Set to True to completely skip getproxylist.com (prevents hanging)
SKIP_JSON_ROTATORS = True

# If you want to use JSON rotators, reduce these values to prevent hanging
GPL_REQUESTS_PER_PROTOCOL = 100        # Reduced from 400 to prevent hanging
GPL_LAST_TESTED_SEC = 900              # only proxies tested in last N seconds
GPL_MIN_UPTIME = 80                    # % uptime minimum (0-100)
GPL_MIN_DL_BPS = 1000                  # min download speed (bytes/sec)
GPL_MAX_CONNECT_S = 2                  # max connect time (seconds)
GPL_PER_REQUEST_SLEEP = 0.1            # Increased from 0.05 to be more polite
GPL_RETRIES = 2                        # Reduced from 3 to prevent hanging
GPL_BACKOFF_BASE = 1.0                 # Increased from 0.6 for better backoff

# ===================== SAFETY LIMITS =====================
# Maximum attempts per protocol to prevent infinite loops
MAX_ATTEMPTS_MULTIPLIER = 2            # Max attempts = GPL_REQUESTS_PER_PROTOCOL * this value
MAX_CONSECUTIVE_FAILURES = 5           # Stop if this many consecutive failures

# ===================== TIMEOUT SETTINGS =====================
# Maximum time for entire collection process (in seconds)
COLLECTION_TIMEOUT = 1800              # 30 minutes

# ===================== OTHER SETTINGS =====================
# GeoNode pagination controls
GEONODE_LIMIT_PER_PAGE = 500           # API maximum limit (not 1000)
GEONODE_MAX_PAGES = 25                 # 25 * 500 = 12,500 max (covers their 12,255 total)

# HTTP client defaults
REQUEST_TIMEOUT = 15                   # Increased from 10 for GeoNode API stability
