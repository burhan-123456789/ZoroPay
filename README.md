# Zoro Pay - Mobile Payment Platform

Zoro Pay is a secure, feature-rich mobile payment platform that allows users to send/receive money, track transactions, earn cashback, and manage virtual cards - all optimized for mobile devices.

## 📱 Features

### Core Features

- **Send/Receive Money**: Instant money transfers between users
- **Wallet Management**: Add balance, track spending, view transaction history
- **QR Code Payments**: Generate and scan QR codes for quick payments
- **Referral System**: Earn bonuses by inviting friends (₹250 for referrer & new user)
- **Cashback Rewards**: Earn cashback on transactions (1-5% based on amount)
- **Virtual Debit Card**: Generate virtual cards for online payments
- **Money Requests**: Request money from other users
- **Contacts Management**: Save and manage frequent contacts

### Security Features

- **PIN Protection**: 4 or 6-digit PIN for transactions
- **Biometric Authentication**: Fingerprint/Face ID support (WebAuthn)
- **Fraud Detection**: Automated fraud detection and blocking
- **Daily Limits**: ₹50,000 daily transaction limit
- **API Key Authentication**: Secure API access for developers
- **Session Management**: Secure session handling with JWT

### Analytics & Tracking

- **Monthly Spending Charts**: Visualize spending patterns
- **Transaction History**: Complete transaction logs with filters
- **Cashback History**: Track earned and claimed cashback
- **Contact-wise Summary**: Transaction summaries per contact

### Mobile Optimization

- **Responsive Design**: Optimized for all mobile screen sizes
- **PWA Support**: Install as native app on mobile devices
- **Desktop Blocking**: Access restricted to mobile devices only
- **SMS Notifications**: Real-time transaction alerts via SMS (Twilio)

## 🚀 Tech Stack

### Backend

- **Framework**: Flask (Python)
- **Database**: SQLite
- **Authentication**: JWT, Session-based
- **SMS Service**: Twilio API
- **QR Generation**: qrcode library
- **PDF Generation**: ReportLab

### Frontend

- **HTML5/CSS3**: Responsive mobile-first design
- **JavaScript**: Dynamic UI interactions
- **Tailwind CSS**: Utility-first styling
- **Chart.js**: Analytics visualizations
- **WebAuthn API**: Biometric authentication

### APIs & Integrations

- **RESTful API**: Complete API for third-party integration
- **WebAuthn**: Biometric authentication support
- **Twilio**: SMS notifications

## 📋 Prerequisites

- Python 3.8+
- pip (Python package manager)
- SQLite3
- Twilio account (for SMS - optional)
- Modern web browser with WebAuthn support (for biometrics)

## 🔧 Installation

### 1. Clone the Repository

```bash
# Clone the repository
git clone https://github.com/burhan-123456789/ZoroPay.git
```
