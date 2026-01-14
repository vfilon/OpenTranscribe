# LDAP/Active Directory Authentication

## Overview

OpenTranscribe supports hybrid authentication combining LDAP/Active Directory with local database users:

- **LDAP users**: Auto-created on first login with role based on `LDAP_ADMIN_USERS`
- **Local admin users**: Created manually via registration endpoint with database passwords
- **Flexible auth**: System supports both email-based (local) and username-based (LDAP) login
- **Priority**: Local users checked first when `auth_type='local'` in database

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

### Hybrid Authentication Strategy

The system uses a flexible authentication flow based on the user's `auth_type` in the database:

#### 1. Local User (Database Password)

```python
User exists in DB + auth_type = 'local'
  → Try direct database authentication (bypasses ORM for reliability)
  → If direct fails, try ORM authentication
  → Success: Return JWT token
  → Failure: Try LDAP (as fallback if user exists)
```

#### 2. LDAP User

```python
LDAP Enabled OR user not found locally
  → Bind to AD with service account
  → Search for user by sAMAccountName
  → Extract email and cn attributes
  → Bind as user to verify password
  → Create/update user in database
  → Return JWT token
```

#### 3. First-Time LDAP Login

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

### Login Input Options

Users can login with:
- **Email address** (for local users)
- **Username/sAMAccountName** (for LDAP users)

The system automatically handles both formats:
```bash
# Local user login
curl -X POST http://localhost:5174/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=local_password"

# LDAP user login
curl -X POST http://localhost:5174/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=john.doe&password=ad_password"
```

## User Creation

### LDAP Users

- **Auto-created**: On first successful LDAP authentication
- **No registration required**: Users login with AD credentials
- **Synchronized**: Email and name updated on each login
- **Role management**: Admin status determined by `LDAP_ADMIN_USERS` list

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

## Security Features

### LDAP Injection Protection

The system escapes special characters in LDAP filter values to prevent injection attacks:

```python
_escaped_username = _escape_ldap_filter(username)
# Escapes: ( ) * \ NUL characters
```

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

### JWT Token Security

- Tokens use UUID as user identifier (not integer ID)
- Role information included in token for immediate permission updates
- Tokens expire based on `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` setting

### Audit Logging

All authentication attempts are logged:

```python
logger.info(f"LDAP authentication successful for user: {username}")
logger.warning(f"LDAP authentication failed for user: {username}")
logger.info(f"New local user registered: {email}")
logger.info(f"Direct authentication successful for local user: {username}")
```

Check logs for:
- Failed authentication attempts
- New user creations
- Role changes
- Authentication method used (direct vs LDAP)

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

5. **"Direct auth failed, trying ORM auth"**
   - This is expected fallback behavior
   - Indicates direct DB connection issue
   - ORM auth will be tried automatically

## Testing

### Test LDAP Authentication

```python
from app.auth.ldap_auth import ldap_authenticate

result = ldap_authenticate("jdoe", "password")
print(result)
# Output: {'username': 'jdoe', 'email': 'jdoe@domain.com', 'full_name': 'John Doe', 'is_admin': False}
```

### Test Direct Authentication

```python
from app.auth.direct_auth import direct_authenticate_user

result = direct_authenticate_user("admin@example.com", "password")
print(result)
# Output: {'id': 1, 'email': 'admin@example.com', 'full_name': 'Admin User', 'role': 'admin', 'is_active': True, 'is_superuser': True}
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
CREATE TABLE "user" (
    id SERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),  -- Public identifier
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    role VARCHAR(50) DEFAULT 'user',
    auth_type VARCHAR(10) DEFAULT 'local' NOT NULL,  -- 'local' or 'ldap'
    ldap_uid VARCHAR(255) UNIQUE NULL,  -- sAMAccountName
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_uuid ON "user"(uuid);
CREATE INDEX idx_user_ldap_uid ON "user"(ldap_uid);
```

### Key Design Decisions

- **UUID as public identifier**: Used in JWT tokens and API responses
- **Integer ID for internal operations**: Faster database joins and queries
- **auth_type field**: Determines authentication method to try first
- **ldap_uid indexed**: Fast lookups for LDAP users

## Migration from Local to LDAP

For existing systems with local users:

1. Enable LDAP in `.env`
2. Users with existing accounts continue using local passwords (`auth_type='local'`)
3. New users can use LDAP credentials
4. Optional: Update existing users to LDAP:

```sql
-- Set auth_type for existing users to use LDAP
UPDATE "user"
SET auth_type = 'ldap',
    ldap_uid = SPLIT_PART(email, '@', 1),
    hashed_password = ''  -- Empty since auth handled by LDAP
WHERE email LIKE '%@domain.com';

-- Note: Users must have matching sAMAccountName in AD
```

## Performance Considerations

- **LDAP search caching**: ldap3 caches connections
- **Direct database auth**: Bypasses ORM for faster local authentication
- **UUID indexing**: Fast lookups for token validation
- **Database lookup**: First check for local user by email or ldap_uid
- **Connection pooling**: Re-use LDAP connections for multiple requests
- **Timeout**: Set `LDAP_TIMEOUT` to appropriate value (default: 10s)

## Production Checklist

- [ ] LDAPS enabled with valid SSL certificate
- [ ] Read-only service account created
- [ ] Service account password stored securely
- [ ] LDAP_ADMIN_USERS configured for admins
- [ ] Firewall allows outbound LDAP connections
- [ ] Test authentication with real AD users
- [ ] Test authentication with local users
- [ ] Verify audit logging is working
- [ ] Monitor LDAP connection errors in logs
- [ ] Verify direct auth fallback works
- [ ] Check UUID-based token validation
- [ ] Test role updates via LDAP_ADMIN_USERS

## Implementation Details

### Directory Structure

```
backend/app/auth/
├── direct_auth.py      # Direct DB authentication (bypasses ORM)
├── ldap_auth.py        # LDAP/Active Directory authentication
└── __init__.py

backend/app/api/endpoints/
└── auth.py             # Authentication endpoints (login, register)
```

### Key Functions

**ldap_auth.py:**
- `_escape_ldap_filter()`: Prevents LDAP injection attacks
- `_get_ldap_server()`: Creates configured LDAP server object
- `ldap_authenticate()`: Authenticates user against AD
- `sync_ldap_user_to_db()`: Creates/updates user from LDAP data

**direct_auth.py:**
- `direct_authenticate_user()`: Direct DB authentication (bypasses ORM)
- `verify_password()`: Password verification with bcrypt_sha256
- `create_access_token()`: JWT token generation

**auth.py:**
- `_authenticate_ldap_user()`: LDAP authentication handler
- `_authenticate_production_user()`: Hybrid authentication flow
- `get_current_user()`: JWT token validation with UUID
- `login_for_access_token()`: OAuth2 token endpoint

### Password Hashing

The system uses `bcrypt_sha256` for password hashing:
- Pre-hashes passwords with SHA256 (overcomes bcrypt's 72-byte limitation)
- Supports existing `bcrypt` hashes (will auto-upgrade on verify)
- Default rounds: 12 for both schemes
