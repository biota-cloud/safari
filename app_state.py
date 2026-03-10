"""
Application State — Global state management for the Reflex app.

Contains authentication logic and user session management.
Session tokens are persisted in browser local storage for longer sessions.
"""

import reflex as rx
from typing import Optional
from backend.supabase_client import get_supabase, create_supabase_auth


class AuthState(rx.State):
    """Authentication state with login/logout/session management."""
    
    # User session data
    user: Optional[dict] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    
    # UI states
    is_loading: bool = False
    error_message: str = ""
    
    # Session lifecycle: False until first auth check completes (prevents login page flash)
    session_checked: bool = False
    
    # Session restoration gate — per-instance (not class-level) to avoid
    # cross-user blocking in multi-user deployments.
    _session_restore_in_progress: bool = False
    
    @rx.var
    def is_authenticated(self) -> bool:
        """Check if user is currently authenticated."""
        return self.user is not None
    
    @rx.var
    def user_email(self) -> str:
        """Get the current user's email."""
        if self.user:
            return self.user.get("email", "")
        return ""
    
    @rx.var
    def user_id(self) -> str:
        """Get the current user's ID."""
        if self.user:
            return self.user.get("id", "")
        return ""
    
    @rx.var(cache=True)
    def user_role(self) -> str:
        """Get the current user's role ('admin' or 'user')."""
        if self.user:
            from backend.supabase_client import get_user_role
            return get_user_role(self.user.get("id", ""))
        return "user"
    
    @rx.var
    def is_admin(self) -> bool:
        """Check if the current user is an admin."""
        return self.user_role == "admin"
    
    async def login(self, form_data: dict):
        """
        Authenticate user with email and password from form submission.
        
        Args:
            form_data: Dict with 'email' and 'password' keys from rx.form.
        """
        email = form_data.get("email", "")
        password = form_data.get("password", "")
        remember_me = True  # Always remember
        
        self.is_loading = True
        self.error_message = ""
        yield  # Update UI to show loading state
        
        try:
            supabase = create_supabase_auth()
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user:
                self.user = {
                    "id": response.user.id,
                    "email": response.user.email,
                }
                self.access_token = response.session.access_token
                self.refresh_token = response.session.refresh_token
                self.error_message = ""
                self.session_checked = True
                
                # Store tokens based on remember_me preference
                storage_type = "localStorage" if remember_me else "sessionStorage"
                yield rx.call_script(
                    f"""
                    {storage_type}.setItem('safari_access_token', '{response.session.access_token}');
                    {storage_type}.setItem('safari_refresh_token', '{response.session.refresh_token}');
                    {storage_type}.setItem('safari_user_id', '{response.user.id}');
                    {storage_type}.setItem('safari_user_email', '{response.user.email}');
                    """
                )
                
                # Redirect to dashboard on success
                yield rx.redirect("/dashboard")
            else:
                self.error_message = "Login failed. Please check your credentials."
                
        except Exception as e:
            error_str = str(e)
            if "Invalid login credentials" in error_str:
                self.error_message = "Invalid email or password."
            elif "Email not confirmed" in error_str:
                self.error_message = "Please confirm your email before logging in."
            else:
                self.error_message = f"Login error: {error_str}"
        finally:
            self.is_loading = False
    
    async def logout(self):
        """Sign out the current user and clear stored tokens."""
        self.is_loading = True
        yield
        
        try:
            supabase = create_supabase_auth()
            supabase.auth.sign_out()
        except Exception:
            pass  # Ignore errors during logout
        finally:
            self.user = None
            self.access_token = None
            self.refresh_token = None
            self.session_checked = False
            self.is_loading = False
            
            # Clear tokens from both localStorage and sessionStorage
            yield rx.call_script(
                """
                localStorage.removeItem('safari_access_token');
                localStorage.removeItem('safari_refresh_token');
                localStorage.removeItem('safari_user_id');
                localStorage.removeItem('safari_user_email');
                sessionStorage.removeItem('safari_access_token');
                sessionStorage.removeItem('safari_refresh_token');
                sessionStorage.removeItem('safari_user_id');
                sessionStorage.removeItem('safari_user_email');
                """
            )
            yield rx.redirect("/login")
    
    async def check_auth(self):
        """
        Check if user has an active session on page load.
        
        In multi-user mode, we rely ONLY on per-instance state (self.user)
        which was set during login or restored from browser storage.
        We do NOT read from a shared Supabase client, because that would
        return whichever user last called set_session() globally.
        
        Restoration from browser storage is handled separately
        by try_restore_from_storage via on_mount in require_auth.
        """
        # If this instance already has a valid user (set during login or
        # a previous restore), mark as checked and return immediately.
        if self.user is not None and self.access_token:
            self.session_checked = True
            return
        
        # No valid per-instance session found — don't clear state or mark checked.
        # Restoration from browser localStorage is handled by on_mount
        # via try_restore_from_storage. That will mark session_checked = True.
    
    async def restore_session(self, user_id: str, user_email: str, access_token: str, refresh_token: str):
        """
        Restore session from localStorage tokens.
        Called from client-side JavaScript.
        """
        # Singleton gate: prevent parallel restoration attempts
        if self._session_restore_in_progress:
            print("[DEBUG] Session restore already in progress, skipping...")
            return
        
        if user_id and user_email and access_token:
            self._session_restore_in_progress = True
            try:
                self.user = {
                    "id": user_id,
                    "email": user_email,
                }
                self.access_token = access_token
                self.refresh_token = refresh_token
                
                # Try to set the session in Supabase client for API calls
                try:
                    supabase = create_supabase_auth()
                    supabase.auth.set_session(access_token, refresh_token)
                    
                    # Get the new session with refreshed tokens
                    new_session = supabase.auth.get_session()
                    if new_session and new_session.refresh_token and new_session.refresh_token != refresh_token:
                        # Update state with new tokens
                        self.access_token = new_session.access_token
                        self.refresh_token = new_session.refresh_token
                        
                        # Atomically update localStorage with new tokens to prevent stale token reuse
                        yield rx.call_script(f"""
                            localStorage.setItem('safari_access_token', '{new_session.access_token}');
                            localStorage.setItem('safari_refresh_token', '{new_session.refresh_token}');
                            sessionStorage.setItem('safari_access_token', '{new_session.access_token}');
                            sessionStorage.setItem('safari_refresh_token', '{new_session.refresh_token}');
                        """)
                        print(f"[SAFARI] Tokens refreshed and stored for: {user_email}")
                except Exception as e:
                    print(f"[DEBUG] Could not restore Supabase session: {e}")
            finally:
                self._session_restore_in_progress = False
    
    def clear_error(self):
        """Clear any error messages."""
        self.error_message = ""

    async def proactive_refresh(self):
        """
        Proactively refresh the session tokens before they expire.
        Called from client-side JavaScript when token is near expiration.
        """
        if not self.refresh_token:
            print("[Auth] No refresh token available for proactive refresh")
            return
        
        # Singleton gate to prevent parallel refresh attempts
        if self._session_restore_in_progress:
            print("[Auth] Refresh already in progress, skipping...")
            return
        
        self._session_restore_in_progress = True
        try:
            supabase = create_supabase_auth()
            
            # Use the refresh token to get a new session
            response = supabase.auth.refresh_session(self.refresh_token)
            
            if response and response.session:
                new_access = response.session.access_token
                new_refresh = response.session.refresh_token
                
                # Update state
                self.access_token = new_access
                self.refresh_token = new_refresh
                
                # Update browser storage atomically
                yield rx.call_script(f"""
                    localStorage.setItem('safari_access_token', '{new_access}');
                    localStorage.setItem('safari_refresh_token', '{new_refresh}');
                    sessionStorage.setItem('safari_access_token', '{new_access}');
                    sessionStorage.setItem('safari_refresh_token', '{new_refresh}');
                    console.log('[SAFARI] Session proactively refreshed');
                """)
                print(f"[Auth] Session proactively refreshed for: {self.user_email}")
            else:
                print("[Auth] Proactive refresh returned no session")
                
        except Exception as e:
            print(f"[Auth] Proactive refresh failed: {e}")
        finally:
            self._session_restore_in_progress = False

    async def try_restore_from_storage(self):
        """
        Try to restore session from browser storage.
        Called via on_mount when unauthenticated but storage might have tokens.
        Uses rx.call_script with callback to read tokens and restore.
        """
        # Use rx.call_script to read tokens from localStorage and call restore_session
        yield rx.call_script(
            """
            (function() {
                let accessToken = localStorage.getItem('safari_access_token');
                let refreshToken = localStorage.getItem('safari_refresh_token') || '';
                let userId = localStorage.getItem('safari_user_id') || '';
                let userEmail = localStorage.getItem('safari_user_email') || '';
                
                if (!accessToken) {
                    accessToken = sessionStorage.getItem('safari_access_token') || '';
                    refreshToken = sessionStorage.getItem('safari_refresh_token') || '';
                    userId = sessionStorage.getItem('safari_user_id') || '';
                    userEmail = sessionStorage.getItem('safari_user_email') || '';
                }
                
                // Return as JSON for the callback
                return JSON.stringify({
                    access_token: accessToken || '',
                    refresh_token: refreshToken || '',
                    user_id: userId || '',
                    user_email: userEmail || ''
                });
            })();
            """,
            callback=AuthState.handle_storage_tokens,
        )

    async def handle_storage_tokens(self, tokens_json: str):
        """
        Callback from try_restore_from_storage with tokens from browser storage.
        Parses the JSON and restores the session if valid.
        """
        import json
        
        try:
            tokens = json.loads(tokens_json)
            access_token = tokens.get("access_token", "")
            refresh_token = tokens.get("refresh_token", "")
            user_id = tokens.get("user_id", "")
            user_email = tokens.get("user_email", "")
            
            if access_token and user_id and user_email:
                # Singleton gate: prevent parallel restoration attempts
                if self._session_restore_in_progress:
                    print("[DEBUG] Session restore already in progress, skipping...")
                    return
                
                self._session_restore_in_progress = True
                try:
                    # Restore the session
                    self.user = {
                        "id": user_id,
                        "email": user_email,
                    }
                    self.access_token = access_token
                    self.refresh_token = refresh_token
                    
                    # Set session in Supabase client for API calls
                    try:
                        supabase = create_supabase_auth()
                        if refresh_token:
                            supabase.auth.set_session(access_token, refresh_token)
                        
                            # Get the new session with refreshed tokens
                            new_session = supabase.auth.get_session()
                            if new_session and new_session.refresh_token and new_session.refresh_token != refresh_token:
                                # Update state with new tokens
                                self.access_token = new_session.access_token
                                self.refresh_token = new_session.refresh_token
                                
                                # Atomically update localStorage with new tokens
                                yield rx.call_script(f"""
                                    localStorage.setItem('safari_access_token', '{new_session.access_token}');
                                    localStorage.setItem('safari_refresh_token', '{new_session.refresh_token}');
                                    sessionStorage.setItem('safari_access_token', '{new_session.access_token}');
                                    sessionStorage.setItem('safari_refresh_token', '{new_session.refresh_token}');
                                """)
                                print(f"[SAFARI] Tokens refreshed and stored for: {user_email}")
                            else:
                                print(f"[SAFARI] Session restored seamlessly for: {user_email}")
                        else:
                            print(f"[SAFARI] Session restored (no refresh token) for: {user_email}")
                    except Exception as e:
                        # Token might be expired — clear user state so we redirect properly
                        print(f"[SAFARI] Session restore failed (token likely expired): {e}")
                        self.user = None
                        self.access_token = None
                        self.refresh_token = None
                        # Clear stale tokens from browser to break any redirect loop
                        yield rx.call_script("""
                            localStorage.removeItem('safari_access_token');
                            localStorage.removeItem('safari_refresh_token');
                            localStorage.removeItem('safari_user_id');
                            localStorage.removeItem('safari_user_email');
                            sessionStorage.removeItem('safari_access_token');
                            sessionStorage.removeItem('safari_refresh_token');
                            sessionStorage.removeItem('safari_user_id');
                            sessionStorage.removeItem('safari_user_email');
                        """)
                    
                    self.session_checked = True
                    yield rx.call_script("window._tytoRestoreInProgress = false;")
                finally:
                    self._session_restore_in_progress = False
            else:
                # No valid tokens — clear stale tokens to break redirect loop, then redirect
                self.session_checked = True
                print("[SAFARI] No valid tokens in storage, clearing and redirecting to login")
                yield rx.call_script("""
                    localStorage.removeItem('safari_access_token');
                    localStorage.removeItem('safari_refresh_token');
                    localStorage.removeItem('safari_user_id');
                    localStorage.removeItem('safari_user_email');
                    sessionStorage.removeItem('safari_access_token');
                    sessionStorage.removeItem('safari_refresh_token');
                    sessionStorage.removeItem('safari_user_id');
                    sessionStorage.removeItem('safari_user_email');
                """)
                yield rx.redirect("/login")
                
        except Exception as e:
            self.session_checked = True
            print(f"[ERROR] Failed to parse storage tokens: {e}")
            yield rx.call_script("""
                localStorage.removeItem('safari_access_token');
                localStorage.removeItem('safari_refresh_token');
                localStorage.removeItem('safari_user_id');
                localStorage.removeItem('safari_user_email');
                sessionStorage.removeItem('safari_access_token');
                sessionStorage.removeItem('safari_refresh_token');
                sessionStorage.removeItem('safari_user_id');
                sessionStorage.removeItem('safari_user_email');
            """)
            yield rx.redirect("/login")


