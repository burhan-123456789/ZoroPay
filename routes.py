from flask import Blueprint, request, jsonify, send_from_directory, session, send_file, render_template
from database import get_db
import random
from datetime import datetime, timedelta
import qrcode
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
import re
import string
import jwt
from functools import wraps
from user_agents import parse
from datetime import date
from mobile_guard import mobile_required

routes_bp = Blueprint('routes', __name__)

JWT_SECRET = os.getenv('JWT_SECRET', 'your-jwt-secret-key-change-this')
DAILY_LIMIT = 50000
FRAUD_THRESHOLD = 5
FRAUD_TIME_WINDOW = 60  # seconds

# Ensure directories exist
os.makedirs('static/qr', exist_ok=True)
os.makedirs('static/receipts', exist_ok=True)

# ====================
# AUTH DECORATORS
# ====================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token and 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        
        if token:
            if token.startswith('Bearer '):
                token = token[7:]
            try:
                data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
                request.user_id = data['user_id']
                return f(*args, **kwargs)
            except jwt.ExpiredSignatureError:
                return jsonify({'error': 'Token has expired'}), 401
            except jwt.InvalidTokenError:
                pass
        
        if 'user_id' in session:
            request.user_id = session['user_id']
            return f(*args, **kwargs)
        
        return jsonify({'error': 'Authentication required'}), 401
    return decorated

def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def api_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({'error': 'API key is required'}), 401
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id, api_usage_count, last_api_used FROM users WHERE api_key = ? AND is_blocked = 0', (api_key,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401
        
        cursor.execute('''
            UPDATE users SET 
                api_usage_count = api_usage_count + 1,
                last_api_used = ?
            WHERE id = ?
        ''', (datetime.now(), user['id']))
        db.commit()
        
        request.api_user_id = user['id']
        
        return f(*args, **kwargs)
    return decorated

# ====================
# HELPER FUNCTIONS
# ====================

def check_daily_limit(user_id, amount):
    """Check if transaction exceeds daily limit"""
    db = get_db()
    cursor = db.cursor()
    
    today = date.today().isoformat()
    
    cursor.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE sender_id = ? AND date(created_at) = date(?)
        AND status = 'success'
    ''', (user_id, today))
    
    result = cursor.fetchone()
    total_sent_today = result['total'] or 0
    
    if total_sent_today + amount > DAILY_LIMIT:
        return False, total_sent_today
    
    return True, total_sent_today

def check_fraud(user_id):
    """Check for suspicious transaction patterns"""
    db = get_db()
    cursor = db.cursor()
    
    time_threshold = datetime.now() - timedelta(seconds=FRAUD_TIME_WINDOW)
    
    cursor.execute('''
        SELECT COUNT(*) as count FROM transactions 
        WHERE sender_id = ? AND created_at > ?
        AND status = 'success'
    ''', (user_id, time_threshold))
    
    result = cursor.fetchone()
    
    if result['count'] >= FRAUD_THRESHOLD:
        cursor.execute('''
            INSERT INTO fraud_logs (user_id, fraud_type, description)
            VALUES (?, ?, ?)
        ''', (user_id, 'rapid_transactions', f'{result["count"]} transactions in {FRAUD_TIME_WINDOW} seconds'))
        db.commit()
        return True
    
    return False

def log_fraud(user_id, fraud_type, description):
    """Log fraud attempt"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        INSERT INTO fraud_logs (user_id, fraud_type, description)
        VALUES (?, ?, ?)
    ''', (user_id, fraud_type, description))
    db.commit()

def add_cashback(user_id, amount):
    """Add cashback based on transaction amount (stores as pending, not auto-added to wallet)"""
    from database import add_cashback as db_add_cashback
    cashback_amount, percentage = db_add_cashback(user_id, amount)
    
    if cashback_amount > 0:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT phone FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if user:
            sms_message = f"Zoro Pay: You earned {format_currency(cashback_amount)} cashback ({percentage:.1f}%) on your transaction! Slide to claim in Cashback Vault."
            send_sms_notification(user['phone'], sms_message)
        
        return cashback_amount
    
    return 0

def send_sms_notification(phone, message):
    """Send SMS notification using Twilio"""
    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
        
        TWILIO_SID = os.getenv('TWILIO_SID')
        TWILIO_AUTH = os.getenv('TWILIO_AUTH')
        TWILIO_PHONE = os.getenv('TWILIO_PHONE')
        
        REGION = 'us1'
        USE_MOCK_OTP = os.getenv('USE_MOCK_OTP', 'False').lower() == 'true'
        
        if USE_MOCK_OTP:
            print(f"\n📱=== MOCK SMS TO {phone} ===📱")
            print(message)
            print("================================\n")
            return True
        elif TWILIO_SID and TWILIO_AUTH and TWILIO_PHONE:
            client = Client(TWILIO_SID, TWILIO_AUTH, region=REGION)
            
            if not phone.startswith('+'):
                phone = '+' + phone
            
            if len(message) > 1600:
                message = message[:1597] + "..."
            
            message_obj = client.messages.create(
                body=message,
                from_=TWILIO_PHONE,
                to=phone
            )
            print(f"✅ SMS sent successfully to {phone}, SID: {message_obj.sid}")
            return True
        else:
            print(f"⚠️ SMS not sent - Twilio credentials not configured")
            return False
    except TwilioRestException as e:
        print(f"❌ Twilio Error: {e.code} - {e.msg}")
        return False
    except Exception as e:
        print(f"❌ Error sending SMS: {e}")
        return False

def format_currency(amount):
    return f"₹{amount:.2f}"

def generate_transaction_id():
    return ''.join(str(random.randint(0, 9)) for _ in range(10))

