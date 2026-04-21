from flask import Flask, request, session, jsonify
from dotenv import load_dotenv
import os
from datetime import timedelta
from database import get_db, init_db, close_connection
import jwt
from functools import wraps
from datetime import datetime, timedelta
import hashlib

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-change-this')
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', 'jwt-secret-key-change-this')

# WebAuthn configuration for localhost
# For production, replace with your actual domain
WEBAUTHN_RP_ID = os.getenv('WEBAUTHN_RP_ID', 'localhost')
WEBAUTHN_RP_NAME = os.getenv('WEBAUTHN_RP_NAME', 'Zoro Pay')
WEBAUTHN_ORIGIN = os.getenv('WEBAUTHN_ORIGIN', 'http://localhost:5000')

app.config['WEBAUTHN_RP_ID'] = WEBAUTHN_RP_ID
app.config['WEBAUTHN_RP_NAME'] = WEBAUTHN_RP_NAME
app.config['WEBAUTHN_ORIGIN'] = WEBAUTHN_ORIGIN

app.teardown_appcontext(close_connection)

# Import routes after app initialization to avoid circular imports
from auth import auth_bp
from routes import routes_bp
from admin import admin_bp

# Register blueprints
app.register_blueprint(auth_bp)           # Auth routes (login, OTP, etc.)
app.register_blueprint(routes_bp)         # Main app routes (dashboard, send, etc.)
app.register_blueprint(admin_bp)          # Admin routes (already has url_prefix='/admin' inside blueprint)

# JWT Token Functions
def generate_jwt_token(user_id, phone):
    """Generate JWT token for user"""
    payload = {
        'user_id': user_id,
        'phone': phone,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')

def verify_jwt_token(token):
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# API Key Middleware
def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id, phone, api_usage_count, last_api_used FROM users WHERE api_key = ? AND is_blocked = 0', (api_key,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'Invalid or inactive API key'}), 401
        
        # Update usage stats
        cursor.execute('''
            UPDATE users 
            SET api_usage_count = api_usage_count + 1, 
                last_api_used = ? 
            WHERE id = ?
        ''', (datetime.now(), user['id']))
        db.commit()
        
        request.user_id = user['id']
        return f(*args, **kwargs)
    
    decorated_function.__name__ = f.__name__
    return decorated_function

# Generate UPI ID
def generate_upi_id(name, phone):
    """Generate UPI ID from name and phone"""
    base_name = name.lower().replace(' ', '')
    upi_id = f"{base_name}@zoropay"
    return upi_id

# WebAuthn helper function to get RP ID based on request
def get_webauthn_rp_id():
    """Get the appropriate WebAuthn RP ID based on the request host"""
    host = request.host.split(':')[0]  # Remove port number
    # For localhost and 127.0.0.1, use 'localhost'
    if host in ['localhost', '127.0.0.1']:
        return 'localhost'
    return host

# Initialize database
init_db()

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 Zoro Pay Server Starting...")
    print("="*50)
    print(f"\n📍 Server URL: http://localhost:5000")
    print(f"📍 Alternative: http://127.0.0.1:5000")
    print(f"\n🔐 WebAuthn Configuration:")
    print(f"   - RP ID: {WEBAUTHN_RP_ID}")
    print(f"   - RP Name: {WEBAUTHN_RP_NAME}")
    print(f"   - Origin: {WEBAUTHN_ORIGIN}")
    print(f"\n📱 For biometric authentication to work:")
    print(f"   ✅ Use http://localhost:5000 (not 127.0.0.1)")
    print(f"   ✅ Chrome/Edge browser recommended")
    print(f"   ✅ Make sure device has fingerprint/face unlock enabled")
    print(f"\n🌐 Available routes:")
    print(f"   - Home: http://localhost:5000/")
    print(f"   - Settings: http://localhost:5000/settings")
    print(f"   - PIN Entry: http://localhost:5000/pin")
    print(f"   - Dashboard: http://localhost:5000/dashboard")
    print("\n" + "="*50)
    print("⚠️  Press CTRL+C to stop the server")
    print("="*50 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)