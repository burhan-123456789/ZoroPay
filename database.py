import sqlite3
from flask import g
import random
import string

DATABASE = 'zoropay.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    from app import app
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Users table with all new columns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                name TEXT,
                wallet_balance REAL DEFAULT 100.0,
                pin TEXT DEFAULT '1234',
                referral_code TEXT UNIQUE,
                referred_by TEXT,
                upi_id TEXT,
                api_key TEXT,
                api_usage_count INTEGER DEFAULT 0,
                last_api_used TIMESTAMP,
                daily_limit_used REAL DEFAULT 0,
                cashback_earned REAL DEFAULT 0,
                is_blocked INTEGER DEFAULT 0,
                biometric_enabled INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Virtual Cards table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS virtual_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                card_number TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                cvv TEXT NOT NULL,
                card_holder_name TEXT NOT NULL,
                card_type TEXT DEFAULT 'virtual',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')
        
        # Add index for virtual cards
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_virtual_cards_user_id ON virtual_cards(user_id)')
        
        # Add new columns to users table if they don't exist
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        column_names = [col['name'] for col in columns]
        
        if 'upi_id' not in column_names:
            cursor.execute("ALTER TABLE users ADD COLUMN upi_id TEXT")
            db.commit()
            print("upi_id column added to users table")
        
        if 'api_key' not in column_names:
            cursor.execute("ALTER TABLE users ADD COLUMN api_key TEXT")
            db.commit()
            print("api_key column added to users table")
        
        if 'api_usage_count' not in column_names:
            cursor.execute("ALTER TABLE users ADD COLUMN api_usage_count INTEGER DEFAULT 0")
            db.commit()
            print("api_usage_count column added to users table")
        
        if 'last_api_used' not in column_names:
            cursor.execute("ALTER TABLE users ADD COLUMN last_api_used TIMESTAMP")
            db.commit()
            print("last_api_used column added to users table")
        
        if 'daily_limit_used' not in column_names:
            cursor.execute("ALTER TABLE users ADD COLUMN daily_limit_used REAL DEFAULT 0")
            db.commit()
            print("daily_limit_used column added to users table")
        
        if 'cashback_earned' not in column_names:
            cursor.execute("ALTER TABLE users ADD COLUMN cashback_earned REAL DEFAULT 0")
            db.commit()
            print("cashback_earned column added to users table")
        
        if 'is_blocked' not in column_names:
            cursor.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
            db.commit()
            print("is_blocked column added to users table")
        
        if 'referred_by' not in column_names:
            cursor.execute("ALTER TABLE users ADD COLUMN referred_by TEXT")
            db.commit()
            print("referred_by column added to users table")
        
        if 'biometric_enabled' not in column_names:
            cursor.execute("ALTER TABLE users ADD COLUMN biometric_enabled INTEGER DEFAULT 0")
            db.commit()
            print("biometric_enabled column added to users table")
        
        # Create unique index for upi_id after adding column
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_upi_id ON users(upi_id) WHERE upi_id IS NOT NULL")
            db.commit()
            print("Unique index for upi_id created")
        except Exception as e:
            print(f"Note: {e}")
        
        # Create unique index for api_key
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key) WHERE api_key IS NOT NULL")
            db.commit()
            print("Unique index for api_key created")
        except Exception as e:
            print(f"Note: {e}")
        
        # Biometric Credentials table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS biometric_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                credential_id TEXT UNIQUE NOT NULL,
                public_key TEXT NOT NULL,
                device_name TEXT DEFAULT 'WebAuthn Device',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')
        
        # Add index for biometric queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_biometric_user_id ON biometric_credentials(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_biometric_credential_id ON biometric_credentials(credential_id)')
        
        # Transactions table with fraud_flag
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                sender_id INTEGER,
                receiver_id INTEGER,
                sender_phone TEXT,
                receiver_phone TEXT,
                amount REAL,
                note TEXT,
                status TEXT DEFAULT 'success',
                fraud_flag INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sender_id) REFERENCES users (id),
                FOREIGN KEY (receiver_id) REFERENCES users (id)
            )
        ''')
        
        # Add fraud_flag column if missing
        cursor.execute("PRAGMA table_info(transactions)")
        txn_columns = cursor.fetchall()
        txn_column_names = [col['name'] for col in txn_columns]
        
        if 'fraud_flag' not in txn_column_names:
            cursor.execute("ALTER TABLE transactions ADD COLUMN fraud_flag INTEGER DEFAULT 0")
            db.commit()
            print("fraud_flag column added to transactions table")
        
        if 'status' not in txn_column_names:
            cursor.execute("ALTER TABLE transactions ADD COLUMN status TEXT DEFAULT 'success'")
            db.commit()
            print("status column added to transactions table")
        
        if 'sender_phone' not in txn_column_names:
            cursor.execute("ALTER TABLE transactions ADD COLUMN sender_phone TEXT")
            db.commit()
            print("sender_phone column added to transactions table")
        
        if 'receiver_phone' not in txn_column_names:
            cursor.execute("ALTER TABLE transactions ADD COLUMN receiver_phone TEXT")
            db.commit()
            print("receiver_phone column added to transactions table")
        
        # Contacts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                contact_phone TEXT NOT NULL,
                contact_name TEXT,
                contact_type TEXT DEFAULT 'internal',
                is_favorite INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, contact_phone)
            )
        ''')
        
        # Check contacts table for missing columns
        cursor.execute("PRAGMA table_info(contacts)")
        contact_columns = cursor.fetchall()
        contact_column_names = [col['name'] for col in contact_columns]
        
        if 'is_favorite' not in contact_column_names:
            cursor.execute("ALTER TABLE contacts ADD COLUMN is_favorite INTEGER DEFAULT 0")
            db.commit()
            print("is_favorite column added to contacts")
        
        if 'contact_type' not in contact_column_names:
            cursor.execute("ALTER TABLE contacts ADD COLUMN contact_type TEXT DEFAULT 'internal'")
            db.commit()
            print("contact_type column added to contacts")
        
        # Rewards table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                reference_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Notifications table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                type TEXT DEFAULT 'info',
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Add type column to notifications if missing
        cursor.execute("PRAGMA table_info(notifications)")
        notif_columns = cursor.fetchall()
        notif_column_names = [col['name'] for col in notif_columns]
        
        if 'type' not in notif_column_names:
            cursor.execute("ALTER TABLE notifications ADD COLUMN type TEXT DEFAULT 'info'")
            db.commit()
            print("type column added to notifications")
        
        # OTP table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS otp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                otp TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Fraud logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fraud_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                fraud_type TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Cashback history table with claimed and claimed_at columns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cashback_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_amount REAL,
                cashback_amount REAL,
                percentage REAL,
                claimed INTEGER DEFAULT 0,
                claimed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Add claimed columns if missing
        cursor.execute("PRAGMA table_info(cashback_history)")
        cashback_columns = cursor.fetchall()
        cashback_column_names = [col['name'] for col in cashback_columns]
        
        if 'claimed' not in cashback_column_names:
            cursor.execute("ALTER TABLE cashback_history ADD COLUMN claimed INTEGER DEFAULT 0")
            db.commit()
            print("claimed column added to cashback_history")
        
        if 'claimed_at' not in cashback_column_names:
            cursor.execute("ALTER TABLE cashback_history ADD COLUMN claimed_at TIMESTAMP")
            db.commit()
            print("claimed_at column added to cashback_history")
        
        # External requests table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS external_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_id INTEGER,
                target_phone TEXT,
                amount REAL,
                note TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (requester_id) REFERENCES users (id)
            )
        ''')
        
        db.commit()
        
        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_sender_id ON transactions(sender_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_receiver_id ON transactions(receiver_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_sender_phone ON transactions(sender_phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_receiver_phone ON transactions(receiver_phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_contact_phone ON contacts(contact_phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fraud_logs_user_id ON fraud_logs(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cashback_history_user_id ON cashback_history(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cashback_history_claimed ON cashback_history(claimed)')
        db.commit()
        
        # Update existing users with UPI IDs if missing
        cursor.execute('SELECT id, name, phone FROM users WHERE upi_id IS NULL')
        users_without_upi = cursor.fetchall()
        
        for user in users_without_upi:
            username = user['name'].lower().replace(' ', '') if user['name'] else 'user'
            base = f"{username}{user['phone'][-4:]}"
            upi_id = f"{base}@zoropay"
            
            # Make sure UPI ID is unique
            counter = 1
            original_upi_id = upi_id
            while True:
                cursor.execute('SELECT id FROM users WHERE upi_id = ?', (upi_id,))
                if not cursor.fetchone():
                    break
                upi_id = f"{original_upi_id}{counter}"
                counter += 1
            
            cursor.execute('UPDATE users SET upi_id = ? WHERE id = ?', (upi_id, user['id']))
        
        db.commit()
        print(f"Updated {len(users_without_upi)} users with UPI IDs")
        
        # Generate virtual cards for users who don't have them
        cursor.execute('''
            SELECT id, name, phone FROM users 
            WHERE id NOT IN (SELECT user_id FROM virtual_cards)
        ''')
        users_without_card = cursor.fetchall()
        
        for user in users_without_card:
            generate_virtual_card_for_user(user['id'], user['name'])
        
        print(f"Generated virtual cards for {len(users_without_card)} users")
        
        print("Database initialized successfully with all tables and columns")

def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# ====================
# VIRTUAL CARD HELPER FUNCTIONS
# ====================

def generate_card_number():
    """Generate a unique 16-digit virtual card number"""
    prefix = random.choice(['4', '5'])
    remaining = ''.join([str(random.randint(0, 9)) for _ in range(15)])
    card_number = prefix + remaining
    
    def luhn_checksum(card_num):
        def digits_of(n):
            return [int(d) for d in str(n)]
        digits = digits_of(card_num)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(digits_of(d * 2))
        return checksum % 10
    
    checksum = luhn_checksum(card_number[:-1]) * 9 % 10
    card_number = card_number[:-1] + str(checksum)
    
    return card_number

def generate_expiry_date():
    """Generate expiry date (3 years from now)"""
    from datetime import datetime, timedelta
    expiry = datetime.now() + timedelta(days=3*365)
    return expiry.strftime("%m/%y")

def generate_cvv():
    """Generate 3-digit CVV"""
    return ''.join([str(random.randint(0, 9)) for _ in range(3)])

def generate_virtual_card_for_user(user_id, user_name):
    """Generate and store virtual card for a user"""
    db = get_db()
    cursor = db.cursor()
    
    card_number = generate_card_number()
    expiry_date = generate_expiry_date()
    cvv = generate_cvv()
    
    card_holder_name = user_name.upper()[:22] if user_name else f"CARDHOLDER{user_id}"
    
    cursor.execute('''
        INSERT OR REPLACE INTO virtual_cards (user_id, card_number, expiry_date, cvv, card_holder_name)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, card_number, expiry_date, cvv, card_holder_name))
    
    db.commit()
    return {
        'card_number': card_number,
        'expiry_date': expiry_date,
        'cvv': cvv,
        'card_holder_name': card_holder_name
    }