def require_auth(page) -> rx.Component:
    """
    Decorator/wrapper for pages that require authentication.
    If not authenticated, tries to restore session from localStorage directly,
    otherwise redirects to /login.
    
    Uses seamless restoration via Reflex events (no visible page reload).
    
    Usage:
        @rx.page(route="/dashboard", on_load=AuthState.check_auth)
        def dashboard() -> rx.Component:
            return require_auth(dashboard_content())
    """
    # Proactive token refresh script (shared, only initialized once)
    proactive_refresh_script = rx.script(
        """
        (function() {
            // Prevent multiple initializations
            if (window._tytoProactiveRefreshInitialized) return;
            window._tytoProactiveRefreshInitialized = true;
            
            // Token expiry check function
            function checkAndRefreshToken() {
                const token = localStorage.getItem('safari_access_token');
                if (!token) return;
                
                try {
                    // Decode JWT to check expiry (tokens are base64 encoded)
                    const parts = token.split('.');
                    if (parts.length !== 3) return;
                    
                    const payload = JSON.parse(atob(parts[1]));
                    const expiresAt = payload.exp * 1000; // Convert to milliseconds
                    const now = Date.now();
                    const timeLeft = expiresAt - now;
                    
                    // Refresh if less than 5 minutes remaining
                    if (timeLeft < 300000 && timeLeft > 0) {
                        console.log('[SAFARI] Token expires in ' + Math.round(timeLeft/1000) + 's, refreshing proactively...');
                        // Trigger Reflex backend event for proactive refresh
                        if (window.__reflex && window.__reflex.call) {
                            window.__reflex.call('auth_state.proactive_refresh', []);
                        }
                    }
                } catch (e) {
                    console.warn('[SAFARI] Could not parse token for expiry check:', e);
                }
            }
            
            // Check immediately on load
            checkAndRefreshToken();
            
            // Check every 60 seconds while page is visible
            setInterval(function() {
                if (document.visibilityState === 'visible') {
                    checkAndRefreshToken();
                }
            }, 60000);
            
            // Also check when tab becomes visible (handles sleep/wake, tab switching)
            document.addEventListener('visibilitychange', function() {
                if (document.visibilityState === 'visible') {
                    console.log('[SAFARI] Tab became visible, checking token...');
                    checkAndRefreshToken();
                }
            });
            
            console.log('[SAFARI] Proactive token refresh initialized');
        })();
        """
    )
    
    return rx.cond(
        AuthState.is_authenticated,
        # Authenticated: show page with proactive refresh
        rx.fragment(page, proactive_refresh_script),
        # Not authenticated yet — check if we've completed the auth check
        rx.cond(
            AuthState.session_checked,
            # Auth check complete, user is NOT authenticated → redirect to login
            rx.fragment(
                rx.center(
                    rx.vstack(
                        rx.text("Redirecting to login...", style={"color": "#A1A1AA"}),
                        align="center",
                    ),
                    style={"min_height": "100vh", "background": "#0A0A0B"}
                ),
            ),
            # Auth check NOT yet complete → show loading + try restore from storage
            rx.fragment(
                rx.center(
                    rx.vstack(
                        rx.spinner(size="3"),
                        rx.text("Loading...", style={"color": "#A1A1AA", "margin_top": "8px"}),
                        align="center",
                    ),
                    style={"min_height": "100vh", "background": "#0A0A0B"}
                ),
                # Single restoration path via on_mount — no racing scripts
                rx.box(
                    on_mount=AuthState.try_restore_from_storage,
                    style={"display": "none"},
                )
            )
        )
    )
