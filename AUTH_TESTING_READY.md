# KOTAK NEO Authentication - READY FOR TESTING! ✅

## ✅ What's Updated

The KOTAK NEO broker implementation has been **completely updated** to match the official documentation:

### **Changes Made**

1. **✅ Authentication Flow** - Now uses official 2-step TOTP + MPIN
2. **✅ API Endpoints** - Corrected to use official URLs
3. **✅ Headers** - Updated to use `neo-fin-key` and plain tokens
4. **✅ Credentials** - Changed from password-based to TOTP-based
5. **✅ Dependencies** - Added `pyotp` for TOTP generation
6. **✅ Syntax** - All files validated successfully

---

## 🔑 Required Credentials (NEW)

Update your `.env` file with these **5 credentials**:

```bash
# KOTAK NEO Authentication (Official Documentation)
KOTAK_ACCESS_TOKEN=your_access_token_from_neo_dashboard
KOTAK_MOBILE_NUMBER=+919876543210
KOTAK_UCC=your_client_code
KOTAK_TOTP_SECRET=your_totp_secret_key
KOTAK_MPIN=123456

# Database
PG_CONN_STR=postgresql://user:pass@host:port/database
```

---

## 📋 How to Get Credentials

### **1. Access Token**
- Login to NEO App → Invest → Trade API
- Create app → Copy access token

### **2. Mobile Number**
- Your registered mobile with +91 prefix
- Example: `+919876543210`

### **3. UCC (Client Code)**
- From your KOTAK account details
- Usually shown in NEO app

### **4. TOTP Secret**
- **CRITICAL**: You need the SECRET KEY, not the 6-digit code!
- Go to API Dashboard → TOTP Registration
- Scan QR with authenticator app
- **Save the secret key** (usually shown as text)
- Format: Base32 string like `JBSWY3DPEHPK3PXP`

### **5. MPIN**
- Your 6-digit trading PIN
- Set during account setup

---

## 🧪 Testing Steps

### **1. Configure Credentials**

Edit `.env` file:
```bash
KOTAK_ACCESS_TOKEN=eyJhbGciOi...  # From NEO dashboard
KOTAK_MOBILE_NUMBER=+919876543210
KOTAK_UCC=ABC12345
KOTAK_TOTP_SECRET=JBSWY3DPEHPK3PXP  # From TOTP registration
KOTAK_MPIN=123456
```

### **2. Test Authentication**

```bash
python main.py --broker kotak --test-broker
```

### **3. Expected Output**

```
[INFO] Authenticating with KOTAK NEO API...
[INFO] Generated TOTP: 123456
[INFO] Step 1: Logging in with TOTP
[SUCCESS] Step 1: Login with TOTP successful
[INFO] Step 2: Validating MPIN
[SUCCESS] Step 2: MPIN validation successful
[SUCCESS] Session token obtained (kType: Trade)
[INFO] Base URL: https://cis.kotaksecurities.com
[SUCCESS] Broker test successful
```

---

## 🔄 Authentication Flow

```
Step 1: Login with TOTP
  → POST https://mis.kotaksecurities.com/login/1.0/tradeApiLogin
  → Headers: Authorization (access_token), neo-fin-key
  → Body: mobileNumber, ucc, totp (generated from secret)
  → Response: View Token + sid

Step 2: Validate MPIN
  → POST https://mis.kotaksecurities.com/login/1.0/tradeApiValidate
  → Headers: Authorization, neo-fin-key, sid, Auth (view token)
  → Body: mpin
  → Response: Trade Token + sid + baseUrl
```

---

## ⚠️ Important Notes

### **TOTP Secret vs TOTP Code**
- ❌ **TOTP Code**: 6-digit number (123456) - changes every 30 seconds
- ✅ **TOTP Secret**: Base32 string (JBSWY3DPEHPK3PXP) - used to generate codes
- **You need the SECRET**, not the code!

### **Mobile Number Format**
- Must include `+91` prefix
- ✅ Correct: `+919876543210`
- ❌ Wrong: `9876543210`

### **Access Token**
- Get from NEO App Dashboard
- Not from any login API
- Plain token, no "Bearer" prefix needed

---

## 🚫 What's NOT Implemented Yet

The following are **pending WebSocket confirmation**:

- ❌ WebSocket connection
- ❌ Subscribe/unsubscribe to instruments
- ❌ Live tick data streaming
- ❌ Real-time quotes

**Current implementation**: Authentication only (Steps 1 & 2)

---

## 📊 Testing Checklist

- [ ] Get access token from NEO dashboard
- [ ] Register TOTP and save secret key
- [ ] Configure all 5 credentials in `.env`
- [ ] Test authentication: `python main.py --broker kotak --test-broker`
- [ ] Verify both steps succeed
- [ ] Check session token and base URL are received
- [ ] Once auth works, we'll implement WebSocket/REST

---

## 🐛 Common Issues

### "Invalid credentials or TOTP"
- Check access token from NEO dashboard
- Verify mobile number has +91
- Confirm UCC is correct
- Re-register TOTP if secret is wrong

### "Invalid MPIN"
- Verify 6-digit MPIN
- Reset MPIN in NEO app if expired

### "TOTP generation failed"
- Check TOTP secret is Base32 format
- Sync system clock
- Test: `python -c "import pyotp; print(pyotp.TOTP('YOUR_SECRET').now())"`

---

## 📁 Files Updated

- ✅ `brokers/kotak_neo_broker.py` - Updated authentication
- ✅ `config/config.py` - New credential structure
- ✅ `requirements.txt` - Added pyotp
- ✅ `.env.example` - Updated template
- ✅ `KOTAK_AUTH_SETUP.md` - Comprehensive guide (NEW)

---

## 🎯 Next Steps

1. **NOW**: Configure `.env` with your credentials
2. **NOW**: Test authentication: `python main.py --broker kotak --test-broker`
3. **NEXT**: Confirm WebSocket availability
4. **THEN**: Implement WebSocket/REST for quotes

---

**Status**: ✅ Ready for authentication testing  
**Test Command**: `python main.py --broker kotak --test-broker`  
**Full Guide**: See `KOTAK_AUTH_SETUP.md`

---

## 📞 Need Help?

1. **Authentication issues**: Check `KOTAK_AUTH_SETUP.md`
2. **Credential setup**: See `.env.example`
3. **TOTP problems**: Ensure you have the SECRET, not the code
4. **Still stuck**: Share the error message!