def get_virtual_card(user_id):
    """Get virtual card details for a user - returns dictionary"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT card_number, expiry_date, cvv, card_holder_name, card_type, is_active, created_at
        FROM virtual_cards 
        WHERE user_id = ? AND is_active = 1
    ''', (user_id,))
    
    row = cursor.fetchone()
    if row:
        return {
            'card_number': row['card_number'],
            'expiry_date': row['expiry_date'],
            'cvv': row['cvv'],
            'card_holder_name': row['card_holder_name'],
            'card_type': row['card_type'],
            'is_active': row['is_active'],
            'created_at': row['created_at']
        }
    return None

def regenerate_virtual_card(user_id, user_name):
    """Regenerate virtual card with new details"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('UPDATE virtual_cards SET is_active = 0 WHERE user_id = ?', (user_id,))
    
    return generate_virtual_card_for_user(user_id, user_name)

# ====================
# BIOMETRIC HELPER FUNCTIONS
# ====================

def get_biometric_credentials(user_id):
    """Get all active biometric credentials for a user"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT id, credential_id, device_name, is_active, created_at, last_used
        FROM biometric_credentials 
        WHERE user_id = ? AND is_active = 1
        ORDER BY created_at DESC
    ''', (user_id,))
    return cursor.fetchall()

def get_biometric_credential_by_id(credential_id):
    """Get biometric credential by credential_id"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT bc.*, u.phone, u.name 
        FROM biometric_credentials bc
        JOIN users u ON bc.user_id = u.id
        WHERE bc.credential_id = ? AND bc.is_active = 1
    ''', (credential_id,))
    return cursor.fetchone()

def register_biometric_credential(user_id, credential_id, public_key, device_name='WebAuthn Device'):
    """Register a new biometric credential for a user"""
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO biometric_credentials (user_id, credential_id, public_key, device_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, credential_id, public_key, device_name))
        
        cursor.execute('UPDATE users SET biometric_enabled = 1 WHERE id = ?', (user_id,))
        
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def disable_biometric_credential(user_id, credential_id):
    """Disable a biometric credential (soft delete)"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        UPDATE biometric_credentials 
        SET is_active = 0 
        WHERE user_id = ? AND credential_id = ?
    ''', (user_id, credential_id))
    
    cursor.execute('''
        SELECT COUNT(*) as count FROM biometric_credentials 
        WHERE user_id = ? AND is_active = 1
    ''', (user_id,))
    
    result = cursor.fetchone()
    if result['count'] == 0:
        cursor.execute('UPDATE users SET biometric_enabled = 0 WHERE id = ?', (user_id,))
    
    db.commit()
    return cursor.rowcount > 0

