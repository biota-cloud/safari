"""
Admin State — State management for admin panel and project sharing.

Handles:
- Admin modal (user management, roles)
- Project members popover (add/remove members per project)
"""

import reflex as rx
from app_state import AuthState
from backend.supabase_client import (
    get_all_users,
    set_user_role,
    get_project_members,
    add_project_member,
    remove_project_member,
    promote_to_team_project,
    demote_from_team_project,
)


class AdminState(rx.State):
    """State for the admin panel modal and project sharing."""
    
    # Admin modal
    show_admin_modal: bool = False
    admin_users: list[dict] = []
    
    # Project sharing popover
    show_members_popover: bool = False
    project_members: list[dict] = []
    _members_project_id: str = ""
    
    # Available users for adding (excludes current members)
    available_users: list[dict] = []
    
    # Team project toggle
    is_team_project: bool = False
    
    def open_admin_modal(self):
        """Load users and open admin modal."""
        self.admin_users = get_all_users()
        self.show_admin_modal = True
    
    def close_admin_modal(self):
        """Close admin modal."""
        self.show_admin_modal = False
    
    def toggle_user_role(self, user_id: str, current_role: str):
        """Toggle a user's role between admin and user."""
        # Don't let admin demote themselves
        auth = self.get_state(AuthState)
        if user_id == auth.user_id:
            return
        
        new_role = "user" if current_role == "admin" else "admin"
        if set_user_role(user_id, new_role):
            # Refresh user list
            self.admin_users = get_all_users()
    
    def load_project_members(self, project_id: str, is_team: bool):
        """Load members for a project and open popover."""
        self._members_project_id = project_id
        self.is_team_project = is_team
        raw_members = get_project_members(project_id)
        # Flatten nested profiles data for Reflex foreach compatibility
        self.project_members = self._flatten_members(raw_members)
        self._refresh_available_users()
        self.show_members_popover = True
    
    def close_members_popover(self):
        """Close the members popover."""
        self.show_members_popover = False
    
    def _refresh_available_users(self):
        """Refresh available users (all users minus current members)."""
        all_users = get_all_users()
        member_ids = {m.get("user_id") for m in self.project_members}
        self.available_users = [
            u for u in all_users 
            if u.get("id") not in member_ids
        ]
    
    def _flatten_members(self, raw_members: list[dict]) -> list[dict]:
        """Flatten nested Supabase profiles into flat dicts for Reflex."""
        return [
            {
                "user_id": m.get("user_id", ""),
                "role": m.get("role", "member"),
                "email": (m.get("profiles") or {}).get("email", "Unknown"),
                "display_name": (m.get("profiles") or {}).get("display_name", ""),
            }
            for m in raw_members
        ]

    def add_member(self, user_id: str):
        """Add a user as member of the current project."""
        if self._members_project_id and add_project_member(self._members_project_id, user_id):
            self.project_members = self._flatten_members(get_project_members(self._members_project_id))
            self._refresh_available_users()
    
    def remove_member(self, user_id: str):
        """Remove a user from the current project."""
        if self._members_project_id and remove_project_member(self._members_project_id, user_id):
            self.project_members = self._flatten_members(get_project_members(self._members_project_id))
            self._refresh_available_users()
    
    def toggle_team_project(self):
        """Toggle is_company flag on the current project."""
        if self._members_project_id:
            if self.is_team_project:
                demote_from_team_project(self._members_project_id)
                self.is_team_project = False
            else:
                promote_to_team_project(self._members_project_id)
                self.is_team_project = True
