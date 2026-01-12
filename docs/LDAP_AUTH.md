# LDAP/Active Directory Authentication

## Overview

OpenTranscribe supports LDAP/Active Directory authentication with hybrid capabilities:

- **LDAP users**: Auto-created on first login, by default role "user"
- **Local admin users**: Created manually via registration endpoint with database passwords
- **Priority**: Local users take precedence (if email exists locally, checks local password first)

## Configuration

### Environment Variables

Add the following to your `.env` file:

```env
# Enable LDAP authentication
LDAP_ENABLED=true

# LDAP/AD Server
LDAP_SERVER=ldaps://your-ad-server.domain.com
LDAP_PORT=636
LDAP_USE_SSL=true
LDAP_USE_TLS=false

# Service account for LDAP search (read-only user)
LDAP_BIND_DN=CN=service-account,CN=Users,DC=domain,DC=com
LDAP_BIND_PASSWORD=your-service-account-password

# Search base and filter
LDAP_SEARCH_BASE=DC=domain,DC=com
LDAP_USER_SEARCH_FILTER=(sAMAccountName={username})

# User attributes
LDAP_EMAIL_ATTR=mail
LDAP_NAME_ATTR=cn

# Timeout (seconds)
LDAP_TIMEOUT=10

# Optional: Comma-separated list of AD usernames that should be admins
LDAP_ADMIN_USERS=admin1,admin2,john.doe
```

### Configuration Details

