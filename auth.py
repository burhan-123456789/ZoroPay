from flask import Blueprint, request, jsonify, session
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import random
import os
from datetime import datetime, timedelta
from database import get_db, validate_referral_code, apply_referral_bonus
import hashlib
import re
import jwt
from functools import wraps

auth_bp = Blueprint('auth', __name__)

TWILIO_SID = os.getenv('TWILIO_SID')
TWILIO_AUTH = os.getenv('TWILIO_AUTH')
TWILIO_PHONE = os.getenv('TWILIO_PHONE')
JWT_SECRET = os.getenv('JWT_SECRET', 'your-jwt-secret-key-change-this')
USE_MOCK_OTP = False

def generate_referral_code(phone):
    return hashlib.md5(f"{phone}{datetime.now()}".encode()).hexdigest()[:8].upper()

def generate_upi_id(name, phone):
    """Generate UPI ID: username@zoropay"""
    username = name.lower().replace(' ', '')[:15]
    base = f"{username}{phone[-4:]}"
    return f"{base}@zoropay"

def generate_api_key():
    """Generate a unique API key"""
    return hashlib.md5(f"{datetime.now()}{random.random()}".encode()).hexdigest()

def validate_phone_number(phone):
    phone = re.sub(r'[\s\-\(\)\+]', '', phone)
    
    if phone.startswith('91') and len(phone) == 12:
        phone = '+' + phone
    elif phone.startswith('1') and len(phone) == 11:
        phone = '+' + phone
    elif not phone.startswith('+'):
        if len(phone) == 10:
            phone = '+91' + phone
        else:
            phone = '+' + phone
    
    return phone

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            
            data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            request.user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(*args, **kwargs)
    return decorated

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

@auth_bp.route('/send_otp', methods=['POST'])
def send_otp():
    data = request.get_json()
    phone = data.get('phone')
    
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    
    phone = validate_phone_number(phone)
    
    otp = str(random.randint(100000, 999999))
    expires_at = datetime.now() + timedelta(minutes=5)
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('DELETE FROM otp WHERE phone = ?', (phone,))
    
    cursor.execute(
        'INSERT INTO otp (phone, otp, expires_at) VALUES (?, ?, ?)',
        (phone, otp, expires_at)
    )
    db.commit()
    
    if USE_MOCK_OTP:
        print(f"MOCK OTP for {phone}: {otp}")
        return jsonify({'message': f'OTP sent (mock: {otp})', 'mock_otp': otp}), 200
    else:
        try:
            client = Client(TWILIO_SID, TWILIO_AUTH)
            
            message = client.messages.create(
                body=f'Your Zoro Pay OTP is: {otp}. Valid for 5 minutes. Do not share this with anyone.',
                from_=TWILIO_PHONE,
                to=phone
            )
            
            print(f"OTP sent to {phone}. Message SID: {message.sid}")
            
            return jsonify({'message': 'OTP sent successfully to your phone'}), 200
            
        except TwilioRestException as e:
            print(f"Twilio Error: {e}")
            error_msg = str(e)
            
            if '21211' in error_msg:
                return jsonify({'error': 'Invalid phone number format. Please use format: +919876543210'}), 400
            elif '21608' in error_msg:
                return jsonify({'error': 'For trial accounts, please verify your phone number with Twilio first'}), 400
            elif '20003' in error_msg:
                return jsonify({'error': 'Twilio authentication failed. Check your credentials.'}), 500
            else:
                return jsonify({'error': f'SMS sending failed: {str(e)}'}), 500
        except Exception as e:
            print(f"Unexpected error: {e}")
            return jsonify({'error': 'Failed to send OTP. Please try again.'}), 500

@auth_bp.route('/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    phone = data.get('phone')
    otp = data.get('otp')
    name = data.get('name', f'User_{phone[-4:]}')
    referral_code = data.get('referral_code', '').strip().upper()
    
    if not phone or not otp:
        return jsonify({'error': 'Phone and OTP required'}), 400
    
    phone = validate_phone_number(phone)
    
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute(
        'SELECT * FROM otp WHERE phone = ? AND otp = ? AND expires_at > ?',
        (phone, otp, datetime.now())
    )
    otp_record = cursor.fetchone()
    
    if not otp_record:
        return jsonify({'error': 'Invalid or expired OTP'}), 400
    
    cursor.execute('DELETE FROM otp WHERE phone = ?', (phone,))
    db.commit()
    
    cursor.execute('SELECT * FROM users WHERE phone = ?', (phone,))
    user = cursor.fetchone()
    
    is_new_user = False
    referrer_info = None
    
    if referral_code and not user:
        referrer = validate_referral_code(referral_code)
        if referrer:
            referrer_info = referrer
            print(f"Valid referral code {referral_code} from user {referrer['name']}")
        else:
            return jsonify({'error': 'Invalid referral code'}), 400
    
    if not user:
        try:
            new_referral_code = generate_referral_code(phone)
            upi_id = generate_upi_id(name, phone)
            api_key = generate_api_key()
            
            cursor.execute(
                '''INSERT OR IGNORE INTO users 
                   (phone, name, wallet_balance, referral_code, referred_by, upi_id, api_key) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (phone, name, 100.0, new_referral_code, referral_code if referrer_info else None, upi_id, api_key)
            )
            db.commit()
            
            cursor.execute('SELECT * FROM users WHERE phone = ?', (phone,))
            user = cursor.fetchone()
            
            if not user:
                return jsonify({'error': 'Failed to create user. Please try again.'}), 500
            
            is_new_user = True
            
            if referrer_info:
                success = apply_referral_bonus(user['id'], referrer_info['id'])
                if success:
                    print(f"Referral bonus applied: New user {user['id']}, Referrer {referrer_info['id']}")
                else:
                    print("Failed to apply referral bonus")
                
        except Exception as e:
            print(f"Error creating user: {e}")
            db.rollback()
            
            cursor.execute('SELECT * FROM users WHERE phone = ?', (phone,))
            user = cursor.fetchone()
            
            if not user:
                return jsonify({'error': 'Failed to create user. Please try again.'}), 500
    
    # Generate JWT token
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
            'balance': user['wallet_balance'],
            'referral_code': user['referral_code'],
            'upi_id': user['upi_id'],
            'is_new_user': is_new_user,
            'referral_applied': bool(referrer_info)
        }
    }), 200

@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'}), 200

@auth_bp.route('/api/validate_referral_code', methods=['POST'])
def validate_referral_code_api():
    data = request.get_json()
    referral_code = data.get('referral_code', '').strip().upper()
    
    if not referral_code:
        return jsonify({'error': 'Referral code required'}), 400
    
    referrer = validate_referral_code(referral_code)
    
    if referrer:
        return jsonify({
            'valid': True,
            'message': f'Valid referral code from {referrer["name"]}! You will get ₹250 bonus, and {referrer["name"]} will also get ₹250!',
            'referrer_name': referrer['name']
        }), 200
    else:
        return jsonify({
            'valid': False,
            'error': 'Invalid referral code'
        }), 400

@auth_bp.route('/api/refresh_token', methods=['POST'])
@token_required
def refresh_token():
    token = jwt.encode({
        'user_id': request.user_id,
        'exp': datetime.now() + timedelta(days=7)
    }, JWT_SECRET, algorithm='HS256')
    
    return jsonify({'token': token}), 200