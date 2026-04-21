from flask import Blueprint, request, jsonify, session, render_template
from database import get_db
from datetime import datetime
from functools import wraps

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ADMIN_CREDENTIALS = {
    'username': 'admin',
    'password': 'admin123'
}

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session['admin_logged_in']:
            return jsonify({'error': 'Admin authentication required'}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


# ====================
# PAGE ROUTES
# ====================

@admin_bp.route('/')
def admin_index():
    """Admin panel home page"""
    if 'admin_logged_in' in session and session['admin_logged_in']:
        return render_template('admin.html')
    return render_template('admin_login.html')


@admin_bp.route('/login', methods=['POST'])
def admin_login():
    """Admin login API"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    print(f"Admin login attempt - Username: {username}")  # Debug
    
    if username == ADMIN_CREDENTIALS['username'] and password == ADMIN_CREDENTIALS['password']:
        session['admin_logged_in'] = True
        session.permanent = True
        print("Admin login successful!")  # Debug
        return jsonify({'success': True, 'message': 'Login successful'}), 200
    
    print("Admin login failed - Invalid credentials")  # Debug
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401


@admin_bp.route('/logout', methods=['POST'])
def admin_logout():
    """Admin logout API"""
    session.pop('admin_logged_in', None)
    return jsonify({'message': 'Logged out successfully'}), 200


# ====================
# USERS API
# ====================

@admin_bp.route('/api/users')
@admin_login_required
def get_all_users():
    """Get all users with details"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT id, phone, name, wallet_balance, referral_code, 
               created_at, is_blocked, cashback_earned, api_usage_count,
               upi_id
        FROM users 
        ORDER BY created_at DESC
    ''')
    
    users = []
    for row in cursor.fetchall():
        users.append({
            'id': row['id'],
            'phone': row['phone'],
            'name': row['name'] or 'N/A',
            'balance': float(row['wallet_balance']),
            'referral_code': row['referral_code'],
            'joined': row['created_at'],
            'is_blocked': bool(row['is_blocked'] or 0),
            'cashback_earned': float(row['cashback_earned'] or 0),
            'api_usage': row['api_usage_count'] or 0,
            'upi_id': row['upi_id'] or 'Not set'
        })
    
    return jsonify(users)


@admin_bp.route('/api/users/<int:user_id>')
@admin_login_required
def get_user_details(user_id):
    """Get single user details"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT id, phone, name, wallet_balance, referral_code, 
               created_at, is_blocked, cashback_earned, api_usage_count,
               upi_id, referred_by
        FROM users 
        WHERE id = ?
    ''', (user_id,))
    
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'User not found'}), 404
    
    # Get referral count
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE referred_by = ?', (row['referral_code'],))
    referral_count = cursor.fetchone()['count']
    
    user = {
        'id': row['id'],
        'phone': row['phone'],
        'name': row['name'] or 'N/A',
        'balance': float(row['wallet_balance']),
        'referral_code': row['referral_code'],
        'joined': row['created_at'],
        'is_blocked': bool(row['is_blocked'] or 0),
        'cashback_earned': float(row['cashback_earned'] or 0),
        'api_usage': row['api_usage_count'] or 0,
        'upi_id': row['upi_id'] or 'Not set',
        'referred_by': row['referred_by'] or 'None',
        'referral_count': referral_count
    }
    
    return jsonify(user)