def disable_all_biometric_credentials(user_id):
    """Disable all biometric credentials for a user"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        UPDATE biometric_credentials 
        SET is_active = 0 
        WHERE user_id = ?
    ''', (user_id,))
    
    cursor.execute('UPDATE users SET biometric_enabled = 0 WHERE id = ?', (user_id,))
    db.commit()
    return True

def update_biometric_last_used(credential_id):
    """Update the last used timestamp for a biometric credential"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        UPDATE biometric_credentials 
        SET last_used = CURRENT_TIMESTAMP 
        WHERE credential_id = ?
    ''', (credential_id,))
    db.commit()

def is_biometric_enabled(user_id):
    """Check if user has biometric enabled"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT biometric_enabled FROM users WHERE id = ?', (user_id,))
    result = cursor.fetchone()
    return result['biometric_enabled'] == 1 if result else False

# ====================
# CONTACT HELPER FUNCTIONS
# ====================

def add_contact(user_id, contact_phone, contact_name, contact_type='internal'):
    """Add a contact for a user"""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('''
            INSERT INTO contacts (user_id, contact_phone, contact_name, contact_type)
            VALUES (?, ?, ?, ?)
        ''', (user_id, contact_phone, contact_name, contact_type))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def get_user_contacts(user_id):
    """Get all contacts for a user"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT c.*, u.name as registered_name, u.id as registered_id
        FROM contacts c
        LEFT JOIN users u ON c.contact_phone = u.phone
        WHERE c.user_id = ?
        ORDER BY c.is_favorite DESC, c.contact_name ASC
    ''', (user_id,))
    return cursor.fetchall()

