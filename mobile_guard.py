# mobile_guard.py
# Add this file to your project root directory

import os
from functools import wraps
from flask import request, render_template, session
from user_agents import parse

# Mobile user agent patterns for detection
MOBILE_PATTERNS = [
    'android', 'iphone', 'ipad', 'ipod', 'blackberry', 
    'windows phone', 'mobile', 'opera mini', 'opera mobi',
    'iemobile', 'webos', 'symbian', 'series60', 'symbianos'
]

def is_mobile_device(user_agent_string):
    """
    Check if the request is coming from a mobile device
    """
    if not user_agent_string:
        return False
    
    user_agent = user_agent_string.lower()
    
    # Check for mobile patterns
    for pattern in MOBILE_PATTERNS:
        if pattern in user_agent:
            return True
    
    # Use user_agents library for more accurate detection
    try:
        parsed_ua = parse(user_agent_string)
        return parsed_ua.is_mobile
    except:
        pass
    
    return False

def mobile_required(f):
    """
    Decorator to restrict access to mobile devices only
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip check for these specific routes (for testing/API)
        skip_routes = ['/api/', '/static/', '/manifest.json', '/service-worker.js', '/download-app']
        
        # Check if current path should skip mobile check
        for skip_route in skip_routes:
            if request.path.startswith(skip_route):
                return f(*args, **kwargs)
        
        # Check if user has already been warned or is on warning page
        if session.get('mobile_warning_shown') and request.path != '/mobile-required':
            return f(*args, **kwargs)
        
        # Check if it's a mobile device
        user_agent_string = request.headers.get('User-Agent', '')
        
        if not is_mobile_device(user_agent_string):
            # Not a mobile device - show warning page
            session['mobile_warning_shown'] = False
            return render_template('mobile_required.html'), 403
        
        # It's a mobile device, allow access
        session['mobile_warning_shown'] = True
        return f(*args, **kwargs)
    
    return decorated_function

def init_mobile_guard(app):
    """
    Initialize mobile guard for the Flask app
    Apply to all routes except those specified
    """
    
    # Store original route mappings
    original_routes = {}
    
    for rule in app.url_map.iter_rules():
        if rule.endpoint not in ['static', 'routes.static']:
            original_routes[rule.endpoint] = app.view_functions[rule.endpoint]
    
    # Apply mobile_required decorator to all routes
    for endpoint, view_func in original_routes.items():
        if endpoint.startswith('routes.'):
            decorated_func = mobile_required(view_func)
            app.view_functions[endpoint] = decorated_func
    
    print("✓ Mobile guard initialized - Desktop access blocked")
    
    return app

# For direct integration - add this to your main app initialization
def setup_mobile_guard(app):
    """
    Setup mobile guard for the Flask application
    """
    
    # Add the mobile_required decorator to routes blueprint routes
    from routes import routes_bp
    
    # Store original view functions
    original_views = {}
    
    for rule in routes_bp.url_map.iter_rules():
        if rule.endpoint != 'routes.static' and not rule.endpoint.startswith('api'):
            original_views[rule.endpoint] = routes_bp.view_functions[rule.endpoint]
    
    # Replace with decorated versions
    for endpoint, view_func in original_views.items():
        decorated_func = mobile_required(view_func)
        routes_bp.view_functions[endpoint] = decorated_func
    
    return app