def generate_referral_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def generate_download_qr():
    """Generate QR code for app download"""
    # Get the base URL for download
    base_url = request.host_url.rstrip('/')
    download_url = f"{base_url}/download-app"
    
    # Create QR code directory
    qr_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'qr')
    os.makedirs(qr_dir, exist_ok=True)
    
    qr_path = os.path.join(qr_dir, 'download_app.png')
    qr_url = '/static/qr/download_app.png'
    
    # Generate QR code if it doesn't exist
    if not os.path.exists(qr_path):
        qr = qrcode.QRCode(
            version=5,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(download_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="#4F46E5", back_color="white")
        img.save(qr_path)
    
    return qr_url, download_url

@routes_bp.route('/manifest.json')
def serve_manifest():
    """Serve the web app manifest"""
    return send_file('static/manifest.json', mimetype='application/manifest+json')

@routes_bp.route('/service-worker.js')
def serve_service_worker():
    """Serve the service worker"""
    return send_file('static/service-worker.js', mimetype='application/javascript')

@routes_bp.route('/static/<path:filename>')
def serve_static_files(filename):
    """Serve static files with proper caching headers"""
    response = send_from_directory('static', filename)
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

# ====================
# PAGE ROUTES (with mobile protection)
# ====================

@routes_bp.route('/')
@mobile_required
def index():
    user_id = session.get('user_id')
    
    if not user_id:
        return render_template('login.html')
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT pin FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        session.clear()
        return render_template('login.html')
    
    if user['pin'] == '1234' or user['pin'] is None or user['pin'] == '':
        return render_template('setup_pin.html')
    
    return render_template('dashboard.html')

@routes_bp.route('/dashboard')
@mobile_required
def dashboard():
    user_id = session.get('user_id')
    
    if not user_id:
        return render_template('login.html')
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT pin FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        session.clear()
        return render_template('login.html')
    
    if user['pin'] == '1234' or user['pin'] is None or user['pin'] == '':
        return render_template('setup_pin.html')
    
    return render_template('dashboard.html')

@routes_bp.route('/send')
@login_required
@mobile_required
def send_page():
    return render_template('send.html')

@routes_bp.route('/analytics')
@login_required
@mobile_required
def analytics_page():
    return render_template('analytics.html')

@routes_bp.route('/all-transactions')
@login_required
@mobile_required
def all_transactions_page():
    return render_template('all_transactions.html')

@routes_bp.route('/transaction-history/<identifier>')
@login_required
@mobile_required
def transaction_history_page(identifier):
    db = get_db()
    cursor = db.cursor()
    
    other_user = None
    is_in_contacts = False
    contact_name = None
    contact_id = None
    
    if identifier.isdigit():
        cursor.execute('SELECT id, name, phone FROM users WHERE id = ?', (identifier,))
        row = cursor.fetchone()
        if row:
            other_user = dict(row)
            
            cursor.execute('''
                SELECT id, contact_name FROM contacts 
                WHERE user_id = ? AND contact_phone = ?
            ''', (session['user_id'], other_user['phone']))
            contact = cursor.fetchone()
            if contact:
                is_in_contacts = True
                contact_name = contact['contact_name']
                contact_id = contact['id']
    else:
        phone = identifier
        cursor.execute('SELECT id, name, phone FROM users WHERE phone = ?', (phone,))
        row = cursor.fetchone()
        if row:
            other_user = dict(row)
        
        cursor.execute('''
            SELECT id, contact_name FROM contacts 
            WHERE user_id = ? AND contact_phone = ?
        ''', (session['user_id'], phone))
        contact = cursor.fetchone()
        if contact:
            is_in_contacts = True
            contact_name = contact['contact_name']
            contact_id = contact['id']
        
        if not other_user:
            other_user = {
                'id': None,
                'phone': phone,
                'name': contact_name if contact_name else phone
            }
    
    if not other_user:
        return render_template('dashboard.html')
    
    return render_template('transaction_history.html', 
                         other_user=other_user,
                         other_user_id=other_user.get('id'),
                         is_external=other_user.get('id') is None,
                         is_in_contacts=is_in_contacts,
                         contact_name=contact_name,
                         contact_id=contact_id)

@routes_bp.route('/contacts-page')
@login_required
@mobile_required
def contacts_page():
    return render_template('contacts.html')

@routes_bp.route('/add-balance')
@login_required
@mobile_required
def add_balance_page():
    return render_template('add_balance.html')

@routes_bp.route('/setup-pin')
@login_required
@mobile_required
def setup_pin_page():
    return render_template('setup_pin.html')

@routes_bp.route('/verify-pin')
@login_required
@mobile_required
def verify_pin_page():
    return render_template('verify_pin.html')

@routes_bp.route('/profile')
@login_required
@mobile_required
def profile_page():
    return render_template('profile.html')

@routes_bp.route('/settings')
@login_required
@mobile_required
def settings_page():
    return render_template('settings.html')

@routes_bp.route('/receipt/<transaction_id>')
@login_required
@mobile_required
def receipt_page(transaction_id):
    return render_template('receipt.html', transaction_id=transaction_id)

@routes_bp.route('/cashback')
@login_required
@mobile_required
def cashback_page():
    return render_template('cashback.html')

@routes_bp.route('/success')
@login_required
@mobile_required
def success_page():
    return render_template('success.html')
    
@routes_bp.route('/pin')
@mobile_required
def pin_page():
    return render_template('pin.html')

@routes_bp.route('/mobile-required')
def mobile_required_page():
    """Show mobile required warning page"""
    return render_template('mobile_required.html'), 403

@routes_bp.route('/download-app')
@mobile_required
def download_app():
    """Redirect to mobile app download or show QR code"""
    return render_template('login.html')

# ====================
# API ENDPOINTS - REFERRAL
# ====================

@routes_bp.route('/api/validate_referral_code', methods=['POST'])
def validate_referral_code():
    """Validate a referral code"""
    data = request.get_json()
    referral_code = data.get('referral_code', '').strip().upper()
    
    if not referral_code:
        return jsonify({'valid': False, 'error': 'Referral code is required'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT id, name, phone FROM users WHERE referral_code = ? AND is_blocked = 0', (referral_code,))
    referrer = cursor.fetchone()
    
    if referrer:
        return jsonify({
            'valid': True,
            'message': f'Referral code from {referrer["name"]}! You will get ₹250 bonus!',
            'referrer_name': referrer['name']
        }), 200
    else:
        return jsonify({'valid': False, 'error': 'Invalid referral code'}), 404

@routes_bp.route('/api/apply_referral', methods=['POST'])
def apply_referral():
    """Apply referral code to a new user"""
    data = request.get_json()
    user_id = data.get('user_id')
    referral_code = data.get('referral_code', '').strip().upper()
    
    if not user_id:
        return jsonify({'error': 'User ID required'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT id, phone, name, wallet_balance, referral_code, referred_by FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user['referred_by']:
        return jsonify({'error': 'Referral code already applied'}), 400
    
    bonus_amount = 0
    referrer_bonus = 0
    
    if referral_code:
        cursor.execute('SELECT id, name, phone, wallet_balance FROM users WHERE referral_code = ? AND is_blocked = 0', (referral_code,))
        referrer = cursor.fetchone()
        
        if referrer and referrer['id'] != user_id:
            cursor.execute('UPDATE users SET referred_by = ? WHERE id = ?', (referral_code, user_id))
            
            bonus_amount = 250
            cursor.execute('UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?', (bonus_amount, user_id))
            
            referrer_bonus = 250
            cursor.execute('UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?', (referrer_bonus, referrer['id']))
            
            transaction_id = generate_transaction_id()
            cursor.execute('''
                INSERT INTO transactions (id, sender_id, receiver_id, amount, note, status, receiver_phone, sender_phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (transaction_id, None, user_id, bonus_amount, f'Welcome bonus from referral code {referral_code}', 'success', user['phone'], None))
            
            referrer_transaction_id = generate_transaction_id()
            cursor.execute('''
                INSERT INTO transactions (id, sender_id, receiver_id, amount, note, status, receiver_phone, sender_phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (referrer_transaction_id, None, referrer['id'], referrer_bonus, f'Referral bonus for inviting new user', 'success', referrer['phone'], None))
            
            db.commit()
            
            send_sms_notification(user['phone'], f"🎉 Zoro Pay: Welcome! ₹{bonus_amount} bonus added to your wallet. Start transacting now!")
            send_sms_notification(referrer['phone'], f"🎉 Zoro Pay: You earned ₹{referrer_bonus} referral bonus! {user['name']} joined using your code.")
            
            cursor.execute('SELECT wallet_balance FROM users WHERE id = ?', (user_id,))
            updated_user = cursor.fetchone()
            
            return jsonify({
                'message': f'Referral code applied successfully! ₹{bonus_amount} bonus added!',
                'bonus_amount': bonus_amount,
                'user': {
                    'id': user['id'],
                    'phone': user['phone'],
                    'name': user['name'],
                    'balance': float(updated_user['wallet_balance']) if updated_user else float(user['wallet_balance']) + bonus_amount,
                    'referral_code': user['referral_code']
                }
            }), 200
    
    bonus_amount = 100
    cursor.execute('UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?', (bonus_amount, user_id))
    
    transaction_id = generate_transaction_id()
    cursor.execute('''
        INSERT INTO transactions (id, sender_id, receiver_id, amount, note, status, receiver_phone, sender_phone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (transaction_id, None, user_id, bonus_amount, 'Welcome bonus', 'success', user['phone'], None))
    
    db.commit()
    
    send_sms_notification(user['phone'], f"🎉 Zoro Pay: Welcome! ₹{bonus_amount} bonus added to your wallet. Start transacting now!")
    
    cursor.execute('SELECT wallet_balance FROM users WHERE id = ?', (user_id,))
    updated_user = cursor.fetchone()
    
    return jsonify({
        'message': f'Account created successfully! ₹{bonus_amount} bonus added!',
        'bonus_amount': bonus_amount,
        'user': {
            'id': user['id'],
            'phone': user['phone'],
            'name': user['name'],
            'balance': float(updated_user['wallet_balance']) if updated_user else float(user['wallet_balance']) + bonus_amount,
            'referral_code': user['referral_code']
        }
    }), 200

# ====================
# API ENDPOINTS - USER
# ====================

@routes_bp.route('/api/user')
@login_required
def get_user():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id, phone, name, wallet_balance, referral_code, pin, upi_id, api_key, is_blocked, cashback_earned, api_usage_count, last_api_used, referred_by FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user['is_blocked']:
            session.clear()
            return jsonify({'error': 'Your account has been blocked'}), 403
        
        return jsonify({
            'id': user['id'],
            'phone': user['phone'],
            'name': user['name'] if user['name'] else 'User',
            'balance': float(user['wallet_balance']) if user['wallet_balance'] else 0,
            'referral_code': user['referral_code'],
            'upi_id': user['upi_id'],
            'api_key': user['api_key'],
            'has_pin_setup': user['pin'] != '1234' if user['pin'] else False,
            'cashback_earned': float(user['cashback_earned']) if user['cashback_earned'] else 0,
            'api_usage_count': user['api_usage_count'] or 0,
            'last_api_used': user['last_api_used'],
            'referred_by': user['referred_by']
        })
    except Exception as e:
        print(f"Error in get_user: {e}")
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/check_user_exists', methods=['POST'])
def check_user_exists():
    data = request.get_json()
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if not phone.startswith('+'):
        if len(phone) == 10:
            phone = '+91' + phone
        else:
            phone = '+' + phone
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, name, phone, pin FROM users WHERE phone = ?', (phone,))
    user = cursor.fetchone()
    
    if user:
        pin_length = len(user['pin']) if user['pin'] else 4
        return jsonify({
            'exists': True,
            'user': {
                'id': user['id'],
                'name': user['name'] if user['name'] else 'User',
                'phone': user['phone']
            },
            'pin_length': pin_length
        }), 200
    else:
        return jsonify({'exists': False}), 200

@routes_bp.route('/api/get_user_by_phone', methods=['POST'])
def get_user_by_phone():
    data = request.get_json()
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if not phone.startswith('+'):
        if len(phone) == 10:
            phone = '+91' + phone
        else:
            phone = '+' + phone
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, name, phone, pin FROM users WHERE phone = ?', (phone,))
    user = cursor.fetchone()
    
    if user:
        pin_length = len(user['pin']) if user['pin'] else 4
        return jsonify({
            'user': {
                'id': user['id'],
                'name': user['name'] if user['name'] else 'User',
                'phone': user['phone']
            },
            'pin_length': pin_length
        }), 200
    else:
        return jsonify({'error': 'User not found'}), 404

@routes_bp.route('/api/verify_pin', methods=['POST'])
def verify_pin():
    data = request.get_json()
    phone = data.get('phone')
    pin = data.get('pin')
    
    if not phone or not pin:
        return jsonify({'error': 'Phone and PIN required'}), 400
    
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if not phone.startswith('+'):
        if len(phone) == 10:
            phone = '+91' + phone
        else:
            phone = '+' + phone
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, name, phone, pin, wallet_balance, referral_code, upi_id, is_blocked FROM users WHERE phone = ?', (phone,))
    user = cursor.fetchone()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user['is_blocked']:
        return jsonify({'error': 'Your account has been blocked'}), 403
    
    if user['pin'] != pin:
        return jsonify({'error': 'Invalid PIN'}), 400
    
    token = jwt.encode({
        'user_id': user['id'],
        'phone': phone,
        'exp': datetime.now() + timedelta(days=7)
    }, JWT_SECRET, algorithm='HS256')
    
    session['user_id'] = user['id']
    session['phone'] = phone
    session.permanent = True
    
    return jsonify({
        'message': 'Login successful',
        'token': token,
        'user': {
            'id': user['id'],
            'phone': user['phone'],
            'name': user['name'],
            'balance': float(user['wallet_balance']) if user['wallet_balance'] else 0,
            'referral_code': user['referral_code'],
            'upi_id': user['upi_id']
        }
    }), 200

@routes_bp.route('/api/check_user/<path:phone>')
@login_required
def check_user(phone):
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if not phone.startswith('+'):
        phone = '+' + phone
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, name FROM users WHERE phone = ?', (phone,))
    user = cursor.fetchone()
    
    return jsonify({
        'exists': bool(user),
        'name': user['name'] if user else None
    })

@routes_bp.route('/api/update_name', methods=['POST'])
@login_required
def update_name():
    data = request.get_json()
    new_name = data.get('name')
    
    if not new_name:
        return jsonify({'error': 'Name required'}), 400
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('UPDATE users SET name = ? WHERE id = ?', (new_name, session['user_id']))
    
    # Also update virtual card holder name if exists
    cursor.execute('''
        UPDATE virtual_cards 
        SET card_holder_name = ? 
        WHERE user_id = ? AND is_active = 1
    ''', (new_name, session['user_id']))
    
    db.commit()
    
    return jsonify({'message': '✅ Name updated successfully!'})

@routes_bp.route('/api/change_pin', methods=['POST'])
@login_required
def change_pin():
    data = request.get_json()
    old_pin = data.get('old_pin')
    new_pin = data.get('new_pin')
    
    if not old_pin or not new_pin:
        return jsonify({'error': 'Both old and new PIN required'}), 400
    
    if len(new_pin) not in [4, 6] or not new_pin.isdigit():
        return jsonify({'error': 'PIN must be 4 or 6 digits'}), 400
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT pin, phone, name FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user['pin'] != old_pin:
        return jsonify({'error': 'Invalid current PIN'}), 400
    
    cursor.execute('UPDATE users SET pin = ? WHERE id = ?', (new_pin, session['user_id']))
    db.commit()
    
    sms_message = f"Zoro Pay: Your {'4' if len(new_pin) == 4 else '6'}-digit PIN has been changed successfully."
    send_sms_notification(user['phone'], sms_message)
    
    return jsonify({'message': f'🔐 PIN changed successfully!'}), 200

@routes_bp.route('/api/setup_pin', methods=['POST'])
@login_required
def setup_pin():
    data = request.get_json()
    pin = data.get('pin')
    pin_type = data.get('pin_type', '4')
    
    if not pin:
        return jsonify({'error': 'PIN required'}), 400
    
    if pin_type == '4' and (len(pin) != 4 or not pin.isdigit()):
        return jsonify({'error': 'PIN must be 4 digits'}), 400
    elif pin_type == '6' and (len(pin) != 6 or not pin.isdigit()):
        return jsonify({'error': 'PIN must be 6 digits'}), 400
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('UPDATE users SET pin = ? WHERE id = ?', (pin, session['user_id']))
    db.commit()
    
    return jsonify({'message': f'{pin_type}-digit PIN setup successfully'}), 200

@routes_bp.route('/api/check_pin_setup')
@login_required
def check_pin_setup():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT pin FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'needs_setup': True, 'error': 'User not found'}), 200
        
        needs_setup = (user['pin'] == '1234' or user['pin'] is None or user['pin'] == '')
        return jsonify({'needs_setup': needs_setup})
    except Exception as e:
        print(f"Error in check_pin_setup: {e}")
        return jsonify({'needs_setup': True}), 200

@routes_bp.route('/api/user_pin_length')
@login_required
def get_user_pin_length():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT pin FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        
        if user and user['pin']:
            pin_length = len(user['pin'])
            return jsonify({'pin_length': pin_length})
        else:
            return jsonify({'pin_length': 4})
    except Exception as e:
        print(f"Error getting PIN length: {e}")
        return jsonify({'pin_length': 4}), 200

@routes_bp.route('/api/referral_stats')
@login_required
def get_referral_stats():
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT referral_code FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM users 
            WHERE referred_by = ? AND is_blocked = 0
        ''', (user['referral_code'],))
        
        referral_count = cursor.fetchone()
        count = referral_count['count'] if referral_count else 0
        
        referral_bonus = count * 50
        
        return jsonify({
            'referral_code': user['referral_code'],
            'referral_count': count,
            'referral_bonus': referral_bonus,
            'message': f'You have referred {count} friend{"s" if count != 1 else ""}'
        }), 200
        
    except Exception as e:
        print(f"Error in get_referral_stats: {e}")
        return jsonify({
            'referral_code': '',
            'referral_count': 0,
            'referral_bonus': 0,
            'error': str(e)
        }), 200

@routes_bp.route('/api/generate_api_key', methods=['POST'])
@login_required
def generate_api_key():
    import hashlib
    from datetime import datetime
    import random
    
    db = get_db()
    cursor = db.cursor()
    
    new_api_key = hashlib.md5(f"{datetime.now()}{random.random()}{session['user_id']}".encode()).hexdigest()
    
    cursor.execute('UPDATE users SET api_key = ? WHERE id = ?', (new_api_key, session['user_id']))
    db.commit()
    
    return jsonify({
        'api_key': new_api_key,
        'message': 'API key generated successfully'
    }), 200

# ====================
# API ENDPOINTS - QR CODE
# ====================

@routes_bp.route('/api/generate_download_qr', methods=['GET'])
def generate_download_qr_api():
    """Generate QR code for app download - API endpoint"""
    qr_url, download_url = generate_download_qr()
    return jsonify({
        'qr_url': qr_url,
        'download_url': download_url
    })

@routes_bp.route('/api/generate_qr')
@login_required
def generate_qr():
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT upi_id, name FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    qr_data = f"upi://pay?pa={user['upi_id']}&pn={user['name']}&cu=INR"
    
    qr_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'qr')
    os.makedirs(qr_dir, exist_ok=True)
    
    qr_path = os.path.join(qr_dir, f'user_{user_id}.png')
    qr_url = f'/static/qr/user_{user_id}.png'
    
    qr = qrcode.QRCode(
        version=3,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="#4F46E5", back_color="white")
    img.save(qr_path)
    
    return jsonify({
        'qr_url': qr_url,
        'qr_data': qr_data,
        'upi_id': user['upi_id'],
        'user_name': user['name']
    })

# ====================
# API ENDPOINTS - TRANSACTIONS
# ====================

@routes_bp.route('/api/transactions', methods=['GET'])
@login_required
def get_transactions():
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT phone FROM users WHERE id = ?', (session['user_id'],))
        current_user = cursor.fetchone()
        current_user_phone = current_user['phone'] if current_user else None
        
        cursor.execute('''
            SELECT t.*, 
                   u1.name as sender_name, u1.phone as sender_phone,
                   u2.name as receiver_name, u2.phone as receiver_phone
            FROM transactions t
            LEFT JOIN users u1 ON t.sender_id = u1.id
            LEFT JOIN users u2 ON t.receiver_id = u2.id
            WHERE t.sender_id = ? 
               OR t.receiver_id = ? 
               OR t.sender_phone = ? 
               OR t.receiver_phone = ?
            ORDER BY t.created_at DESC
            LIMIT 100
        ''', (session['user_id'], session['user_id'], current_user_phone, current_user_phone))
        
        transactions = []
        for row in cursor.fetchall():
            is_sent = False
            if row['sender_id'] == session['user_id']:
                is_sent = True
            elif row['sender_phone'] and row['sender_phone'] == current_user_phone:
                is_sent = True
            
            if is_sent:
                counterparty_name = row['receiver_name'] if row['receiver_name'] else row['receiver_phone']
                counterparty_phone = row['receiver_phone']
            else:
                counterparty_name = row['sender_name'] if row['sender_name'] else row['sender_phone']
                counterparty_phone = row['sender_phone']
            
            if not counterparty_name or counterparty_name == 'null' or counterparty_name == 'External User':
                counterparty_name = counterparty_phone
            
            transactions.append({
                'id': row['id'],
                'amount': float(row['amount']),
                'note': row['note'] if row['note'] else '',
                'status': row['status'] if row['status'] else 'success',
                'created_at': row['created_at'],
                'sender_name': row['sender_name'] if row['sender_name'] else row['sender_phone'],
                'receiver_name': row['receiver_name'] if row['receiver_name'] else row['receiver_phone'],
                'sender_phone': row['sender_phone'],
                'receiver_phone': row['receiver_phone'],
                'sender_id': row['sender_id'],
                'receiver_id': row['receiver_id'],
                'is_sent': is_sent,
                'counterparty_name': counterparty_name,
                'counterparty_phone': counterparty_phone
            })
        
        return jsonify(transactions)
        
    except Exception as e:
        print(f"Error in get_transactions: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([])

@routes_bp.route('/api/transactions/with/<identifier>')
@login_required
def get_transactions_with_user(identifier):
    try:
        db = get_db()
        cursor = db.cursor()
        
        user_id = session['user_id']
        
        cursor.execute('SELECT phone FROM users WHERE id = ?', (user_id,))
        current_user = cursor.fetchone()
        current_user_phone = current_user['phone'] if current_user else None
        
        other_user_id = None
        other_user_phone = identifier
        
        if identifier.isdigit():
            other_user_id = int(identifier)
            cursor.execute('SELECT phone FROM users WHERE id = ?', (other_user_id,))
            user_result = cursor.fetchone()
            if user_result:
                other_user_phone = user_result['phone']
        
        cursor.execute('''
            SELECT t.*, 
                   u1.name as sender_name, u1.phone as sender_phone,
                   u2.name as receiver_name, u2.phone as receiver_phone
            FROM transactions t
            LEFT JOIN users u1 ON t.sender_id = u1.id
            LEFT JOIN users u2 ON t.receiver_id = u2.id
            WHERE ((t.sender_id = ? AND (t.receiver_id = ? OR t.receiver_phone = ?))
               OR (t.receiver_id = ? AND (t.sender_id = ? OR t.sender_phone = ?))
               OR (t.sender_phone = ? AND (t.receiver_id = ? OR t.receiver_phone = ?))
               OR (t.receiver_phone = ? AND (t.sender_id = ? OR t.sender_phone = ?)))
            ORDER BY t.created_at DESC
            LIMIT 100
        ''', (user_id, other_user_id, other_user_phone,
              user_id, other_user_id, other_user_phone,
              current_user_phone, other_user_id, other_user_phone,
              current_user_phone, other_user_id, other_user_phone))
        
        transactions = []
        for row in cursor.fetchall():
            is_sent = False
            if row['sender_id'] == user_id:
                is_sent = True
            elif row['sender_phone'] and row['sender_phone'] == current_user_phone:
                is_sent = True
            
            counterparty_name = None
            counterparty_phone = None
            
            if is_sent:
                counterparty_name = row['receiver_name'] if row['receiver_name'] else row['receiver_phone']
                counterparty_phone = row['receiver_phone']
            else:
                counterparty_name = row['sender_name'] if row['sender_name'] else row['sender_phone']
                counterparty_phone = row['sender_phone']
            
            if not counterparty_name or counterparty_name == 'null' or counterparty_name == 'External User':
                counterparty_name = counterparty_phone
            
            transactions.append({
                'id': row['id'],
                'amount': float(row['amount']),
                'note': row['note'] if row['note'] else '',
                'status': row['status'] if row['status'] else 'success',
                'created_at': row['created_at'],
                'sender_name': row['sender_name'] if row['sender_name'] else row['sender_phone'],
                'receiver_name': row['receiver_name'] if row['receiver_name'] else row['receiver_phone'],
                'is_sent': is_sent,
                'counterparty_name': counterparty_name,
                'counterparty_phone': counterparty_phone
            })
        
        return jsonify(transactions)
        
    except Exception as e:
        print(f"Error in get_transactions_with_user: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([])

@routes_bp.route('/api/transaction_summary/<identifier>')
@login_required
def get_transaction_summary(identifier):
    try:
        db = get_db()
        cursor = db.cursor()
        
        user_id = session['user_id']
        
        cursor.execute('SELECT phone FROM users WHERE id = ?', (user_id,))
        current_user = cursor.fetchone()
        current_user_phone = current_user['phone'] if current_user else None
        
        other_user_id = None
        other_user_phone = identifier
        
        if identifier.isdigit():
            other_user_id = int(identifier)
            cursor.execute('SELECT phone FROM users WHERE id = ?', (other_user_id,))
            user_result = cursor.fetchone()
            if user_result:
                other_user_phone = user_result['phone']
        
        cursor.execute('''
            SELECT SUM(amount) as total
            FROM transactions
            WHERE ((sender_id = ? AND (receiver_id = ? OR receiver_phone = ?))
               OR (sender_phone = ? AND (receiver_id = ? OR receiver_phone = ?)))
            AND status = 'success'
        ''', (user_id, other_user_id, other_user_phone,
              current_user_phone, other_user_id, other_user_phone))
        
        sent_result = cursor.fetchone()
        total_sent = float(sent_result['total'] or 0)
        
        cursor.execute('''
            SELECT SUM(amount) as total
            FROM transactions
            WHERE ((receiver_id = ? AND (sender_id = ? OR sender_phone = ?))
               OR (receiver_phone = ? AND (sender_id = ? OR sender_phone = ?)))
            AND status = 'success'
        ''', (user_id, other_user_id, other_user_phone,
              current_user_phone, other_user_id, other_user_phone))
        
        received_result = cursor.fetchone()
        total_received = float(received_result['total'] or 0)
        
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM transactions
            WHERE ((sender_id = ? AND (receiver_id = ? OR receiver_phone = ?))
               OR (receiver_id = ? AND (sender_id = ? OR sender_phone = ?))
               OR (sender_phone = ? AND (receiver_id = ? OR receiver_phone = ?))
               OR (receiver_phone = ? AND (sender_id = ? OR sender_phone = ?)))
            AND status = 'success'
        ''', (user_id, other_user_id, other_user_phone,
              user_id, other_user_id, other_user_phone,
              current_user_phone, other_user_id, other_user_phone,
              current_user_phone, other_user_id, other_user_phone))
        
        count_result = cursor.fetchone()
        transaction_count = count_result['count'] or 0
        
        return jsonify({
            'total_sent': total_sent,
            'total_received': total_received,
            'transaction_count': transaction_count
        })
    except Exception as e:
        print(f"Error in get_transaction_summary: {e}")
        return jsonify({'total_sent': 0, 'total_received': 0, 'transaction_count': 0})

@routes_bp.route('/api/transaction/<transaction_id>')
@login_required
def get_transaction_details(transaction_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT t.*, 
               u1.name as sender_name, u1.phone as sender_phone,
               u2.name as receiver_name, u2.phone as receiver_phone
        FROM transactions t
        LEFT JOIN users u1 ON t.sender_id = u1.id
        LEFT JOIN users u2 ON t.receiver_id = u2.id
        WHERE t.id = ? AND (t.sender_id = ? OR t.receiver_id = ? OR t.sender_id IS NULL OR t.receiver_id IS NULL)
    ''', (transaction_id, session['user_id'], session['user_id']))
    
    transaction = cursor.fetchone()
    if not transaction:
        return jsonify({'error': 'Transaction not found'}), 404
    
    return jsonify({
        'id': transaction['id'],
        'amount': float(transaction['amount']),
        'note': transaction['note'],
        'status': transaction['status'],
        'created_at': transaction['created_at'],
        'sender_name': transaction['sender_name'],
        'sender_phone': transaction['sender_phone'],
        'receiver_name': transaction['receiver_name'],
        'receiver_phone': transaction['receiver_phone']
    })

@routes_bp.route('/api/download_receipt/<transaction_id>')
@login_required
def download_receipt(transaction_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT t.*, 
               u1.name as sender_name, u1.phone as sender_phone,
               u2.name as receiver_name, u2.phone as receiver_phone
        FROM transactions t
        LEFT JOIN users u1 ON t.sender_id = u1.id
        LEFT JOIN users u2 ON t.receiver_id = u2.id
        WHERE t.id = ?
    ''', (transaction_id,))
    
    transaction = cursor.fetchone()
    if not transaction:
        return jsonify({'error': 'Transaction not found'}), 404
    
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    p.setFont("Helvetica-Bold", 24)
    p.setFillColorRGB(0.31, 0.27, 0.90)
    p.drawString(50, height - 50, "Zoro Pay")
    
    p.setFont("Helvetica", 12)
    p.setFillColorRGB(0, 0, 0)
    p.drawString(50, height - 75, "Transaction Receipt")
    
    p.setStrokeColorRGB(0.8, 0.8, 0.8)
    p.line(50, height - 85, width - 50, height - 85)
    
    y = height - 120
    p.setFont("Helvetica-Bold", 10)
    p.setFillColorRGB(0.5, 0.5, 0.5)
    p.drawString(50, y, "DETAILS")
    p.setFillColorRGB(0, 0, 0)
    
    row_height = 25
    y -= row_height
    
    p.setFont("Helvetica", 10)
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawString(50, y, "Transaction ID:")
    p.setFillColorRGB(0, 0, 0)
    p.drawString(180, y, transaction['id'])
    
    y -= row_height
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawString(50, y, "Date & Time:")
    p.setFillColorRGB(0, 0, 0)
    p.drawString(180, y, str(transaction['created_at']))
    
    y -= row_height
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawString(50, y, "Sender:")
    p.setFillColorRGB(0, 0, 0)
    sender_text = f"{transaction['sender_name'] or 'External'} ({transaction['sender_phone'] or 'N/A'})"
    p.drawString(180, y, sender_text)
    
    y -= row_height
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawString(50, y, "Receiver:")
    p.setFillColorRGB(0, 0, 0)
    receiver_text = f"{transaction['receiver_name'] or 'External'} ({transaction['receiver_phone'] or 'N/A'})"
    p.drawString(180, y, receiver_text)
    
    y -= row_height
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawString(50, y, "Amount:")
    p.setFillColorRGB(0.31, 0.27, 0.90)
    p.setFont("Helvetica-Bold", 14)
    p.drawString(180, y, f"₹{transaction['amount']:.2f}")
    
    y -= row_height
    p.setFont("Helvetica", 10)
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawString(50, y, "Note:")
    p.setFillColorRGB(0, 0, 0)
    note_text = transaction['note'] if transaction['note'] else "No note"
    p.drawString(180, y, note_text)
    
    y -= row_height
    p.setFillColorRGB(0.4, 0.4, 0.4)
    p.drawString(50, y, "Status:")
    
    if transaction['status'] == 'success':
        p.setFillColorRGB(0.06, 0.69, 0.51)
    elif transaction['status'] == 'pending':
        p.setFillColorRGB(0.96, 0.62, 0.04)
    else:
        p.setFillColorRGB(0.94, 0.27, 0.27)
    
    p.drawString(180, y, transaction['status'].upper())
    
    p.setFillColorRGB(0.5, 0.5, 0.5)
    p.setFont("Helvetica-Oblique", 8)
    p.drawString(50, 50, "Thank you for using Zoro Pay!")
    p.drawString(50, 35, "For support, contact: support@zoropay.com")
    
    p.save()
    buffer.seek(0)
    
    return send_file(
        buffer, 
        as_attachment=True, 
        download_name=f'receipt_{transaction_id}.pdf', 
        mimetype='application/pdf'
    )

# ====================
# API ENDPOINTS - SEND MONEY
# ====================

@routes_bp.route('/api/send_money', methods=['POST'])
@login_required
def send_money():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request data'}), 400
        
        identifier = data.get('phone') or data.get('identifier')
        amount = float(data.get('amount', 0))
        note = data.get('note', '')
        pin = data.get('pin')
        
        if not identifier:
            return jsonify({'error': 'Recipient identifier required'}), 400
            
        if amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT is_blocked FROM users WHERE id = ?', (session['user_id'],))
        sender_check = cursor.fetchone()
        if sender_check and sender_check['is_blocked']:
            return jsonify({'error': 'Your account has been blocked'}), 403
        
        cursor.execute('SELECT pin, wallet_balance, name, phone FROM users WHERE id = ?', (session['user_id'],))
        sender = cursor.fetchone()
        
        if not sender:
            return jsonify({'error': 'Sender not found'}), 404
            
        if sender['pin'] != pin:
            return jsonify({'error': 'Invalid PIN'}), 400
        
        receiver = None
        
        phone_clean = re.sub(r'[\s\-\(\)]', '', str(identifier))
        if not phone_clean.startswith('+'):
            if phone_clean.startswith('0'):
                phone_clean = '+91' + phone_clean[1:]
            elif len(phone_clean) == 10:
                phone_clean = '+91' + phone_clean
            elif len(phone_clean) == 12 and phone_clean.startswith('91'):
                phone_clean = '+' + phone_clean
            else:
                phone_clean = '+' + phone_clean
        
        cursor.execute('SELECT id, name, phone FROM users WHERE phone = ? AND is_blocked = 0', (phone_clean,))
        receiver = cursor.fetchone()
        
        if not receiver and '@' in identifier:
            cursor.execute('SELECT id, name, phone FROM users WHERE upi_id = ? AND is_blocked = 0', (identifier.lower(),))
            receiver = cursor.fetchone()
        
        if not receiver:
            cursor.execute('SELECT id, name, phone FROM users WHERE name LIKE ? AND is_blocked = 0 LIMIT 1', (f'%{identifier}%',))
            receiver = cursor.fetchone()
        
        if receiver:
            if session['user_id'] == receiver['id']:
                return jsonify({'error': 'Cannot send money to yourself'}), 400
            
            within_limit, total_sent = check_daily_limit(session['user_id'], amount)
            if not within_limit:
                return jsonify({'error': f'Daily limit exceeded. You have sent ₹{total_sent:.2f} out of ₹{DAILY_LIMIT:.2f} today'}), 400
            
            if sender['wallet_balance'] < amount:
                return jsonify({'error': 'Insufficient balance'}), 400
            
            if check_fraud(session['user_id']):
                log_fraud(session['user_id'], 'rapid_transactions', f'Attempted to send ₹{amount}')
                return jsonify({'error': 'Suspicious activity detected. Transaction blocked.'}), 403
            
            new_sender_balance = sender['wallet_balance'] - amount
            cursor.execute('UPDATE users SET wallet_balance = ? WHERE id = ?', (new_sender_balance, session['user_id']))
            cursor.execute('UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?', (amount, receiver['id']))
            
            transaction_id = generate_transaction_id()
            cursor.execute('''
                INSERT INTO transactions (id, sender_id, receiver_id, amount, note, status, sender_phone, receiver_phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (transaction_id, session['user_id'], receiver['id'], amount, note, 'success', sender['phone'], receiver['phone']))
            
            db.commit()
            
            cashback = add_cashback(session['user_id'], amount)
            cashback_msg = f" 🎉 You earned {format_currency(cashback)} cashback!" if cashback > 0 else ""
            
            sender_sms = f"Zoro Pay: You sent {format_currency(amount)} to {receiver['name']}. Transaction ID: {transaction_id}. New balance: {format_currency(new_sender_balance)}{cashback_msg}"
            send_sms_notification(sender['phone'], sender_sms)
            
            receiver_sms = f"Zoro Pay: You received {format_currency(amount)} from {sender['name']}. Transaction ID: {transaction_id}."
            send_sms_notification(receiver['phone'], receiver_sms)
            
            cursor.execute('SELECT wallet_balance FROM users WHERE id = ?', (session['user_id'],))
            new_balance = cursor.fetchone()['wallet_balance']
            
            return jsonify({
                'message': f'✅ {format_currency(amount)} sent successfully!{cashback_msg}',
                'transaction_id': transaction_id,
                'status': 'success',
                'new_balance': float(new_balance),
                'cashback': cashback
            })
        
        else:
            if len(phone_clean) < 10 or not phone_clean.replace('+', '').isdigit():
                return jsonify({'error': 'Invalid phone number. Please enter a valid phone number.'}), 400
            
            if sender['wallet_balance'] < amount:
                return jsonify({'error': 'Insufficient balance'}), 400
            
            within_limit, total_sent = check_daily_limit(session['user_id'], amount)
            if not within_limit:
                return jsonify({'error': f'Daily limit exceeded. You have sent ₹{total_sent:.2f} out of ₹{DAILY_LIMIT:.2f} today'}), 400
            
            new_sender_balance = sender['wallet_balance'] - amount
            cursor.execute('UPDATE users SET wallet_balance = ? WHERE id = ?', (new_sender_balance, session['user_id']))
            
            transaction_id = generate_transaction_id()
            cursor.execute('''
                INSERT INTO transactions (id, sender_id, receiver_id, amount, note, status, receiver_phone, sender_phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (transaction_id, session['user_id'], None, amount, note, 'success', phone_clean, sender['phone']))
            
            db.commit()
            
            cashback = add_cashback(session['user_id'], amount)
            cashback_msg = f" 🎉 You earned {format_currency(cashback)} cashback!" if cashback > 0 else ""
            
            sender_sms = f"Zoro Pay: You sent {format_currency(amount)} to {phone_clean}. Transaction ID: {transaction_id}. New balance: {format_currency(new_sender_balance)}{cashback_msg}"
            send_sms_notification(sender['phone'], sender_sms)
            
            invite_sms = f"Zoro Pay: {sender['name']} sent you {format_currency(amount)}. Download Zoro Pay to receive this money!"
            send_sms_notification(phone_clean, invite_sms)
            
            cursor.execute('SELECT wallet_balance FROM users WHERE id = ?', (session['user_id'],))
            new_balance = cursor.fetchone()['wallet_balance']
            
            return jsonify({
                'message': f'💸 {format_currency(amount)} sent to {phone_clean} successfully!{cashback_msg}',
                'transaction_id': transaction_id,
                'status': 'success',
                'is_external': True,
                'new_balance': float(new_balance),
                'cashback': cashback
            })
        
    except Exception as e:
        print(f"Error in send_money: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Transaction failed: {str(e)}'}), 500

@routes_bp.route('/api/find_user_by_upi', methods=['POST'])
@login_required
def find_user_by_upi():
    data = request.get_json()
    upi_id = data.get('upi_id', '').strip().lower()
    
    if not upi_id:
        return jsonify({'error': 'UPI ID required'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT id, name, phone, upi_id FROM users WHERE upi_id = ? AND is_blocked = 0', (upi_id,))
    user = cursor.fetchone()
    
    if user:
        return jsonify({
            'exists': True,
            'name': user['name'],
            'phone': user['phone'],
            'upi_id': user['upi_id']
        }), 200
    else:
        return jsonify({'exists': False, 'error': 'User not found with this UPI ID'}), 404

@routes_bp.route('/api/find_user', methods=['POST'])
@login_required
def find_user():
    data = request.get_json()
    identifier = data.get('identifier', '').strip()
    
    if not identifier:
        return jsonify({'exists': False, 'error': 'Identifier required'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    if '@' in identifier:
        cursor.execute('SELECT id, name, phone, upi_id FROM users WHERE upi_id = ? AND is_blocked = 0', (identifier.lower(),))
        user = cursor.fetchone()
        if user:
            return jsonify({
                'exists': True,
                'name': user['name'],
                'phone': user['phone'],
                'upi_id': user['upi_id']
            })
    
    phone = re.sub(r'[\s\-\(\)]', '', identifier)
    if not phone.startswith('+'):
        phone = '+' + phone
    
    cursor.execute('SELECT id, name, phone, upi_id FROM users WHERE phone = ? AND is_blocked = 0', (phone,))
    user = cursor.fetchone()
    
    if user:
        return jsonify({
            'exists': True,
            'name': user['name'],
            'phone': user['phone'],
            'upi_id': user['upi_id']
        })
    
    cursor.execute('SELECT id, name, phone, upi_id FROM users WHERE name LIKE ? AND is_blocked = 0 LIMIT 1', (f'%{identifier}%',))
    user = cursor.fetchone()
    
    if user:
        return jsonify({
            'exists': True,
            'name': user['name'],
            'phone': user['phone'],
            'upi_id': user['upi_id']
        })
    
    return jsonify({'exists': False})

# ====================
# API ENDPOINTS - ADD BALANCE
# ====================

@routes_bp.route('/api/add_balance', methods=['POST'])
@login_required
def add_balance():
    data = request.get_json()
    amount = float(data.get('amount', 0))
    pin = data.get('pin')
    payment_method = data.get('payment_method', 'card')
    
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    if amount < 10:
        return jsonify({'error': 'Minimum amount to add is ₹10'}), 400
    
    if amount > 50000:
        return jsonify({'error': 'Maximum amount per transaction is ₹50,000'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT pin, name, phone, wallet_balance FROM users WHERE id = ?', (session['user_id'],))
    user = cursor.fetchone()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if user['pin'] != pin:
        return jsonify({'error': 'Invalid PIN'}), 400
    
    new_balance = user['wallet_balance'] + amount
    
    cursor.execute('UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?', 
                  (amount, session['user_id']))
    
    transaction_id = generate_transaction_id()
    cursor.execute('''
        INSERT INTO transactions (id, sender_id, receiver_id, amount, note, status, sender_phone, receiver_phone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (transaction_id, None, session['user_id'], amount, f'Added balance via {payment_method}', 'success', None, user['phone']))
    
    db.commit()
    
    sms_message = f"Zoro Pay: {format_currency(amount)} added to your wallet. New balance: {format_currency(new_balance)}"
    send_sms_notification(user['phone'], sms_message)
    
    return jsonify({
        'message': f'✅ {format_currency(amount)} added successfully!',
        'new_balance': float(new_balance),
        'transaction_id': transaction_id
    }), 200

# ====================
# API ENDPOINTS - MONEY REQUESTS
# ====================

@routes_bp.route('/api/request_money', methods=['POST'])
@login_required
def request_money():
    data = request.get_json()
    phone = data.get('phone')
    amount = float(data.get('amount', 0))
    note = data.get('note', '')
    
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if not phone.startswith('+'):
        if len(phone) == 10:
            phone = '+91' + phone
        else:
            phone = '+' + phone
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS money_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (requester_id) REFERENCES users(id),
            FOREIGN KEY (target_id) REFERENCES users(id)
        )
    ''')
    db.commit()
    
    cursor.execute('SELECT id, name, phone FROM users WHERE id = ?', (session['user_id'],))
    requester = cursor.fetchone()
    
    if not requester:
        return jsonify({'error': 'User not found'}), 404
    
    cursor.execute('SELECT id, name, phone FROM users WHERE phone = ? AND is_blocked = 0', (phone,))
    target = cursor.fetchone()
    
    if not target:
        return jsonify({'error': 'User not found. Only registered users can receive money requests.'}), 404
    
    if target['id'] == session['user_id']:
        return jsonify({'error': 'Cannot request money from yourself'}), 400
    
    cursor.execute('''
        INSERT INTO money_requests (requester_id, target_id, amount, note, status)
        VALUES (?, ?, ?, ?, 'pending')
    ''', (requester['id'], target['id'], amount, note))
    
    db.commit()
    request_id = cursor.lastrowid
    
    sms_message = f"💰 Zoro Pay: {requester['name']} requested {format_currency(amount)} from you. Open app to approve or reject."
    send_sms_notification(target['phone'], sms_message)
    
    return jsonify({
        'message': f'📨 Money request sent to {target["name"]}!',
        'request_id': request_id,
        'target_name': target['name']
    }), 200

@routes_bp.route('/api/incoming_requests', methods=['GET'])
@login_required
def get_incoming_requests():
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS money_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                note TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (requester_id) REFERENCES users(id),
                FOREIGN KEY (target_id) REFERENCES users(id)
            )
        ''')
        db.commit()
        
        cursor.execute('''
            SELECT mr.*, 
                   u1.id as requester_id, u1.name as requester_name, u1.phone as requester_phone,
                   u2.id as target_id, u2.name as target_name, u2.phone as target_phone
            FROM money_requests mr
            JOIN users u1 ON mr.requester_id = u1.id
            JOIN users u2 ON mr.target_id = u2.id
            WHERE mr.target_id = ? AND mr.status = 'pending'
            ORDER BY mr.created_at DESC
        ''', (session['user_id'],))
        
        requests = []
        for row in cursor.fetchall():
            requests.append({
                'id': row['id'],
                'requester_id': row['requester_id'],
                'requester_name': row['requester_name'] if row['requester_name'] else row['requester_phone'],
                'requester_phone': row['requester_phone'],
                'target_id': row['target_id'],
                'target_name': row['target_name'],
                'target_phone': row['target_phone'],
                'amount': float(row['amount']),
                'note': row['note'] or '',
                'status': row['status'],
                'created_at': row['created_at']
            })
        
        return jsonify(requests), 200
        
    except Exception as e:
        print(f"Error in get_incoming_requests: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([]), 200

@routes_bp.route('/api/incoming_requests/<int:request_id>/resolve', methods=['PUT'])
@login_required
def resolve_incoming_request(request_id):
    try:
        data = request.get_json()
        action = data.get('action')
        
        if action not in ['paid', 'rejected']:
            return jsonify({'error': 'Invalid action. Use "paid" or "rejected"'}), 400
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT mr.*, 
                   u1.id as requester_id, u1.name as requester_name, u1.phone as requester_phone, u1.wallet_balance as requester_balance,
                   u2.id as target_id, u2.name as target_name, u2.phone as target_phone, u2.wallet_balance as target_balance
            FROM money_requests mr
            JOIN users u1 ON mr.requester_id = u1.id
            JOIN users u2 ON mr.target_id = u2.id
            WHERE mr.id = ? AND mr.target_id = ? AND mr.status = 'pending'
        ''', (request_id, session['user_id']))
        
        request_data = cursor.fetchone()
        
        if not request_data:
            return jsonify({'error': 'Request not found or already processed'}), 404
        
        if action == 'rejected':
            cursor.execute('''
                UPDATE money_requests 
                SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (request_id,))
            db.commit()
            
            sms_message = f"Zoro Pay: {request_data['target_name']} rejected your money request of {format_currency(request_data['amount'])}."
            send_sms_notification(request_data['requester_phone'], sms_message)
            
            return jsonify({'message': 'Request rejected successfully'}), 200
        
        elif action == 'paid':
            amount = float(request_data['amount'])
            target_id = session['user_id']
            requester_id = request_data['requester_id']
            
            if request_data['target_balance'] < amount:
                return jsonify({'error': 'Insufficient balance to approve this request'}), 400
            
            within_limit, total_sent = check_daily_limit(target_id, amount)
            if not within_limit:
                return jsonify({'error': f'Daily limit exceeded. You have sent ₹{total_sent:.2f} out of ₹{DAILY_LIMIT:.2f} today'}), 400
            
            if check_fraud(target_id):
                log_fraud(target_id, 'rapid_transactions', f'Approved money request of ₹{amount}')
                return jsonify({'error': 'Suspicious activity detected. Transaction blocked.'}), 403
            
            new_target_balance = request_data['target_balance'] - amount
            cursor.execute('UPDATE users SET wallet_balance = ? WHERE id = ?', (new_target_balance, target_id))
            cursor.execute('UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?', (amount, requester_id))
            
            cursor.execute('''
                UPDATE money_requests 
                SET status = 'paid', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (request_id,))
            
            transaction_id = generate_transaction_id()
            cursor.execute('''
                INSERT INTO transactions (id, sender_id, receiver_id, amount, note, status, sender_phone, receiver_phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (transaction_id, target_id, requester_id, amount, f"Approved money request: {request_data['note']}", 'success', 
                  request_data['target_phone'], request_data['requester_phone']))
            
            db.commit()
            
            cashback = add_cashback(target_id, amount)
            cashback_msg = f" 🎉 You earned {format_currency(cashback)} cashback!" if cashback > 0 else ""
            
            sender_sms = f"Zoro Pay: You sent {format_currency(amount)} to {request_data['requester_name']} (approved request). Transaction ID: {transaction_id}. New balance: {format_currency(new_target_balance)}{cashback_msg}"
            send_sms_notification(request_data['target_phone'], sender_sms)
            
            receiver_sms = f"Zoro Pay: You received {format_currency(amount)} from {request_data['target_name']} (request approved). Transaction ID: {transaction_id}."
            send_sms_notification(request_data['requester_phone'], receiver_sms)
            
            cursor.execute('SELECT wallet_balance FROM users WHERE id = ?', (target_id,))
            new_balance = cursor.fetchone()['wallet_balance']
            
            return jsonify({
                'message': f'✅ {format_currency(amount)} sent successfully!{cashback_msg}',
                'transaction_id': transaction_id,
                'status': 'success',
                'new_balance': float(new_balance),
                'cashback': cashback
            }), 200
        
    except Exception as e:
        print(f"Error in resolve_incoming_request: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/sent_requests', methods=['GET'])
@login_required
def get_sent_requests():
    try:
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            SELECT mr.*, 
                   u1.name as requester_name, u1.phone as requester_phone,
                   u2.name as target_name, u2.phone as target_phone
            FROM money_requests mr
            JOIN users u1 ON mr.requester_id = u1.id
            JOIN users u2 ON mr.target_id = u2.id
            WHERE mr.requester_id = ?
            ORDER BY mr.created_at DESC
        ''', (session['user_id'],))
        
        requests = []
        for row in cursor.fetchall():
            requests.append({
                'id': row['id'],
                'target_name': row['target_name'] if row['target_name'] else row['target_phone'],
                'target_phone': row['target_phone'],
                'amount': float(row['amount']),
                'note': row['note'] or '',
                'status': row['status'],
                'created_at': row['created_at']
            })
        
        return jsonify(requests), 200
        
    except Exception as e:
        print(f"Error in get_sent_requests: {e}")
        return jsonify([]), 200

# ====================
# API ENDPOINTS - CONTACTS
# ====================

@routes_bp.route('/api/people')
@login_required
def get_people():
    try:
        db = get_db()
        cursor = db.cursor()
        
        people = []
        seen_phones = set()
        
        cursor.execute('SELECT phone FROM users WHERE id = ?', (session['user_id'],))
        current_user = cursor.fetchone()
        current_user_phone = current_user['phone'] if current_user else None
        
        cursor.execute('''
            SELECT DISTINCT 
                c.contact_phone as phone,
                c.contact_name as name,
                c.is_favorite,
                u.id as user_id,
                u.name as registered_name
            FROM contacts c
            LEFT JOIN users u ON c.contact_phone = u.phone
            WHERE c.user_id = ?
            ORDER BY c.is_favorite DESC, c.contact_name ASC
        ''', (session['user_id'],))
        
        contacts = cursor.fetchall()
        
        for contact in contacts:
            phone = contact['phone']
            if not phone or phone == current_user_phone:
                continue
            if phone in seen_phones:
                continue
            seen_phones.add(phone)
            
            name = contact['name'] if contact['name'] else contact['registered_name']
            if not name:
                name = phone
            
            people.append({
                'id': contact['user_id'] if contact['user_id'] else phone,
                'name': name,
                'phone': phone,
                'initial': name[0].upper() if name and name[0].isalpha() else '📱',
                'is_favorite': bool(contact['is_favorite']),
                'is_registered': contact['user_id'] is not None
            })
        
        cursor.execute('''
            SELECT DISTINCT 
                u.id as user_id,
                u.phone,
                u.name
            FROM transactions t
            JOIN users u ON (u.id = t.sender_id OR u.id = t.receiver_id)
            WHERE (t.sender_id = ? OR t.receiver_id = ?)
              AND u.id != ?
        ''', (session['user_id'], session['user_id'], session['user_id']))
        
        user_partners = cursor.fetchall()
        
        for partner in user_partners:
            phone = partner['phone']
            if not phone or phone == current_user_phone:
                continue
            if phone in seen_phones:
                continue
            seen_phones.add(phone)
            
            name = partner['name'] if partner['name'] else phone
            
            people.append({
                'id': partner['user_id'],
                'name': name,
                'phone': phone,
                'initial': name[0].upper() if name and name[0].isalpha() else '📱',
                'is_favorite': False,
                'is_registered': True
            })
        
        people.sort(key=lambda x: (not x['is_favorite'], x['name'].lower()))
        
        return jsonify(people)
    except Exception as e:
        print(f"Error in get_people: {e}")
        return jsonify([])

@routes_bp.route('/api/contacts', methods=['GET'])
@login_required
def get_contacts():
    try:
        from database import get_user_contacts
        contacts = get_user_contacts(session['user_id'])
        contacts_list = []
        for contact in contacts:
            contacts_list.append({
                'id': contact['id'],
                'phone': contact['contact_phone'],
                'name': contact['contact_name'],
                'type': contact['contact_type'],
                'is_favorite': contact['is_favorite'],
                'registered_name': contact['registered_name'],
                'is_registered': contact['registered_id'] is not None
            })
        return jsonify(contacts_list)
    except Exception as e:
        print(f"Error in get_contacts: {e}")
        return jsonify([])

@routes_bp.route('/api/contacts', methods=['POST'])
@login_required
def add_contact_api():
    from database import add_contact
    data = request.get_json()
    phone = data.get('phone')
    name = data.get('name')
    
    if not phone or not name:
        return jsonify({'error': 'Phone and name required'}), 400
    
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if not phone.startswith('+'):
        phone = '+' + phone
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, name FROM users WHERE phone = ?', (phone,))
    existing_user = cursor.fetchone()
    
    contact_type = 'internal' if existing_user else 'external'
    
    success = add_contact(session['user_id'], phone, name, contact_type)
    if success:
        return jsonify({'message': 'Contact added successfully', 'type': contact_type}), 201
    else:
        return jsonify({'error': 'Contact already exists'}), 400

@routes_bp.route('/api/contacts/<int:contact_id>/favorite', methods=['PUT'])
@login_required
def toggle_favorite(contact_id):
    from database import update_contact_favorite
    data = request.get_json()
    is_favorite = data.get('is_favorite', 0)
    
    success = update_contact_favorite(contact_id, session['user_id'], is_favorite)
    if success:
        return jsonify({'message': 'Favorite status updated'}), 200
    return jsonify({'error': 'Contact not found'}), 404

@routes_bp.route('/api/contacts/<int:contact_id>', methods=['DELETE'])
@login_required
def delete_contact_api(contact_id):
    from database import delete_contact
    success = delete_contact(contact_id, session['user_id'])
    if success:
        return jsonify({'message': 'Contact deleted successfully'}), 200
    return jsonify({'error': 'Contact not found'}), 404

@routes_bp.route('/api/contacts/<int:contact_id>', methods=['PUT'])
@login_required
def update_contact_api(contact_id):
    from database import update_contact
    data = request.get_json()
    name = data.get('name')
    
    if not name:
        return jsonify({'error': 'Name required'}), 400
    
    success = update_contact(contact_id, session['user_id'], name)
    if success:
        return jsonify({'message': 'Contact updated successfully'}), 200
    return jsonify({'error': 'Contact not found'}), 404

# ====================
# API ENDPOINTS - ANALYTICS
# ====================

@routes_bp.route('/api/analytics/monthly_spending', methods=['GET'])
@login_required
def get_monthly_spending():
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT 
            strftime('%Y-%m', created_at) as month,
            SUM(amount) as total_sent,
            COUNT(*) as count
        FROM transactions
        WHERE sender_id = ? AND status = 'success'
        AND created_at >= date('now', '-5 months')
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY month ASC
    ''', (session['user_id'],))
    
    sent_results = cursor.fetchall()
    
    cursor.execute('''
        SELECT 
            strftime('%Y-%m', created_at) as month,
            SUM(amount) as total_received,
            COUNT(*) as count
        FROM transactions
        WHERE receiver_id = ? AND status = 'success'
        AND created_at >= date('now', '-5 months')
        GROUP BY strftime('%Y-%m', created_at)
        ORDER BY month ASC
    ''', (session['user_id'],))
    
    received_results = cursor.fetchall()
    
    sent_dict = {row['month']: float(row['total_sent'] or 0) for row in sent_results}
    received_dict = {row['month']: float(row['total_received'] or 0) for row in received_results}
    
    months = []
    current_date = datetime.now()
    for i in range(5, -1, -1):
        month_date = current_date - timedelta(days=30*i)
        month_str = month_date.strftime('%Y-%m')
        months.append(month_str)
    
    month_labels = []
    sent_amounts = []
    received_amounts = []
    
    for month in months:
        month_date = datetime.strptime(month, '%Y-%m')
        month_labels.append(month_date.strftime('%b %Y'))
        sent_amounts.append(sent_dict.get(month, 0))
        received_amounts.append(received_dict.get(month, 0))
    
    return jsonify({
        'months': month_labels,
        'amounts': sent_amounts,
        'received_amounts': received_amounts,
        'sent_counts': [sent_dict.get(month, 0) for month in months],
        'received_counts': [received_dict.get(month, 0) for month in months]
    })

@routes_bp.route('/api/analytics/transactions', methods=['GET'])
@login_required
def get_analytics_transactions():
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE sender_id = ? AND status = 'success'
        AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
    ''', (session['user_id'],))
    monthly_spent = cursor.fetchone()
    monthly_spent = float(monthly_spent['total'] or 0)
    
    cursor.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE receiver_id = ? AND status = 'success'
        AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
    ''', (session['user_id'],))
    monthly_received = cursor.fetchone()
    monthly_received = float(monthly_received['total'] or 0)
    
    cursor.execute('''
        SELECT COUNT(*) as count FROM transactions 
        WHERE (sender_id = ? OR receiver_id = ?) AND status = 'success'
    ''', (session['user_id'], session['user_id']))
    total_transactions = cursor.fetchone()
    total_transactions = total_transactions['count'] or 0
    
    cursor.execute('''
        SELECT AVG(amount) as avg FROM transactions 
        WHERE sender_id = ? AND status = 'success'
    ''', (session['user_id'],))
    avg_transaction = cursor.fetchone()
    avg_transaction = float(avg_transaction['avg'] or 0)
    
    cursor.execute('''
        SELECT MAX(amount) as max_amount FROM transactions 
        WHERE (sender_id = ? OR receiver_id = ?) AND status = 'success'
    ''', (session['user_id'], session['user_id']))
    largest_transaction = cursor.fetchone()
    largest_transaction = float(largest_transaction['max_amount'] or 0)
    
    cursor.execute('''
        SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
        FROM transactions
        WHERE (sender_id = ? OR receiver_id = ?) AND status = 'success'
        GROUP BY month
        ORDER BY count DESC
        LIMIT 1
    ''', (session['user_id'], session['user_id']))
    active_month = cursor.fetchone()
    
    return jsonify({
        'monthly_spent': monthly_spent,
        'monthly_received': monthly_received,
        'total_transactions': total_transactions,
        'avg_transaction': avg_transaction,
        'largest_transaction': largest_transaction,
        'most_active_month': active_month['month'] if active_month else None,
        'daily_limit': DAILY_LIMIT
    })

# ====================
# API ENDPOINTS - CASHBACK
# ====================

@routes_bp.route('/api/cashback_history', methods=['GET'])
@login_required
def get_cashback_history():
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT * FROM cashback_history 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 50
    ''', (session['user_id'],))
    
    cashbacks = []
    for row in cursor.fetchall():
        cashbacks.append({
            'id': row['id'],
            'transaction_amount': float(row['transaction_amount']),
            'amount': float(row['cashback_amount']),
            'percentage': float(row['percentage']),
            'transaction_id': 'N/A',
            'created_at': row['created_at']
        })
    
    return jsonify(cashbacks)

@routes_bp.route('/api/cashback/pending', methods=['GET'])
@login_required
def get_pending_cashback_api():
    from database import get_pending_cashback, get_cashback_history
    
    user_id = session['user_id']
    pending_total, pending_count = get_pending_cashback(user_id)
    history = get_cashback_history(user_id, include_claimed=True)
    
    history_list = []
    for row in history:
        history_list.append({
            'id': row['id'],
            'transaction_amount': float(row['transaction_amount']),
            'cashback_amount': float(row['cashback_amount']),
            'percentage': float(row['percentage']),
            'claimed': row['claimed'],
            'claimed_at': row['claimed_at'],
            'created_at': row['created_at']
        })
    
    return jsonify({
        'pending_total': pending_total,
        'pending_count': pending_count,
        'history': history_list
    })

@routes_bp.route('/api/cashback/claim', methods=['POST'])
@login_required
def claim_cashback_api():
    from database import claim_pending_cashback, get_pending_cashback
    
    user_id = session['user_id']
    pending_total, pending_count = get_pending_cashback(user_id)
    
    if pending_total <= 0:
        return jsonify({'error': 'No pending cashback to claim'}), 400
    
    claimed_amount, claimed_count = claim_pending_cashback(user_id)
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT wallet_balance FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    
    cursor.execute('SELECT phone, name FROM users WHERE id = ?', (user_id,))
    user_info = cursor.fetchone()
    if user_info:
        sms_message = f"Zoro Pay: You claimed {format_currency(claimed_amount)} cashback! New wallet balance: {format_currency(user['wallet_balance'])}"
        send_sms_notification(user_info['phone'], sms_message)
    
    return jsonify({
        'message': f'Successfully claimed {format_currency(claimed_amount)} cashback!',
        'claimed_amount': claimed_amount,
        'claimed_count': claimed_count,
        'new_balance': float(user['wallet_balance']) if user else 0
    })

@routes_bp.route('/api/cashback/history', methods=['GET'])
@login_required
def get_cashback_history_api():
    from database import get_cashback_history
    
    user_id = session['user_id']
    history = get_cashback_history(user_id, include_claimed=True)
    
    history_list = []
    for row in history:
        history_list.append({
            'id': row['id'],
            'transaction_amount': float(row['transaction_amount']),
            'cashback_amount': float(row['cashback_amount']),
            'percentage': float(row['percentage']),
            'claimed': row['claimed'],
            'claimed_at': row['claimed_at'],
            'created_at': row['created_at']
        })
    
    return jsonify(history_list)

# ====================
# API ENDPOINTS - BIOMETRIC
# ====================

@routes_bp.route('/api/biometric/status', methods=['GET'])
@login_required
def get_biometric_status():
    from database import get_biometric_credentials, is_biometric_enabled
    
    user_id = session['user_id']
    enabled = is_biometric_enabled(user_id)
    credentials = get_biometric_credentials(user_id)
    
    return jsonify({
        'enabled': enabled,
        'credentials': [{
            'id': cred['id'],
            'credential_id': cred['credential_id'],
            'device_name': cred['device_name'],
            'created_at': cred['created_at'],
            'last_used': cred['last_used']
        } for cred in credentials]
    })

@routes_bp.route('/api/biometric/register', methods=['POST'])
@login_required
def register_biometric():
    from database import register_biometric_credential
    
    data = request.get_json()
    credential_id = data.get('credential_id')
    public_key = data.get('public_key')
    device_name = data.get('device_name', 'WebAuthn Device')
    
    if not credential_id or not public_key:
        return jsonify({'error': 'Missing biometric data'}), 400
    
    user_id = session['user_id']
    
    success = register_biometric_credential(user_id, credential_id, public_key, device_name)
    
    if success:
        return jsonify({'message': 'Biometric registered successfully'}), 200
    else:
        return jsonify({'error': 'Failed to register biometric credential'}), 500

@routes_bp.route('/api/biometric/disable', methods=['POST'])
@login_required
def disable_biometric():
    from database import disable_all_biometric_credentials
    
    user_id = session['user_id']
    success = disable_all_biometric_credentials(user_id)
    
    if success:
        return jsonify({'message': 'Biometric login disabled'}), 200
    else:
        return jsonify({'error': 'Failed to disable biometric login'}), 500

@routes_bp.route('/api/biometric/remove', methods=['POST'])
@login_required
def remove_biometric_device():
    from database import disable_biometric_credential
    
    data = request.get_json()
    credential_id = data.get('credential_id')
    
    if not credential_id:
        return jsonify({'error': 'Credential ID required'}), 400
    
    user_id = session['user_id']
    success = disable_biometric_credential(user_id, credential_id)
    
    if success:
        return jsonify({'message': 'Biometric device removed'}), 200
    else:
        return jsonify({'error': 'Failed to remove biometric device'}), 500

@routes_bp.route('/api/biometric/verify', methods=['POST'])
def verify_biometric():
    from database import get_biometric_credential_by_id, update_biometric_last_used
    import jwt
    from datetime import datetime, timedelta
    
    data = request.get_json()
    credential_id = data.get('credential_id')
    phone = data.get('phone')
    
    if not credential_id or not phone:
        return jsonify({'error': 'Missing verification data'}), 400
    
    credential = get_biometric_credential_by_id(credential_id)
    
    if not credential or credential['phone'] != phone:
        return jsonify({'error': 'Invalid biometric credential'}), 401
    
    update_biometric_last_used(credential_id)
    
    token = jwt.encode({
        'user_id': credential['user_id'],
        'phone': phone,
        'exp': datetime.now() + timedelta(days=7)
    }, JWT_SECRET, algorithm='HS256')
    
    session['user_id'] = credential['user_id']
    session['phone'] = phone
    session.permanent = True
    
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT name, wallet_balance, referral_code, upi_id FROM users WHERE id = ?', (credential['user_id'],))
    user = cursor.fetchone()
    
    return jsonify({
        'message': 'Biometric login successful',
        'token': token,
        'user': {
            'id': credential['user_id'],
            'phone': phone,
            'name': user['name'] if user else 'User',
            'balance': float(user['wallet_balance']) if user and user['wallet_balance'] else 0,
            'referral_code': user['referral_code'] if user else None,
            'upi_id': user['upi_id'] if user else None
        }
    }), 200

@routes_bp.route('/api/webauthn/config')
def webauthn_config():
    host = request.host.split(':')[0]
    if host in ['localhost', '127.0.0.1']:
        rp_id = 'localhost'
    else:
        rp_id = host
    
    return jsonify({
        'rpId': rp_id,
        'rpName': 'Zoro Pay',
        'origin': request.host_url.rstrip('/')
    })
    
@routes_bp.route('/api/biometric/public_status', methods=['POST'])
def public_biometric_status():
    from database import get_db, get_biometric_credentials
    
    data = request.get_json()
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'enabled': False, 'credentials': []}), 200
    
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if not phone.startswith('+'):
        if len(phone) == 10:
            phone = '+91' + phone
        else:
            phone = '+' + phone
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT id, biometric_enabled FROM users WHERE phone = ?', (phone,))
    user = cursor.fetchone()
    
    if not user or not user['biometric_enabled']:
        return jsonify({'enabled': False, 'credentials': []}), 200
    
    credentials = get_biometric_credentials(user['id'])
    
    return jsonify({
        'enabled': len(credentials) > 0,
        'credentials': [{
            'credential_id': cred['credential_id'],
            'device_name': cred['device_name'],
            'created_at': cred['created_at']
        } for cred in credentials]
    })

@routes_bp.route('/api/biometric/public_disable', methods=['POST'])
def public_disable_biometric():
    from database import get_db, disable_all_biometric_credentials
    
    data = request.get_json()
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'error': 'Phone required'}), 400
    
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if not phone.startswith('+'):
        if len(phone) == 10:
            phone = '+91' + phone
        else:
            phone = '+' + phone
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT id FROM users WHERE phone = ?', (phone,))
    user = cursor.fetchone()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    success = disable_all_biometric_credentials(user['id'])
    
    if success:
        return jsonify({'message': 'Biometric disabled successfully'}), 200
    else:
        return jsonify({'error': 'Failed to disable biometric'}), 500

# ====================
# API ENDPOINTS - VIRTUAL CARD
# ====================

@routes_bp.route('/api/virtual_card', methods=['GET'])
@login_required
def get_virtual_card():
    try:
        from database import get_virtual_card, generate_virtual_card_for_user
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT id, name, phone FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        card = get_virtual_card(user['id'])
        
        if not card:
            card_data = generate_virtual_card_for_user(user['id'], user['name'])
            return jsonify({
                'card_number': card_data['card_number'],
                'expiry_date': card_data['expiry_date'],
                'cvv': card_data['cvv'],
                'card_holder_name': card_data['card_holder_name'],
                'card_type': 'virtual',
                'is_active': 1
            }), 200
        else:
            return jsonify({
                'card_number': card['card_number'],
                'expiry_date': card['expiry_date'],
                'cvv': card['cvv'],
                'card_holder_name': card['card_holder_name'],
                'card_type': card['card_type'] if 'card_type' in card.keys() else 'virtual',
                'is_active': card['is_active'] if 'is_active' in card.keys() else 1,
                'created_at': card['created_at'] if 'created_at' in card.keys() else None
            }), 200
        
    except Exception as e:
        print(f"Error in get_virtual_card: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/virtual_card/regenerate', methods=['POST'])
@login_required
def regenerate_virtual_card():
    try:
        from database import regenerate_virtual_card
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT id, name, phone FROM users WHERE id = ?', (session['user_id'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        new_card = regenerate_virtual_card(user['id'], user['name'])
        
        sms_message = f"Zoro Pay: Your virtual debit card has been regenerated. Old card is now deactivated. New card ending with {new_card['card_number'][-4:]} is active."
        send_sms_notification(user['phone'], sms_message)
        
        return jsonify({
            'card_number': new_card['card_number'],
            'expiry_date': new_card['expiry_date'],
            'cvv': new_card['cvv'],
            'card_holder_name': new_card['card_holder_name'],
            'message': 'Virtual card regenerated successfully'
        }), 200
        
    except Exception as e:
        print(f"Error in regenerate_virtual_card: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500