def get_favorite_contacts(user_id):
    """Get favorite contacts for a user"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT c.*, u.name as registered_name
        FROM contacts c
        LEFT JOIN users u ON c.contact_phone = u.phone
        WHERE c.user_id = ? AND c.is_favorite = 1
        ORDER BY c.contact_name ASC
    ''', (user_id,))
    return cursor.fetchall()

def update_contact_favorite(contact_id, user_id, is_favorite):
    """Update contact favorite status"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        UPDATE contacts SET is_favorite = ? 
        WHERE id = ? AND user_id = ?
    ''', (is_favorite, contact_id, user_id))
    db.commit()
    return True

def delete_contact(contact_id, user_id):
    """Delete a contact"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM contacts WHERE id = ? AND user_id = ?', (contact_id, user_id))
    db.commit()
    return cursor.rowcount > 0

def update_contact(contact_id, user_id, contact_name):
    """Update contact name"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        UPDATE contacts SET contact_name = ? 
        WHERE id = ? AND user_id = ?
    ''', (contact_name, contact_id, user_id))
    db.commit()
    return cursor.rowcount > 0

def generate_referral_code():
    """Generate a unique referral code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def validate_referral_code(referral_code):
    """Validate if referral code exists and return the referrer user"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, name, phone FROM users WHERE referral_code = ?', (referral_code,))
    return cursor.fetchone()