@admin_bp.route('/api/users/<int:user_id>/block', methods=['POST'])
@admin_login_required
def block_user(user_id):
    """Block a user"""
    db = get_db()
    cursor = db.cursor()
    
    # Check if user exists
    cursor.execute('SELECT id, name FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    cursor.execute('UPDATE users SET is_blocked = 1 WHERE id = ?', (user_id,))
    db.commit()
    
    # Log to fraud_logs
    cursor.execute('''
        INSERT INTO fraud_logs (user_id, fraud_type, description, created_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, 'admin_action', f'User {user["name"]} was blocked by admin', datetime.now()))
    db.commit()
    
    return jsonify({'message': f'User {user["name"]} blocked successfully'})


@admin_bp.route('/api/users/<int:user_id>/unblock', methods=['POST'])
@admin_login_required
def unblock_user(user_id):
    """Unblock a user"""
    db = get_db()
    cursor = db.cursor()
    
    # Check if user exists
    cursor.execute('SELECT id, name FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    cursor.execute('UPDATE users SET is_blocked = 0 WHERE id = ?', (user_id,))
    db.commit()
    
    # Log to fraud_logs
    cursor.execute('''
        INSERT INTO fraud_logs (user_id, fraud_type, description, created_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, 'admin_action', f'User {user["name"]} was unblocked by admin', datetime.now()))
    db.commit()
    
    return jsonify({'message': f'User {user["name"]} unblocked successfully'})


@admin_bp.route('/api/users/<int:user_id>/adjust_balance', methods=['POST'])
@admin_login_required
def adjust_user_balance(user_id):
    """Adjust user balance (add or deduct)"""
    data = request.get_json()
    amount = data.get('amount', 0)
    reason = data.get('reason', 'Admin adjustment')
    
    if amount == 0:
        return jsonify({'error': 'Amount must be non-zero'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    # Check if user exists
    cursor.execute('SELECT id, name, wallet_balance FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    new_balance = float(user['wallet_balance']) + amount
    if new_balance < 0:
        return jsonify({'error': 'Balance cannot go negative'}), 400
    
    cursor.execute('UPDATE users SET wallet_balance = ? WHERE id = ?', (new_balance, user_id))
    
    # Create adjustment transaction
    txn_id = f"ADJ{datetime.now().strftime('%Y%m%d%H%M%S')}{user_id}"
    cursor.execute('''
        INSERT INTO transactions (id, sender_id, receiver_id, amount, note, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (txn_id, None, user_id, abs(amount), f'Admin adjustment: {reason}', 'success', datetime.now()))
    
    db.commit()
    
    return jsonify({
        'message': f'Balance adjusted by ₹{abs(amount)} {"added" if amount > 0 else "deducted"}',
        'new_balance': new_balance
    })


@admin_bp.route('/api/users/<int:user_id>/reset_pin', methods=['POST'])
@admin_login_required
def reset_user_pin(user_id):
    """Reset user's PIN (sets to default '1234')"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('SELECT id, name FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Reset PIN to default '1234'
    import hashlib
    default_pin_hash = hashlib.sha256('1234'.encode()).hexdigest()
    cursor.execute('UPDATE users SET pin = ? WHERE id = ?', (default_pin_hash, user_id))
    db.commit()
    
    return jsonify({'message': f'PIN reset to default (1234) for user {user["name"]}'})


# ====================
# TRANSACTIONS API
# ====================

@admin_bp.route('/api/transactions')
@admin_login_required
def get_all_transactions():
    """Get all transactions with user details"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT t.*, 
               u1.name as sender_name, u1.phone as sender_phone,
               u2.name as receiver_name, u2.phone as receiver_phone
        FROM transactions t
        LEFT JOIN users u1 ON t.sender_id = u1.id
        LEFT JOIN users u2 ON t.receiver_id = u2.id
        ORDER BY t.created_at DESC
        LIMIT 200
    ''')
    
    transactions = []
    for row in cursor.fetchall():
        transactions.append({
            'id': row['id'],
            'amount': float(row['amount']),
            'note': row['note'] or '',
            'status': row['status'] or 'success',
            'created_at': row['created_at'],
            'sender_name': row['sender_name'] or row['sender_phone'] or 'System',
            'receiver_name': row['receiver_name'] or row['receiver_phone'] or 'External',
            'fraud_flag': bool(row['fraud_flag'] or 0)
        })
    
    return jsonify(transactions)


@admin_bp.route('/api/transactions/<string:txn_id>')
@admin_login_required
def get_transaction_details(txn_id):
    """Get single transaction details"""
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
    ''', (txn_id,))
    
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Transaction not found'}), 404
    
    transaction = {
        'id': row['id'],
        'amount': float(row['amount']),
        'note': row['note'] or '',
        'status': row['status'] or 'success',
        'created_at': row['created_at'],
        'sender_name': row['sender_name'] or row['sender_phone'] or 'System',
        'receiver_name': row['receiver_name'] or row['receiver_phone'] or 'External',
        'fraud_flag': bool(row['fraud_flag'] or 0),
        'sender_id': row['sender_id'],
        'receiver_id': row['receiver_id']
    }
    
    return jsonify(transaction)


@admin_bp.route('/api/transactions/user/<int:user_id>')
@admin_login_required
def get_user_transactions(user_id):
    """Get all transactions for a specific user"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT t.*, 
               u1.name as sender_name, u1.phone as sender_phone,
               u2.name as receiver_name, u2.phone as receiver_phone
        FROM transactions t
        LEFT JOIN users u1 ON t.sender_id = u1.id
        LEFT JOIN users u2 ON t.receiver_id = u2.id
        WHERE t.sender_id = ? OR t.receiver_id = ?
        ORDER BY t.created_at DESC
        LIMIT 100
    ''', (user_id, user_id))
    
    transactions = []
    for row in cursor.fetchall():
        transactions.append({
            'id': row['id'],
            'amount': float(row['amount']),
            'note': row['note'] or '',
            'status': row['status'] or 'success',
            'created_at': row['created_at'],
            'sender_name': row['sender_name'] or row['sender_phone'] or 'System',
            'receiver_name': row['receiver_name'] or row['receiver_phone'] or 'External',
            'is_sent': row['sender_id'] == user_id
        })
    
    return jsonify(transactions)


# ====================
# FRAUD LOGS API
# ====================

@admin_bp.route('/api/fraud_logs')
@admin_login_required
def get_fraud_logs():
    """Get all fraud detection logs"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT f.*, u.name, u.phone
        FROM fraud_logs f
        LEFT JOIN users u ON f.user_id = u.id
        ORDER BY f.created_at DESC
        LIMIT 100
    ''')
    
    logs = []
    for row in cursor.fetchall():
        logs.append({
            'id': row['id'],
            'user_name': row['name'] or 'Unknown',
            'user_phone': row['phone'] or 'Unknown',
            'user_id': row['user_id'],
            'type': row['fraud_type'],
            'details': row['description'],
            'created_at': row['created_at']
        })
    
    return jsonify(logs)


@admin_bp.route('/api/fraud_logs/clear', methods=['POST'])
@admin_login_required
def clear_fraud_logs():
    """Clear all fraud logs (admin only)"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM fraud_logs')
    db.commit()
    return jsonify({'message': 'All fraud logs cleared successfully'})


@admin_bp.route('/api/fraud_logs/<int:log_id>', methods=['DELETE'])
@admin_login_required
def delete_fraud_log(log_id):
    """Delete a single fraud log"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM fraud_logs WHERE id = ?', (log_id,))
    db.commit()
    return jsonify({'message': 'Fraud log deleted successfully'})


# ====================
# STATS API
# ====================

@admin_bp.route('/api/stats')
@admin_login_required
def get_stats():
    """Get dashboard statistics"""
    db = get_db()
    cursor = db.cursor()
    
    # Total users
    cursor.execute('SELECT COUNT(*) as count FROM users')
    total_users = cursor.fetchone()['count']
    
    # Active users (not blocked)
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_blocked = 0')
    active_users = cursor.fetchone()['count']
    
    # Blocked users
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE is_blocked = 1')
    blocked_users = cursor.fetchone()['count']
    
    # Total transactions and volume
    cursor.execute('SELECT COUNT(*) as count, SUM(amount) as total FROM transactions WHERE status = "success"')
    result = cursor.fetchone()
    total_transactions = result['count'] or 0
    total_volume = float(result['total'] or 0)
    
    # Total cashback given (using cashback_history table)
    cursor.execute('SELECT SUM(cashback_amount) as total FROM cashback_history')
    cashback_result = cursor.fetchone()
    total_cashback = float(cashback_result['total'] or 0)
    
    # Fraud logs count
    cursor.execute('SELECT COUNT(*) as count FROM fraud_logs')
    fraud_count = cursor.fetchone()['count']
    
    # Today's transactions
    cursor.execute('''
        SELECT COUNT(*) as count, SUM(amount) as total 
        FROM transactions 
        WHERE date(created_at) = date('now') AND status = 'success'
    ''')
    today_result = cursor.fetchone()
    today_transactions = today_result['count'] or 0
    today_volume = float(today_result['total'] or 0)
    
    # This week's transactions
    cursor.execute('''
        SELECT COUNT(*) as count, SUM(amount) as total 
        FROM transactions 
        WHERE date(created_at) >= date('now', '-7 days') AND status = 'success'
    ''')
    week_result = cursor.fetchone()
    week_volume = float(week_result['total'] or 0)
    
    # Average transaction amount
    avg_transaction = total_volume / total_transactions if total_transactions > 0 else 0
    
    # New users this week
    cursor.execute('''
        SELECT COUNT(*) as count 
        FROM users 
        WHERE date(created_at) >= date('now', '-7 days')
    ''')
    new_users_week = cursor.fetchone()['count'] or 0
    
    return jsonify({
        'total_users': total_users,
        'active_users': active_users,
        'blocked_users': blocked_users,
        'total_transactions': total_transactions,
        'total_volume': total_volume,
        'total_cashback': total_cashback,
        'fraud_count': fraud_count,
        'today_transactions': today_transactions,
        'today_volume': today_volume,
        'week_volume': week_volume,
        'avg_transaction': avg_transaction,
        'new_users_week': new_users_week
    })


@admin_bp.route('/api/stats/daily')
@admin_login_required
def get_daily_stats():
    """Get daily transaction stats for chart"""
    db = get_db()
    cursor = db.cursor()
    
    # Last 14 days
    cursor.execute('''
        SELECT date(created_at) as day, 
               COUNT(*) as count, 
               SUM(amount) as total
        FROM transactions 
        WHERE date(created_at) >= date('now', '-13 days')
        GROUP BY date(created_at)
        ORDER BY day ASC
    ''')
    
    stats = []
    for row in cursor.fetchall():
        stats.append({
            'date': row['day'],
            'count': row['count'] or 0,
            'volume': float(row['total'] or 0)
        })
    
    return jsonify(stats)


# ====================
# CONTACTS API (Admin View)
# ====================

@admin_bp.route('/api/contacts')
@admin_login_required
def get_all_contacts():
    """Get all user contacts (for admin monitoring)"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT c.*, u.name as user_name, u.phone as user_phone
        FROM contacts c
        LEFT JOIN users u ON c.user_id = u.id
        ORDER BY c.created_at DESC
        LIMIT 200
    ''')
    
    contacts = []
    for row in cursor.fetchall():
        contacts.append({
            'id': row['id'],
            'user_name': row['user_name'] or 'Unknown',
            'user_phone': row['user_phone'],
            'contact_name': row['contact_name'],
            'contact_phone': row['contact_phone'],
            'is_favorite': bool(row['is_favorite'] or 0),
            'created_at': row['created_at']
        })
    
    return jsonify(contacts)


# ====================
# REFERRAL API (Admin View)
# ====================

@admin_bp.route('/api/referrals')
@admin_login_required
def get_all_referrals():
    """Get all referral relationships"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT u.id, u.name, u.phone, u.referral_code, u.referred_by, u.created_at,
               (SELECT COUNT(*) FROM users WHERE referred_by = u.referral_code) as referral_count
        FROM users u
        WHERE u.referred_by IS NOT NULL OR u.referral_code IS NOT NULL
        ORDER BY u.created_at DESC
    ''')
    
    referrals = []
    for row in cursor.fetchall():
        referrals.append({
            'user_id': row['id'],
            'user_name': row['name'],
            'user_phone': row['phone'],
            'referral_code': row['referral_code'],
            'referred_by': row['referred_by'],
            'referral_count': row['referral_count'] or 0,
            'joined': row['created_at']
        })
    
    return jsonify(referrals)


# ====================
# SYSTEM API
# ====================

@admin_bp.route('/api/system_info')
@admin_login_required
def get_system_info():
    """Get system information"""
    db = get_db()
    cursor = db.cursor()
    
    # Database size
    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    db_size = cursor.fetchone()
    
    # Table counts
    tables = ['users', 'transactions', 'contacts', 'fraud_logs', 'cashback_history', 'otp']
    table_stats = {}
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
            table_stats[table] = cursor.fetchone()['count'] or 0
        except:
            table_stats[table] = 0
    
    return jsonify({
        'database_size_kb': round((db_size['size'] if db_size else 0) / 1024, 2),
        'table_stats': table_stats,
        'server_time': datetime.now().isoformat()
    })


# ====================
# SEARCH API
# ====================

@admin_bp.route('/api/search')
@admin_login_required
def global_search():
    """Search across users and transactions"""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({'error': 'Search query too short'}), 400
    
    db = get_db()
    cursor = db.cursor()
    
    # Search users
    cursor.execute('''
        SELECT id, name, phone, wallet_balance, is_blocked
        FROM users 
        WHERE name LIKE ? OR phone LIKE ?
        LIMIT 20
    ''', (f'%{query}%', f'%{query}%'))
    users = []
    for row in cursor.fetchall():
        users.append({
            'type': 'user',
            'id': row['id'],
            'name': row['name'],
            'phone': row['phone'],
            'balance': float(row['wallet_balance']),
            'is_blocked': bool(row['is_blocked'] or 0)
        })
    
    # Search transactions
    cursor.execute('''
        SELECT t.id, t.amount, t.note, t.created_at, t.status,
               u1.name as sender_name, u2.name as receiver_name
        FROM transactions t
        LEFT JOIN users u1 ON t.sender_id = u1.id
        LEFT JOIN users u2 ON t.receiver_id = u2.id
        WHERE t.id LIKE ? OR t.note LIKE ?
        LIMIT 20
    ''', (f'%{query}%', f'%{query}%'))
    transactions = []
    for row in cursor.fetchall():
        transactions.append({
            'type': 'transaction',
            'id': row['id'],
            'amount': float(row['amount']),
            'note': row['note'],
            'date': row['created_at'],
            'status': row['status'],
            'sender': row['sender_name'] or 'System',
            'receiver': row['receiver_name'] or 'External'
        })
    
    return jsonify({
        'query': query,
        'users': users,
        'transactions': transactions,
        'total_results': len(users) + len(transactions)
    })