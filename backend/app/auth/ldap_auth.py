"""
LDAP/Active Directory authentication module.

Handles authentication against Active Directory using LDAPS.
"""

import logging
from typing import Optional

from ldap3 import ALL
from ldap3 import AUTO_BIND_TLS_BEFORE_BIND
from ldap3 import Connection
from ldap3 import Server
from ldap3.core.exceptions import LDAPBindError
from ldap3.core.exceptions import LDAPException

from app.core.config import settings

logger = logging.getLogger(__name__)


def _escape_ldap_filter(value: str) -> str:
    """Escape special characters in LDAP filter values to prevent injection.

    LDAP special characters that need escaping: ( ) * \\ NUL

    Args:
        value: The string to escape

    Returns:
        Escaped string safe for use in LDAP filters
    """
    return (
        value.replace("\\", "\\5c")
        .replace("*", "\\2a")
        .replace("(", "\\28")
        .replace(")", "\\29")
        .replace("\x00", "\\00")
    )


def _get_ldap_server():
    """
    Create and return an LDAP server object.

    Returns:
        Server: Configured LDAP server object
    """
    server = Server(
        settings.LDAP_SERVER,
        port=settings.LDAP_PORT,
        use_ssl=settings.LDAP_USE_SSL,
        get_info=ALL,
        connect_timeout=settings.LDAP_TIMEOUT,
    )
    return server


def ldap_authenticate(username: str, password: str) -> Optional[dict]:
    """
    Authenticate a user against Active Directory.

    This function:
    1. Connects to AD using a service account
    2. Searches for the user by sAMAccountName (or email if username contains @)
    3. Attempts to bind as the user to verify credentials
    4. Extracts user attributes (email, full name)

    Args:
        username: The username (sAMAccountName) or email to authenticate
        password: The user's password

    Returns:
        dict with keys:
            - username: sAMAccountName
            - email: User's email address
            - full_name: User's full name (cn)
            - is_admin: Boolean indicating admin status
        None: If authentication fails

    Raises:
        None (errors are logged and None is returned)
    """
    if not settings.LDAP_ENABLED:
        logger.warning("LDAP authentication attempted but LDAP is not enabled")
        return None

    logger.info(f"LDAP authenticate called for: {username}")
    if "@" in username:
        ldap_username = username.split("@")[0]
    else:
        ldap_username = username

    try:
        server = _get_ldap_server()

        # Step 1: Connect and bind with service account
        try:
            bind_conn = Connection(
                server,
                user=settings.LDAP_BIND_DN,
                password=settings.LDAP_BIND_PASSWORD,
                auto_bind=AUTO_BIND_TLS_BEFORE_BIND if settings.LDAP_USE_SSL else True,
            )
            logger.debug(f"LDAP service account bind successful")
        except LDAPBindError as e:
            logger.error(f"Failed to bind to LDAP server: {str(e)}")
            return None

        # Step 2: Search for user by sAMAccountName
        search_filter = settings.LDAP_USER_SEARCH_FILTER.format(
            username=_escape_ldap_filter(ldap_username)
        )
        attributes = [settings.LDAP_EMAIL_ATTR, settings.LDAP_NAME_ATTR]

        bind_conn.search(
            search_base=settings.LDAP_SEARCH_BASE,
            search_filter=search_filter,
            attributes=attributes,
        )

        if not bind_conn.entries:
            logger.debug(
                f"User not found by {settings.LDAP_USERNAME_ATTR}={ldap_username}, trying email search"
            )
            email_search_filter = f"({settings.LDAP_EMAIL_ATTR}={_escape_ldap_filter(username)})"
            bind_conn.search(
                search_base=settings.LDAP_SEARCH_BASE,
                search_filter=email_search_filter,
                attributes=attributes,
            )

        if not bind_conn.entries:
            logger.warning(f"User not found in LDAP: {username}")
            bind_conn.unbind()
            return None

        user_entry = bind_conn.entries[0]
        logger.debug(f"Found user in LDAP: {user_entry}")

        # Extract username attribute from entry
        ldap_username_value = (
            str(getattr(user_entry, settings.LDAP_USERNAME_ATTR, ldap_username))
            if hasattr(user_entry, settings.LDAP_USERNAME_ATTR)
            else ldap_username
        )

        # Extract user attributes
        user_email = (
            str(user_entry[settings.LDAP_EMAIL_ATTR].value)
            if settings.LDAP_EMAIL_ATTR in user_entry
            else ""
        )
        user_full_name = (
            str(user_entry[settings.LDAP_NAME_ATTR].value)
            if settings.LDAP_NAME_ATTR in user_entry
            else ""
        )

        if not user_email:
            logger.warning(f"User {username} has no email attribute in LDAP")
            bind_conn.unbind()
            return None

        # Step 3: Verify credentials by binding as the user
        try:
            user_conn = Connection(
                server,
                user=user_entry.entry_dn,
                password=password,
                auto_bind=AUTO_BIND_TLS_BEFORE_BIND if settings.LDAP_USE_SSL else True,
            )
            logger.info(f"LDAP authentication successful for user: {ldap_username_value}")
            user_conn.unbind()
        except LDAPBindError as e:
            logger.warning(
                f"LDAP password verification failed for user {ldap_username_value}: {str(e)}"
            )
            bind_conn.unbind()
            return None

        # Step 4: Determine admin status
        admin_users = settings.LDAP_ADMIN_USERS.split(",") if settings.LDAP_ADMIN_USERS else []
        is_admin = ldap_username_value.lower() in [u.lower().strip() for u in admin_users]

        bind_conn.unbind()

        return {
            "username": ldap_username_value,
            "email": user_email,
            "full_name": user_full_name,
            "is_admin": is_admin,
        }

    except LDAPException as e:
        logger.error(f"LDAP authentication error for {username}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during LDAP authentication for {username}: {str(e)}")
        return None


def sync_ldap_user_to_db(db, ldap_data: dict):
    """
    Create or update a user in the database from LDAP data.

    Args:
        db: Database session
        ldap_data: Dictionary with LDAP user data (username, email, full_name, is_admin)

    Returns:
        User: The created or updated User object
    """
    from app.models.user import User

    username = ldap_data["username"]
    email = ldap_data["email"]

    # Check if user exists by ldap_uid or email
    user = db.query(User).filter(User.ldap_uid == username).first()

    if not user:
        user = db.query(User).filter(User.email == email).first()

    if not user:
        # Create new user from LDAP
        logger.info(f"Creating new user from LDAP: {username} ({email})")
        user = User(
            email=email,
            full_name=ldap_data["full_name"] or email.split("@")[0],
            hashed_password="",  # Empty - authentication handled by LDAP, not local password
            auth_type="ldap",
            ldap_uid=username,
            role="admin" if ldap_data["is_admin"] else "user",
            is_active=True,
            is_superuser=ldap_data["is_admin"],
        )
        db.add(user)
    else:
        # Update existing user's LDAP data
        logger.info(f"Updating existing user from LDAP: {username} ({email})")
        user.email = email
        user.full_name = ldap_data["full_name"] or user.full_name
        user.ldap_uid = username
        user.auth_type = "ldap"

        # Update role if user is LDAP admin
        if ldap_data["is_admin"] and user.role != "admin":
            user.role = "admin"
            user.is_superuser = True

    db.commit()
    db.refresh(user)
    return user