def apply_referral_bonus(new_user_id, referrer_id):
    """Apply ₹250 bonus to both new user and referrer"""
    db = get_db()
    cursor = db.cursor()
    bonus_amount = 250.0
    
    try:
        cursor.execute('UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?', 
                      (bonus_amount, new_user_id))
        
        cursor.execute('UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?', 
                      (bonus_amount, referrer_id))
        
        cursor.execute('''
            INSERT INTO rewards (user_id, type, amount, reference_id)
            VALUES (?, ?, ?, ?)
        ''', (new_user_id, 'welcome_bonus', bonus_amount, f'referred_by_{referrer_id}'))
        
        cursor.execute('''
            INSERT INTO rewards (user_id, type, amount, reference_id)
            VALUES (?, ?, ?, ?)
        ''', (referrer_id, 'referral_bonus', bonus_amount, f'referred_user_{new_user_id}'))
        
        db.commit()
        return True
    except Exception as e:
        print(f"Error applying referral bonus: {e}")
        db.rollback()
        return False

# ====================
# CASHBACK HELPER FUNCTIONS (UPDATED)
# ====================

def calculate_cashback(amount):
    """Calculate cashback based on transaction amount
    - Amount <= 20: 0% cashback (no cashback)
    - Amount <= 50: 1% cashback
    - Amount >= 100: 1.5% cashback
    """
    if amount <= 20:
        percentage = 0
        cashback_amount = 0
    elif amount <= 50:
        percentage = 1.0
        cashback_amount = round(amount * 1.0 / 100, 2)
    else:  # amount >= 100
        percentage = 1.5
        cashback_amount = round(amount * 1.5 / 100, 2)
    
    # Cap cashback at ₹500 per transaction
    cashback_amount = min(cashback_amount, 500)
    
    return cashback_amount, percentage

def add_cashback(user_id, amount):
    """Add cashback to user's pending cashback (not auto-added to wallet)"""
    cashback_amount, percentage = calculate_cashback(amount)
    
    if cashback_amount > 0:
        db = get_db()
        cursor = db.cursor()
        
        # Store in cashback_history as unclaimed
        cursor.execute('''
            INSERT INTO cashback_history (user_id, transaction_amount, cashback_amount, percentage, claimed)
            VALUES (?, ?, ?, ?, 0)
        ''', (user_id, amount, cashback_amount, percentage))
        
        # Update total cashback earned in users table
        cursor.execute('UPDATE users SET cashback_earned = cashback_earned + ? WHERE id = ?', 
                      (cashback_amount, user_id))
        
        db.commit()
        
        return cashback_amount, percentage
    
    return 0, 0

def get_pending_cashback(user_id):
    """Get total pending cashback amount for user"""
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        SELECT SUM(cashback_amount) as total, COUNT(*) as count
        FROM cashback_history 
        WHERE user_id = ? AND claimed = 0
    ''', (user_id,))
    
    result = cursor.fetchone()
    return float(result['total'] or 0), result['count'] or 0

def get_cashback_history(user_id, include_claimed=True):
    """Get cashback history for user"""
    db = get_db()
    cursor = db.cursor()
    
    if include_claimed:
        cursor.execute('''
            SELECT * FROM cashback_history 
            WHERE user_id = ? 
            ORDER BY created_at DESC
            LIMIT 100
        ''', (user_id,))
    else:
        cursor.execute('''
            SELECT * FROM cashback_history 
            WHERE user_id = ? AND claimed = 0
            ORDER BY created_at DESC
        ''', (user_id,))
    
    return cursor.fetchall()

def claim_pending_cashback(user_id):
    """Claim all pending cashback and add to wallet"""
    db = get_db()
    cursor = db.cursor()
    
    # Get total pending
    pending_total, count = get_pending_cashback(user_id)
    
    if pending_total <= 0:
        return 0, 0
    
    # Update user wallet balance
    cursor.execute('''
        UPDATE users 
        SET wallet_balance = wallet_balance + ? 
        WHERE id = ?
    ''', (pending_total, user_id))
    
    # Mark cashback as claimed
    from datetime import datetime
    cursor.execute('''
        UPDATE cashback_history 
        SET claimed = 1, claimed_at = ?
        WHERE user_id = ? AND claimed = 0
    ''', (datetime.now(), user_id))
    
    db.commit()
    
    return pending_total, count