- **LDAP_SERVER**: Full LDAP URL (ldaps:// for secure LDAP)
- **LDAP_PORT**: 389 for standard LDAP, 636 for LDAPS
- **LDAP_USE_SSL**: Enable LDAPS (recommended for production)
- **LDAP_USE_TLS**: Alternative to LDAPS (StartTLS)
- **LDAP_BIND_DN**: Distinguished Name of service account (must have read access to user objects)
- **LDAP_BIND_PASSWORD**: Password for service account (stored in .env)
- **LDAP_SEARCH_BASE**: Base DN for user searches (e.g., DC=domain,DC=com)
- **LDAP_USER_SEARCH_FILTER**: Filter to find users by username
  - Active Directory: `(sAMAccountName={username})`
  - OpenLDAP: `(uid={username})`
- **LDAP_EMAIL_ATTR**: Attribute containing user email (mail, userPrincipalName, etc.)
- **LDAP_NAME_ATTR**: Attribute containing full name (cn, displayName, etc.)
- **LDAP_ADMIN_USERS**: List of AD usernames that should automatically be admins

## Authentication Flow

### 1. Local User (Database Password)

```python
User exists in DB + auth_type = 'local'
  → Check password in database
  → Success: Return JWT token
  → Failure: Try LDAP (if enabled)
```

### 2. LDAP User

```python
LDAP Enabled
  → Bind to AD with service account
  → Search for user by sAMAccountName
  → Extract email and cn attributes
  → Bind as user to verify password
  → Create/update user in database
  → Return JWT token
```

### 3. First-Time LDAP Login

```python
User not in database
  → Authenticate via LDAP
  → Create user record:
    - email: from AD
    - full_name: from AD
    - ldap_uid: sAMAccountName
    - auth_type: 'ldap'
    - role: 'admin' if in LDAP_ADMIN_USERS else 'user'
  → Return JWT token
```

## User Creation

### LDAP Users

- **Auto-created**: On first successful LDAP authentication
- **No registration required**: Users login with AD credentials
- **Synchronized**: Email and name updated on each login

### Local Admin Users

```bash
# Via API registration (admin must create manually)
curl -X POST http://localhost:5174/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "secure_password",
    "full_name": "Local Admin",
    "role": "admin"
  }'
```

**Important**: Local registration should be done carefully in production to prevent unauthorized user creation.

## Security Considerations

### Service Account Permissions

- Create a read-only service account in AD
- Grant only necessary permissions (read user attributes)
- Use strong password and regular rotation
- Store password securely in `.env` (not in code)

### SSL/TLS

- **LDAPS** (LDAP over SSL) is recommended for production
- Use port 636 with `LDAP_USE_SSL=true`
- Ensure valid SSL certificate on AD server
- Test connection: `openssl s_client -connect ad-server:636`

### Audit Logging

All authentication attempts are logged:

```python
logger.info(f"LDAP authentication successful for user: {username}")
logger.warning(f"LDAP authentication failed for user: {username}")
logger.info(f"New local user registered: {email}")
```

Check logs for:
- Failed authentication attempts
- New user creations
- Role changes

## Troubleshooting

### LDAP Connection Issues

```bash
# Test connection with ldap3
python3 -c "
from ldap3 import Server, Connection
server = Server('ldaps://ad-server.domain.com', port=636, use_ssl=True)
conn = Connection(server, 'CN=service,CN=Users,DC=domain,DC=com', 'password', auto_bind=True)
print('Connected successfully')
"
```

### Search Filter Issues

```bash
# Test user search with ldapsearch
ldapsearch -H ldaps://ad-server.domain.com:636 \
  -D 'CN=service,CN=Users,DC=domain,DC=com' \
  -W \
  -b 'DC=domain,DC=com' \
  '(sAMAccountName=john.doe)' \
  mail cn
```

### Common Errors

1. **"Failed to bind to LDAP server"**
   - Check LDAP_SERVER and LDAP_PORT
   - Verify service account credentials
   - Check firewall rules

2. **"User not found in LDAP"**
   - Verify LDAP_SEARCH_BASE
   - Check LDAP_USER_SEARCH_FILTER
   - Ensure user exists in AD

3. **"User has no email attribute"**
   - Verify LDAP_EMAIL_ATTR
   - Ensure users have email populated in AD

4. **"LDAP authentication failed"**
   - Verify user password
   - Check account is not locked/disabled
   - Verify user can log in to AD normally

## Testing

### Test LDAP Authentication

```python
from app.auth.ldap_auth import ldap_authenticate

result = ldap_authenticate("jdoe", "password")
print(result)
# Output: {'username': 'jdoe', 'email': 'jdoe@domain.com', 'full_name': 'John Doe', 'is_admin': False}
```

### Test Hybrid Authentication

```bash
# Test LDAP user
curl -X POST http://localhost:5174/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=jdoe&password=ad_password"

# Test local user
curl -X POST http://localhost:5174/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=local_password"
```

## Database Schema

### User Table (Updated)

```sql
CREATE TABLE user (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    role VARCHAR(50) DEFAULT 'user',
    auth_type VARCHAR(10) DEFAULT 'local' NOT NULL,  -- 'local' or 'ldap'
    ldap_uid VARCHAR(255) UNIQUE NULL,  -- sAMAccountName
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_user_ldap_uid ON user (ldap_uid);
```

## Migration from Local to LDAP

For existing systems with local users:

1. Enable LDAP in `.env`
2. Users with existing accounts continue using local passwords
3. New users can use LDAP credentials
4. Optional: Update existing users to LDAP:

```sql
-- Set auth_type for existing users
UPDATE user SET auth_type = 'ldap', ldap_uid = LOWER(email) WHERE email LIKE '%@domain.com';
```

## Performance Considerations

- **LDAP search caching**: ldap3 caches connections
- **Database lookup**: First check for local user (indexed by email and ldap_uid)
- **Connection pooling**: Re-use LDAP connections for multiple requests
- **Timeout**: Set `LDAP_TIMEOUT` to appropriate value (default: 10s)

## Production Checklist

- [ ] LDAPS enabled with valid SSL certificate
- [ ] Read-only service account created
- [ ] Service account password stored securely
- [ ] LDAP_ADMIN_USERS configured for admins
- [ ] Firewall allows outbound LDAP connections
- [ ] Test authentication with real AD users
- [ ] Verify audit logging is working
- [ ] Monitor LDAP connection errors in logs
