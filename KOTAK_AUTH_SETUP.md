# KOTAK NEO Authentication Setup Guide

## ✅ Implementation Updated!

The KOTAK NEO broker has been updated to match the **official documentation** for authentication.

---

## 🔑 Required Credentials (Updated)

You need **5 credentials** to authenticate with KOTAK NEO:

### **1. Access Token (from NEO Dashboard)**
- **What**: API access token from your NEO application
- **Where to get**: 
  1. Login to NEO App
  2. Go to **Invest → Trade API**
  3. Create an app under **Your Applications**
  4. Copy the **access token** shown
- **Format**: Plain token string (e.g., `abc123xyz...`)
- **Environment variable**: `KOTAK_ACCESS_TOKEN`

### **2. Mobile Number**
- **What**: Your registered mobile number with ISD code
- **Format**: `+919876543210` (must include `+91`)
- **Environment variable**: `KOTAK_MOBILE_NUMBER`

### **3. UCC (Unique Client Code)**
- **What**: Your client code / client ID
- **Where to get**: From KOTAK Securities account / NEO app
- **Format**: Usually alphanumeric (e.g., `ABC123`)
- **Environment variable**: `KOTAK_UCC`

### **4. TOTP Secret**
- **What**: Secret key for generating Time-based One-Time Passwords
- **Where to get**:
  1. On **API Dashboard**, click **TOTP Registration**
  2. Verify with mobile OTP and client code
  3. Scan QR code with Google/Microsoft Authenticator app
  4. **Important**: Save the **secret key** (usually shown as text below QR)
- **Format**: Base32 encoded string (e.g., `JBSWY3DPEHPK3PXP`)
- **Environment variable**: `KOTAK_TOTP_SECRET`
- **Note**: You need the SECRET KEY, not the 6-digit codes!

### **5. MPIN**
- **What**: Your 6-digit Mobile PIN for trading
- **Where to get**: Set during account setup
- **Format**: 6 digits (e.g., `123456`)
- **Environment variable**: `KOTAK_MPIN`

---

## 📝 Configuration

### **Step 1: Edit .env File**

```bash
# KOTAK NEO Credentials (Updated - Official Documentation)
KOTAK_ACCESS_TOKEN=your_access_token_from_neo_dashboard
KOTAK_MOBILE_NUMBER=+919876543210
KOTAK_UCC=your_client_code
KOTAK_TOTP_SECRET=JBSWY3DPEHPK3PXP
KOTAK_MPIN=123456

# Database (required)
PG_CONN_STR=postgresql://user:pass@host:port/database
```

### **Example .env (with dummy values)**

```bash
KOTAK_ACCESS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
KOTAK_MOBILE_NUMBER=+919876543210
KOTAK_UCC=ABC12345
KOTAK_TOTP_SECRET=JBSWY3DPEHPK3PXP2R3TQRS
KOTAK_MPIN=123456
```

---

## 🧪 Testing Authentication

### **Step 1: Install Dependencies**

```bash
pip install -r requirements.txt
```

This installs the new `pyotp` package for TOTP generation.

### **Step 2: Test Authentication**

```bash
python main.py --broker kotak --test-broker
```

### **Expected Output (Success)**

```
[INFO] === Broker Data Feed Service Starting ===
[INFO] Initializing KOTAK broker...
[INFO] Authenticating with KOTAK NEO API...
[INFO] Generated TOTP: 123456
[INFO] Step 1: Logging in with TOTP to https://mis.kotaksecurities.com/login/1.0/tradeApiLogin
[SUCCESS] Step 1: Login with TOTP successful
[INFO] Step 2: Validating MPIN to https://mis.kotaksecurities.com/login/1.0/tradeApiValidate
[SUCCESS] Step 2: MPIN validation successful
[SUCCESS] Session token obtained (kType: Trade)
[INFO] Base URL: https://cis.kotaksecurities.com
[SUCCESS] Broker test successful
```

---

## 🔧 Authentication Flow (Updated)

The implementation now follows the **official 2-step authentication**:

### **Step 1: Login with TOTP**
```
POST https://mis.kotaksecurities.com/login/1.0/tradeApiLogin

Headers:
  - Authorization: <access_token>
  - neo-fin-key: neotradeapi
  - Content-Type: application/json

Body:
  {
    "mobileNumber": "+919876543210",
    "ucc": "ABC123",
    "totp": "123456"  // Generated dynamically using TOTP secret
  }

Response:
  - View Token (token)
  - Session ID (sid)
  - Request ID (rid)
```

### **Step 2: Validate with MPIN**
```
POST https://mis.kotaksecurities.com/login/1.0/tradeApiValidate

Headers:
  - Authorization: <access_token>
  - neo-fin-key: neotradeapi
  - sid: <view_sid_from_step1>
  - Auth: <view_token_from_step1>
  - Content-Type: application/json

Body:
  {
    "mpin": "123456"
  }

Response:
  - Trade Token (token)
  - Session ID (sid)
  - Base URL (baseUrl) - for subsequent API calls
  - kType: "Trade"
```

---

## ❓ Troubleshooting

### **Issue: "Invalid credentials or TOTP"**

**Causes**:
- Access token is wrong or expired
- Mobile number format is incorrect (missing +91)
- UCC is wrong
- TOTP secret is wrong or TOTP generation failed

**Solution**:
1. Verify access token from NEO dashboard
2. Ensure mobile number has +91 prefix
3. Confirm UCC from KOTAK account
4. Re-register TOTP and get new secret key

### **Issue: "Invalid MPIN"**

**Causes**:
- MPIN is incorrect
- MPIN is expired

**Solution**:
1. Verify 6-digit MPIN
2. Reset MPIN in NEO app if needed

### **Issue: "TOTP generation failed"**

**Causes**:
- TOTP secret is invalid
- System clock is out of sync

**Solution**:
1. Verify TOTP secret is correct Base32 string
2. Sync your system clock
3. Test TOTP generation: `python -c "import pyotp; print(pyotp.TOTP('YOUR_SECRET').now())"`

### **Issue: "Connection timeout"**

**Causes**:
- Network connectivity issue
- Firewall blocking requests

**Solution**:
1. Check internet connection
2. Test URL manually: `curl https://mis.kotaksecurities.com`
3. Check firewall settings

---

## 📊 What Changed?

| Component | Old (Incorrect) | New (Official Docs) |
|-----------|----------------|---------------------|
| **Authentication** | Password + MPIN | **TOTP + MPIN** |
| **Endpoints** | `/login/v2/validate` | `/tradeApiLogin` + `/tradeApiValidate` |
| **Headers** | `Bearer key:secret` | Plain token + `neo-fin-key` |
| **Credentials** | consumer_key, consumer_secret, password | **access_token, ucc, totp_secret** |
| **Base URL** | gw-napi.kotaksecurities.com | **mis.kotaksecurities.com** |

---

## 🎯 Next Steps

1. ✅ **Install dependencies**: `pip install -r requirements.txt`
2. ✅ **Get TOTP secret**: Register TOTP in NEO dashboard
3. ✅ **Configure .env**: Add all 5 credentials
4. ✅ **Test authentication**: `python main.py --broker kotak --test-broker`
5. ⏳ **Wait for WebSocket confirmation**: Then we'll implement quotes/streaming

---

## 📚 Reference

Based on official KOTAK NEO documentation:
- **Authentication.txt**: 2-step TOTP + MPIN authentication
- **Quotes.txt**: REST API for market quotes

---

## 💡 Important Notes

1. **TOTP Secret vs TOTP Code**:
   - TOTP Secret: Base32 string (one-time setup)
   - TOTP Code: 6-digit number (changes every 30 seconds)
   - You need the SECRET, not the code!

2. **Token Types**:
   - Access Token: From NEO dashboard (long-lived)
   - View Token: From Step 1 (session-specific)
   - Trade Token: From Step 2 (session-specific, for trading)

3. **Mobile Number**:
   - Must include ISD code (+91 for India)
   - Example: `+919876543210` not `9876543210`

4. **Base URL**:
   - Returned in Step 2 response
   - Use this for all subsequent API calls
   - Example: `https://cis.kotaksecurities.com`

---

**Status**: ✅ Authentication flow updated to official documentation  
**Ready for**: Authentication testing  
**Next**: WebSocket/REST implementation (pending confirmation)

**Test Command**: `python main.py --broker kotak --test-broker`
