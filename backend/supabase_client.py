"""
Supabase Client — Database and authentication helper.

Usage:
    from backend.supabase_client import get_supabase
    
    supabase = get_supabase()
    result = supabase.table("projects").select("*").execute()
"""

import os
import hashlib
import secrets


from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from .env
load_dotenv()

# Import auth retry decorator (lazy import to avoid circular dependency)
def _get_auth_retry():
    from backend.supabase_auth import with_auth_retry
    return with_auth_retry()  # Call the factory to get the actual decorator



_supabase_client: Client | None = None
def get_supabase() -> Client:
    """
    Get a cached Supabase client for DATA operations (service role, bypasses RLS).
    
    WARNING: Do NOT call .auth methods on this client — use create_supabase_auth() instead.
    Calling auth.set_session() on this client would override the service role identity.
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    
    url = os.getenv('SUPABASE_URL')
    service_key = os.getenv('SUPABASE_SERVICE_ROLE')
    anon_key = os.getenv('SUPABASE_KEY')
    key = service_key or anon_key
    
    print(f"[SUPABASE] Data client: {'SERVICE_ROLE' if service_key else 'ANON'} key")
    
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE (or SUPABASE_KEY) must be set "
            "in environment variables. Check your .env file."
        )
    
    _supabase_client = create_client(url, key)
    return _supabase_client


def create_supabase_auth() -> Client:
    """
    Create a NEW Supabase client for AUTH operations (anon key, supports user sessions).
    
    IMPORTANT: Not cached — each user session must get its own client instance to
    avoid cross-user session contamination. When one user calls set_session() it
    must NOT affect another user's in-memory auth state.
    """
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')
    
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY must be set in environment variables."
        )
    
    return create_client(url, key)


# Backward-compatible alias (deprecated — use create_supabase_auth instead)
def get_supabase_auth() -> Client:
    """DEPRECATED: Use create_supabase_auth() instead. This returns a fresh client
    each time (no longer cached) to prevent multi-user session contamination."""
    return create_supabase_auth()


# =============================================================================
# PROFILE OPERATIONS
# =============================================================================

def get_user_profile(user_id: str) -> dict | None:
    """Get a user's profile by their ID."""
    supabase = get_supabase()
    result = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
    return result.data if result.data else None


# -----------------------------------------------------------------------------
# LOCAL GPU MACHINE MANAGEMENT (stored at user profile level)
# -----------------------------------------------------------------------------

def get_user_local_machines(user_id: str) -> list[dict]:
    """Get all configured local GPU machines for a user.
    
    Returns:
        List of machine configs: [{"name": "...", "host": "...", "port": 22, "user": "..."}]
    """
    profile = get_user_profile(user_id)
    if profile and profile.get("local_gpu_machines"):
        return profile["local_gpu_machines"]
    return []


def add_local_machine(user_id: str, machine_config: dict) -> list[dict] | None:
    """Add a local GPU machine to user's profile.
    
    Args:
        user_id: User's UUID
        machine_config: Dict with keys: name, host, port, user
                       Example: {"name": "Alienware", "host": "192.168.1.100", 
                                "port": 22, "user": "ise"}
    
    Returns:
        Updated list of machines or None on error
    """
    try:
        supabase = get_supabase()
        machines = get_user_local_machines(user_id)
        
        # Check for duplicate name
        existing_names = [m.get("name") for m in machines]
        if machine_config.get("name") in existing_names:
            print(f"[LocalMachines] Machine '{machine_config.get('name')}' already exists")
            return None
        
        machines.append(machine_config)
        result = supabase.table("profiles").update(
            {"local_gpu_machines": machines}
        ).eq("id", user_id).execute()
        
        if result.data:
            return result.data[0].get("local_gpu_machines", [])
        return None
    except Exception as e:
        print(f"[LocalMachines] Error adding machine: {e}")
        return None


def remove_local_machine(user_id: str, machine_name: str) -> list[dict] | None:
    """Remove a local GPU machine from user's profile.
    
    Args:
        user_id: User's UUID
        machine_name: Name of the machine to remove
        
    Returns:
        Updated list of machines or None on error
    """
    try:
        supabase = get_supabase()
        machines = get_user_local_machines(user_id)
        
        # Filter out the machine to remove
        updated = [m for m in machines if m.get("name") != machine_name]
        
        if len(updated) == len(machines):
            print(f"[LocalMachines] Machine '{machine_name}' not found")
            return machines  # Return unchanged list
        
        result = supabase.table("profiles").update(
            {"local_gpu_machines": updated}
        ).eq("id", user_id).execute()
        
        if result.data:
            return result.data[0].get("local_gpu_machines", [])
        return None
    except Exception as e:
        print(f"[LocalMachines] Error removing machine: {e}")
        return None


def test_ssh_connection(host: str, port: int, user: str) -> dict:
    """Test SSH connection to a remote machine.
    
    Args:
        host: IP or hostname
        port: SSH port (usually 22)
        user: SSH username
        
    Returns:
        Dict with keys: success (bool), message (str), gpu_info (str or None)
    """
    try:
        import subprocess
        
        # Try a simple SSH command with timeout
        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=accept-new",
            "-p", str(port),
            f"{user}@{host}",
            "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            gpu_info = result.stdout.strip()
            return {
                "success": True,
                "message": "Connection successful",
                "gpu_info": gpu_info
            }
        else:
            return {
                "success": False,
                "message": f"SSH failed: {result.stderr.strip()}",
                "gpu_info": None
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "Connection timed out",
            "gpu_info": None
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "gpu_info": None
        }


# =============================================================================
# PROJECT OPERATIONS (Container level)
# =============================================================================

def get_user_preferences(user_id: str) -> dict:
    """Get user preferences from profiles table.
    
    Returns empty dict if not set, never None.
    """
    supabase = get_supabase()
    try:
        result = supabase.table("profiles").select("preferences").eq("id", user_id).single().execute()
        if result.data and result.data.get("preferences"):
            return result.data["preferences"]
    except Exception as e:
        print(f"[Preferences] Error loading preferences: {e}")
    return {}


def update_user_preferences(user_id: str, section: str, updates: dict) -> dict | None:
    """Update a section of user preferences (merge, not replace).
    
    Args:
        user_id: User's UUID
        section: Top-level key (e.g., 'playground', 'autolabel', 'training')
        updates: Dict of key-value pairs to merge into that section
    
    Example:
        update_user_preferences(user_id, 'playground', {'confidence_threshold': 0.5})
    
    Returns:
        Updated preferences dict or None on error
    """
    try:
        supabase = get_supabase()
        
        # Get current preferences
        current = get_user_preferences(user_id)
        
        # Merge updates into the section
        if section not in current:
            current[section] = {}
        current[section].update(updates)
        
        # Save back
        result = supabase.table("profiles").update({"preferences": current}).eq("id", user_id).execute()
        return result.data[0].get("preferences") if result.data else None
    except Exception as e:
        print(f"[Preferences] Error saving preferences: {e}")
        return None


# =============================================================================
# MULTI-USER / PROJECT SHARING
# =============================================================================

def get_user_role(user_id: str) -> str:
    """Get user role ('admin' or 'user'). Returns 'user' if not found."""
    profile = get_user_profile(user_id)
    return profile.get("role", "user") if profile else "user"


def get_all_users() -> list[dict]:
    """Get all user profiles (admin function)."""
    supabase = get_supabase()
    result = supabase.table("profiles").select("id, email, display_name, role, created_at").order("created_at").execute()
    return result.data or []


def set_user_role(user_id: str, role: str) -> bool:
    """Set a user's role ('admin' or 'user')."""
    if role not in ('admin', 'user'):
        return False
    supabase = get_supabase()
    try:
        supabase.table("profiles").update({"role": role}).eq("id", user_id).execute()
        return True
    except Exception as e:
        print(f"[Sharing] Error setting role: {e}")
        return False


def promote_to_team_project(project_id: str) -> bool:
    """Mark a project as team-shared."""
    supabase = get_supabase()
    try:
        supabase.table("projects").update({"is_company": True}).eq("id", project_id).execute()
        return True
    except Exception as e:
        print(f"[Sharing] Error promoting project: {e}")
        return False


def demote_from_team_project(project_id: str) -> bool:
    """Remove team-shared status from a project."""
    supabase = get_supabase()
    try:
        supabase.table("projects").update({"is_company": False}).eq("id", project_id).execute()
        return True
    except Exception as e:
        print(f"[Sharing] Error demoting project: {e}")
        return False


def get_project_members(project_id: str) -> list[dict]:
    """Get all members of a project with their profile info."""
    supabase = get_supabase()
    result = (
        supabase.table("project_members")
        .select("id, user_id, role, added_at, profiles(email, display_name)")
        .eq("project_id", project_id)
        .execute()
    )
    return result.data or []


def add_project_member(project_id: str, user_id: str, role: str = "member") -> bool:
    """Add a user as a member of a project."""
    supabase = get_supabase()
    try:
        supabase.table("project_members").insert({
            "project_id": project_id,
            "user_id": user_id,
            "role": role,
        }).execute()
        return True
    except Exception as e:
        print(f"[Sharing] Error adding member: {e}")
        return False


def remove_project_member(project_id: str, user_id: str) -> bool:
    """Remove a user from a project."""
    supabase = get_supabase()
    try:
        supabase.table("project_members").delete().eq(
            "project_id", project_id
        ).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        print(f"[Sharing] Error removing member: {e}")
        return False


def _get_accessible_projects(user_id: str) -> list[dict]:
    """Get all projects a user can access: owned + member + admin-company.
    
    This is the central access control function for multi-user project access.
    Used by get_user_projects() and get_user_projects_with_stats().
    """
    supabase = get_supabase()
    
    # 1. Own projects
    own_result = supabase.table("projects").select("*").eq("user_id", user_id).execute()
    projects = own_result.data or []
    seen_ids = {p["id"] for p in projects}
    
    # 2. Projects user is a member of
    members_result = (
        supabase.table("project_members")
        .select("project_id")
        .eq("user_id", user_id)
        .execute()
    )
    member_project_ids = [
        m["project_id"] for m in (members_result.data or [])
        if m["project_id"] not in seen_ids
    ]
    if member_project_ids:
        member_projects = (
            supabase.table("projects")
            .select("*")
            .in_("id", member_project_ids)
            .execute()
        )
        for p in (member_projects.data or []):
            projects.append(p)
            seen_ids.add(p["id"])
    
    # 3. If admin, also include all company projects
    role = get_user_role(user_id)
    if role == "admin":
        company_result = (
            supabase.table("projects")
            .select("*")
            .eq("is_company", True)
            .execute()
        )
        for p in (company_result.data or []):
            if p["id"] not in seen_ids:
                projects.append(p)
                seen_ids.add(p["id"])
    
    return projects


# =============================================================================
# PROJECT OPERATIONS (Container level)
# =============================================================================


def get_user_projects_with_stats(user_id: str) -> list[dict]:
    """Get all projects with dataset counts and class counts in batched queries.
    
    MULTI-USER: Returns owned + member + admin-company projects.
    
    OPTIMIZED: Reduces N+1 queries to 3 total queries:
    1. Fetch all accessible projects
    2. Fetch all datasets (with project_id grouping)
    3. Fetch class counts for all datasets at once
    
    Returns list of dicts with: id, name, description, created_at, last_accessed_at,
    classes, dataset_count, class_counts (dict)
    """
    from backend.annotation_service import compute_class_counts_for_datasets
    
    supabase = get_supabase()
    
    # Query 1: Get all accessible projects (owned + member + admin-company)
    projects = _get_accessible_projects(user_id)
    
    if not projects:
        return []
    
    project_ids = [p["id"] for p in projects]
    
    # Query 2: Get ALL datasets for all projects at once
    datasets_result = (
        supabase.table("datasets")
        .select("id, project_id, type, name")
        .in_("project_id", project_ids)
        .execute()
    )
    all_datasets = datasets_result.data or []
    
    # Group datasets by project_id
    datasets_by_project: dict[str, list] = {pid: [] for pid in project_ids}
    for ds in all_datasets:
        pid = ds.get("project_id")
        if pid in datasets_by_project:
            datasets_by_project[pid].append(ds)
    
    # Query 3: Get ALL annotations for ALL datasets in ONE batched query
    # This is the key optimization - single round trip for all annotation data
    all_dataset_ids = [ds["id"] for ds in all_datasets]
    all_dataset_types = {ds["id"]: ds.get("type", "image") for ds in all_datasets}
    
    # Build project_classes lookup for class name resolution
    project_classes_map = {p["id"]: p.get("classes", []) or [] for p in projects}
    
    # Map dataset_id -> project_id for class aggregation
    dataset_to_project = {ds["id"]: ds.get("project_id") for ds in all_datasets}
    
    # Batch fetch all annotations (2-3 queries total regardless of dataset count)
    from backend.annotation_service import get_annotations_for_training, compute_class_counts
    
    all_annotations_map = {}
    if all_dataset_ids:
        all_annotations_map = get_annotations_for_training(all_dataset_ids, all_dataset_types)
    
    # Group annotations by project for aggregation
    annotations_by_project: dict[str, dict] = {p["id"]: {} for p in projects}
    
    # Map item_ids to their project based on dataset membership
    dataset_items = {ds["id"]: set() for ds in all_datasets}
    
    # For images, we need to know which dataset each image belongs to
    # The annotation_map keys are item_ids (image or keyframe IDs)
    # We need to resolve item_id -> dataset_id -> project_id
    # This requires an additional query, but only once for all items
    if all_annotations_map:
        # Get all image/keyframe -> dataset mapping in batch
        image_dataset_ids = [ds["id"] for ds in all_datasets if ds.get("type") != "video"]
        video_dataset_ids = [ds["id"] for ds in all_datasets if ds.get("type") == "video"]
        
        item_to_project: dict[str, str] = {}
        
        if image_dataset_ids:
            images_result = (
                supabase.table("images")
                .select("id, dataset_id")
                .in_("dataset_id", image_dataset_ids)
                .execute()
            )
            for img in (images_result.data or []):
                ds_id = img.get("dataset_id")
                project_id = dataset_to_project.get(ds_id)
                if project_id:
                    item_to_project[img["id"]] = project_id
        
        if video_dataset_ids:
            videos_result = (
                supabase.table("videos")
                .select("id, dataset_id")
                .in_("dataset_id", video_dataset_ids)
                .execute()
            )
            video_to_dataset = {v["id"]: v.get("dataset_id") for v in (videos_result.data or [])}
            video_ids = list(video_to_dataset.keys())
            
            if video_ids:
                keyframes_result = (
                    supabase.table("keyframes")
                    .select("id, video_id")
                    .in_("video_id", video_ids)
                    .execute()
                )
                for kf in (keyframes_result.data or []):
                    ds_id = video_to_dataset.get(kf.get("video_id"))
                    project_id = dataset_to_project.get(ds_id)
                    if project_id:
                        item_to_project[kf["id"]] = project_id
        
        # Now aggregate annotations by project
        for item_id, annotations in all_annotations_map.items():
            project_id = item_to_project.get(item_id)
            if project_id:
                annotations_by_project[project_id][item_id] = annotations
    
    # Build enriched project list with class counts
    enriched_projects = []
    for p in projects:
        project_id = p["id"]
        project_datasets = datasets_by_project.get(project_id, [])
        project_classes = project_classes_map.get(project_id, [])
        
        # Compute class counts for this project's annotations
        project_annotations = annotations_by_project.get(project_id, {})
        aggregated_counts = compute_class_counts(project_annotations, project_classes=project_classes)
        
        enriched_projects.append({
            **p,
            "dataset_count": len(project_datasets),
            "class_counts": aggregated_counts,
        })
    
    return enriched_projects


def get_user_projects(user_id: str) -> list[dict]:
    """Get all projects for a user, sorted by last accessed (most recent first).
    
    MULTI-USER: Returns owned + member + admin-company projects.
    Falls back to created_at for projects never accessed.
    """
    projects = _get_accessible_projects(user_id)
    
    # Sort in Python: last_accessed_at DESC, fallback to created_at DESC for NULLs
    def sort_key(p):
        # Return tuple (priority, timestamp) - higher priority sorts first with reverse=True
        accessed = p.get("last_accessed_at")
        created = p.get("created_at", "")
        if accessed:
            return (1, accessed)  # 1 = accessed (higher priority, sorts first)
        return (0, created)  # 0 = never accessed (lower priority, sorts after)
    
    projects.sort(key=sort_key, reverse=True)
    return projects


def create_project(
    user_id: str,
    name: str,
    description: str = "",
) -> dict:
    """Create a new project container for a user.
    
    Args:
        user_id: User's UUID
        name: Project name
        description: Optional project description
    """
    supabase = get_supabase()
    data = {
        "user_id": user_id,
        "name": name,
        "description": description,
    }
    
    result = supabase.table("projects").insert(data).execute()
    return result.data[0] if result.data else None



def get_project(project_id: str) -> dict | None:
    """Get a project by ID."""
    supabase = get_supabase()
    result = supabase.table("projects").select("*").eq("id", project_id).single().execute()
    return result.data if result.data else None


def update_project(project_id: str, **updates) -> dict | None:
    """Update a project's fields."""
    supabase = get_supabase()
    result = supabase.table("projects").update(updates).eq("id", project_id).execute()
    return result.data[0] if result.data else None


def touch_project_accessed(project_id: str) -> None:
    """Update last_accessed_at timestamp for a project (called on project entry)."""
    @_get_auth_retry()
    def _update():
        supabase = get_supabase()
        from datetime import datetime, timezone
        supabase.table("projects").update(
            {"last_accessed_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", project_id).execute()
    
    try:
        _update()
    except Exception as e:
        print(f"[WARN] Failed to touch project access time: {e}")


def delete_project(project_id: str) -> bool:
    """Delete a project by ID.
    
    Dependent records (api_models, api_keys, api_jobs, api_usage_logs)
    are automatically removed via ON DELETE CASCADE at the database level.
    """
    supabase = get_supabase()
    try:
        result = supabase.table("projects").delete().eq("id", project_id).execute()
        return len(result.data) > 0 if result.data else False
    except Exception as e:
        print(f"[ERROR] Failed to delete project: {e}")
        return False


def get_project_dataset_count(project_id: str) -> int:
    """Get the count of datasets in a project."""
    supabase = get_supabase()
    result = supabase.table("datasets").select("id", count="exact").eq("project_id", project_id).execute()
    return result.count or 0




# =============================================================================
# DATASET OPERATIONS
# =============================================================================

def get_project_datasets(project_id: str) -> list[dict]:
    """Get all datasets within a project, sorted by last accessed (most recent first).
    
    Falls back to created_at for datasets never accessed.
    """
    @_get_auth_retry()
    def _fetch():
        supabase = get_supabase()
        return (
            supabase.table("datasets")
            .select("*")
            .eq("project_id", project_id)
            .execute()
        )
    
    result = _fetch()
    datasets = result.data or []
    
    # Sort in Python: last_accessed_at DESC, fallback to created_at DESC for NULLs
    def sort_key(d):
        # Use last_accessed_at if present, otherwise use created_at
        # Return tuple (priority, timestamp) - higher priority sorts first with reverse=True
        accessed = d.get("last_accessed_at")
        created = d.get("created_at", "")
        if accessed:
            return (1, accessed)  # 1 = accessed (higher priority, sorts first)
        return (0, created)  # 0 = never accessed (lower priority, sorts after)
    
    datasets.sort(key=sort_key, reverse=True)
    return datasets


def get_user_datasets(user_id: str) -> list[dict]:
    """Get all datasets across all projects for a user (via join)."""
    supabase = get_supabase()
    # Get all project IDs for this user first
    projects = get_user_projects(user_id)
    project_ids = [p["id"] for p in projects]
    if not project_ids:
        return []
    result = (
        supabase.table("datasets")
        .select("*")
        .in_("project_id", project_ids)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def create_dataset(
    project_id: str,
    name: str,
    type: str = "image",
    classes: list[str] = None,  # DEPRECATED - classes are stored at project level
    description: str = "",
    usage_tag: str = "train"
) -> dict:
    """Create a new dataset in a project with usage tag (train/validation).
    
    Note: The `classes` parameter is deprecated. Classes should be managed at the
    project level via update_project(project_id, classes=...). If classes are passed
    here, they will be ignored (not stored in dataset).
    """
    if classes:
        print(f"[WARN] create_dataset received classes={classes} but classes are project-level. Ignoring.")
    
    supabase = get_supabase()
    result = supabase.table("datasets").insert({
        "project_id": project_id,
        "name": name,
        "type": type,
        "description": description,
        "usage_tag": usage_tag,
    }).execute()
    return result.data[0] if result.data else None


def get_dataset(dataset_id: str) -> dict | None:
    """Get a dataset by ID."""
    supabase = get_supabase()
    result = supabase.table("datasets").select("*").eq("id", dataset_id).single().execute()
    return result.data if result.data else None


def update_dataset(dataset_id: str, **updates) -> dict | None:
    """Update a dataset's fields."""
    supabase = get_supabase()
    result = supabase.table("datasets").update(updates).eq("id", dataset_id).execute()
    return result.data[0] if result.data else None


def touch_dataset_accessed(dataset_id: str) -> None:
    """Update last_accessed_at timestamp for a dataset (called on dataset entry)."""
    @_get_auth_retry()
    def _update():
        supabase = get_supabase()
        from datetime import datetime, timezone
        supabase.table("datasets").update(
            {"last_accessed_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", dataset_id).execute()
    
    try:
        _update()
    except Exception as e:
        print(f"[WARN] Failed to touch dataset access time: {e}")


def delete_dataset(dataset_id: str) -> bool:
    """Delete a dataset by ID."""
    supabase = get_supabase()
    result = supabase.table("datasets").delete().eq("id", dataset_id).execute()
    return len(result.data) > 0 if result.data else False


def get_project_datasets_by_tag(project_id: str, usage_tag: str) -> list[dict]:
    """Get datasets filtered by usage tag (train/validation)."""
    supabase = get_supabase()
    result = (
        supabase.table("datasets")
        .select("*")
        .eq("project_id", project_id)
        .eq("usage_tag", usage_tag)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


# =============================================================================
# IMAGE OPERATIONS (Now linked to datasets)
# =============================================================================

def create_image(
    dataset_id: str,
    filename: str,
    r2_path: str,
    width: int = None,
    height: int = None,
    captured_at: str = None,
    camera_make: str = None,
    camera_model: str = None,
    is_night_shot: bool = None,
) -> dict | None:
    """Create a new image record for a dataset."""
    supabase = get_supabase()
    data = {
        "dataset_id": dataset_id,
        "filename": filename,
        "r2_path": r2_path,
    }
    if width is not None:
        data["width"] = width
    if height is not None:
        data["height"] = height
    if captured_at is not None:
        data["captured_at"] = captured_at
    if camera_make is not None:
        data["camera_make"] = camera_make
    if camera_model is not None:
        data["camera_model"] = camera_model
    if is_night_shot is not None:
        data["is_night_shot"] = is_night_shot
    
    result = supabase.table("images").insert(data).execute()
    return result.data[0] if result.data else None


def get_dataset_images(dataset_id: str) -> list[dict]:
    """Get all images for a dataset, ordered by creation date."""
    supabase = get_supabase()
    result = (
        supabase.table("images")
        .select("*")
        .eq("dataset_id", dataset_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


def get_image(image_id: str) -> dict | None:
    """Get a single image by ID."""
    supabase = get_supabase()
    result = supabase.table("images").select("*").eq("id", image_id).single().execute()
    return result.data if result.data else None


def update_image(image_id: str, **updates) -> dict | None:
    """Update an image's fields (e.g., labeled=True)."""
    supabase = get_supabase()
    result = supabase.table("images").update(updates).eq("id", image_id).execute()
    return result.data[0] if result.data else None


def delete_image(image_id: str) -> bool:
    """Delete an image record by ID."""
    supabase = get_supabase()
    result = supabase.table("images").delete().eq("id", image_id).execute()
    return len(result.data) > 0 if result.data else False


def get_dataset_image_count(dataset_id: str, labeled_only: bool = False) -> int:
    """Get the count of images in a dataset."""
    supabase = get_supabase()
    query = supabase.table("images").select("id", count="exact").eq("dataset_id", dataset_id)
    if labeled_only:
        query = query.eq("labeled", True)
    result = query.execute()
    return result.count or 0


def get_dataset_camera_stats(dataset_id: str) -> dict:
    """Get camera stats for a dataset from EXIF metadata.
    
    Returns:
        {
            "cameras": [{"model": "Bushnell 87C", "count": 54}, ...],
            "date_min": "2024-12-07T05:42:17" or None,
            "date_max": "2025-01-15T22:30:00" or None,
            "day_count": 62,
            "night_count": 17,
            "total_with_exif": 79,
        }
    """
    supabase = get_supabase()
    result = (
        supabase.table("images")
        .select("camera_make, camera_model, captured_at, is_night_shot")
        .eq("dataset_id", dataset_id)
        .execute()
    )
    images = result.data or []
    
    # Aggregate
    camera_counts: dict[str, int] = {}
    dates = []
    day_count = 0
    night_count = 0
    total_with_exif = 0
    
    for img in images:
        model = img.get("camera_model")
        make = img.get("camera_make")
        captured = img.get("captured_at")
        is_night = img.get("is_night_shot")
        
        if model or make or captured:
            total_with_exif += 1
        
        # Camera grouping: prefer "Make Model", fallback to Model or Make
        camera_label = None
        if make and model:
            # Avoid "BUSHNELL BUSHNELL 87C" — check if make is already in model
            if make.upper() in model.upper():
                camera_label = model
            else:
                camera_label = f"{make} {model}"
        elif model:
            camera_label = model
        elif make:
            camera_label = make
        
        if camera_label:
            camera_counts[camera_label] = camera_counts.get(camera_label, 0) + 1
        
        if captured:
            dates.append(captured)
        
        if is_night is True:
            night_count += 1
        elif is_night is False:
            day_count += 1
    
    # Sort cameras by count descending
    cameras = sorted(
        [{"model": m, "count": c} for m, c in camera_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )
    
    return {
        "cameras": cameras,
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "day_count": day_count,
        "night_count": night_count,
        "total_with_exif": total_with_exif,
    }


def get_project_camera_stats(project_id: str) -> dict:
    """Get aggregated camera stats across all image datasets in a project."""
    datasets = get_project_datasets(project_id)
    image_dataset_ids = [d["id"] for d in datasets if d.get("type") != "video"]
    
    if not image_dataset_ids:
        return {"cameras": [], "date_min": None, "date_max": None, "day_count": 0, "night_count": 0, "total_with_exif": 0}
    
    supabase = get_supabase()
    
    # Batch query across all datasets
    all_images = []
    for ds_id in image_dataset_ids:
        result = (
            supabase.table("images")
            .select("camera_make, camera_model, captured_at, is_night_shot")
            .eq("dataset_id", ds_id)
            .execute()
        )
        all_images.extend(result.data or [])
    
    # Same aggregation as dataset-level
    camera_counts: dict[str, int] = {}
    dates = []
    day_count = 0
    night_count = 0
    total_with_exif = 0
    
    for img in all_images:
        model = img.get("camera_model")
        make = img.get("camera_make")
        captured = img.get("captured_at")
        is_night = img.get("is_night_shot")
        
        if model or make or captured:
            total_with_exif += 1
        
        camera_label = None
        if make and model:
            if make.upper() in model.upper():
                camera_label = model
            else:
                camera_label = f"{make} {model}"
        elif model:
            camera_label = model
        elif make:
            camera_label = make
        
        if camera_label:
            camera_counts[camera_label] = camera_counts.get(camera_label, 0) + 1
        
        if captured:
            dates.append(captured)
        
        if is_night is True:
            night_count += 1
        elif is_night is False:
            day_count += 1
    
    cameras = sorted(
        [{"model": m, "count": c} for m, c in camera_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )
    
    return {
        "cameras": cameras,
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "day_count": day_count,
        "night_count": night_count,
        "total_with_exif": total_with_exif,
    }


def bulk_create_images(dataset_id: str, images: list[dict]) -> list[dict]:
    """
    Bulk create image records for a dataset.
    
    Args:
        dataset_id: The dataset to add images to
        images: List of dicts with keys: filename, r2_path, width, height, labeled
    
    Returns:
        List of created image records
    """
    if not images:
        return []
    
    supabase = get_supabase()
    
    # Prepare records with dataset_id
    records = []
    for img in images:
        record = {
            "dataset_id": dataset_id,
            "filename": img.get("filename", ""),
            "r2_path": img.get("r2_path", ""),
            "width": img.get("width"),
            "height": img.get("height"),
            "labeled": img.get("labeled", False),
        }
        # Include annotations if provided (for dataset copy/migration)
        if "annotations" in img and img["annotations"] is not None:
            record["annotations"] = img["annotations"]
        if "annotation_count" in img:
            record["annotation_count"] = img["annotation_count"]
        # EXIF metadata
        for field in ("captured_at", "camera_make", "camera_model", "is_night_shot"):
            if field in img and img[field] is not None:
                record[field] = img[field]
        records.append(record)
    
    result = supabase.table("images").insert(records).execute()
    return result.data or []


def bulk_delete_images(image_ids: list[str]) -> int:
    """
    Delete multiple images in a single query using IN clause.
    
    Args:
        image_ids: List of image UUIDs to delete
        
    Returns:
        Number of images deleted
    """
    if not image_ids:
        return 0
    
    supabase = get_supabase()
    result = supabase.table("images").delete().in_("id", image_ids).execute()
    return len(result.data) if result.data else 0


def get_image_annotations(image_id: str) -> list | None:
    """Retrieve annotations for a specific image from Supabase JSONB column.
    
    Args:
        image_id: UUID of the image
        
    Returns:
        - List of annotation dicts if found in Supabase
        - None if annotations column is NULL (fallback to R2)
        - Empty list if image has no annotations
    """
    try:
        supabase = get_supabase()
        result = (
            supabase.table("images")
            .select("annotations")
            .eq("id", image_id)
            .single()
            .execute()
        )
        
        if result.data:
            return result.data.get("annotations")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to fetch annotations from Supabase for image {image_id}: {e}")
        return None


def get_dataset_image_annotations(dataset_id: str) -> dict[str, list]:
    """Load all annotations for all images in a dataset (batch load).
    
    This is much faster than loading annotations one by one - single query
    instead of N queries for N images.
    
    Args:
        dataset_id: UUID of the dataset
        
    Returns:
        Dict mapping image_id -> annotations list
        Only includes images that have non-NULL annotations in Supabase.
    """
    try:
        supabase = get_supabase()
        result = (
            supabase.table("images")
            .select("id, annotations")
            .eq("dataset_id", dataset_id)
            .execute()
        )
        
        # Only return images with non-NULL annotations
        return {
            img["id"]: img["annotations"] 
            for img in (result.data or [])
            if img.get("annotations") is not None
        }
    except Exception as e:
        print(f"[ERROR] Failed to batch load annotations for dataset {dataset_id}: {e}")
        return {}


def update_image_annotations(image_id: str, annotations: list) -> dict | None:
    """Save annotations to Supabase for an image.
    
    Updates both the annotations JSONB column and annotation_count.
    
    Args:
        image_id: UUID of the image
        annotations: List of annotation dicts
        
    Returns:
        Updated image record or None on error
    """
    try:
        supabase = get_supabase()
        result = (
            supabase.table("images")
            .update({
                "annotations": annotations,
                "annotation_count": len(annotations),
                "labeled": len(annotations) > 0
            })
            .eq("id", image_id)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[ERROR] Failed to save annotations to Supabase for image {image_id}: {e}")
        return None


# =============================================================================
# VIDEO OPERATIONS
# =============================================================================


def create_video(
    dataset_id: str,
    filename: str,
    r2_path: str,
    duration_seconds: float = None,
    frame_count: int = None,
    fps: float = None,
    width: int = None,
    height: int = None,
    thumbnail_path: str = None,
    proxy_r2_path: str = None
) -> dict | None:
    """Create a new video record for a dataset."""
    supabase = get_supabase()
    data = {
        "dataset_id": dataset_id,
        "filename": filename,
        "r2_path": r2_path,
    }
    if duration_seconds is not None:
        data["duration_seconds"] = duration_seconds
    if frame_count is not None:
        data["frame_count"] = frame_count
    if fps is not None:
        data["fps"] = fps
    if width is not None:
        data["width"] = width
    if height is not None:
        data["height"] = height
    if thumbnail_path is not None:
        data["thumbnail_path"] = thumbnail_path
    if proxy_r2_path is not None:
        data["proxy_r2_path"] = proxy_r2_path
    
    result = supabase.table("videos").insert(data).execute()
    return result.data[0] if result.data else None



def get_dataset_videos(dataset_id: str) -> list[dict]:
    """Get all videos for a dataset, ordered by creation date."""
    supabase = get_supabase()
    result = (
        supabase.table("videos")
        .select("*")
        .eq("dataset_id", dataset_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


def get_video(video_id: str) -> dict | None:
    """Get a single video by ID."""
    supabase = get_supabase()
    result = supabase.table("videos").select("*").eq("id", video_id).single().execute()
    return result.data if result.data else None


def update_video(video_id: str, **updates) -> dict | None:
    """Update a video's fields."""
    supabase = get_supabase()
    result = supabase.table("videos").update(updates).eq("id", video_id).execute()
    return result.data[0] if result.data else None


def delete_video(video_id: str) -> bool:
    """Delete a video record by ID."""
    supabase = get_supabase()
    result = supabase.table("videos").delete().eq("id", video_id).execute()
    return len(result.data) > 0 if result.data else False


def get_dataset_video_count(dataset_id: str) -> int:
    """Get the count of videos in a dataset."""
    supabase = get_supabase()
    result = supabase.table("videos").select("id", count="exact").eq("dataset_id", dataset_id).execute()
    return result.count or 0


# Legacy aliases for backward compatibility during migration
get_project_images = get_dataset_images
get_project_image_count = get_dataset_image_count


def bulk_delete_videos(video_ids: list[str]) -> int:
    """
    Delete multiple videos in a single query using IN clause.
    Also deletes all associated keyframes in a single query.
    
    Args:
        video_ids: List of video UUIDs to delete
        
    Returns:
        Number of videos deleted
    """
    if not video_ids:
        return 0
    
    supabase = get_supabase()
    
    # First delete all associated keyframes in a single query
    supabase.table("keyframes").delete().in_("video_id", video_ids).execute()
    
    # Then delete the videos
    result = supabase.table("videos").delete().in_("id", video_ids).execute()
    return len(result.data) if result.data else 0


def bulk_create_videos(dataset_id: str, videos: list[dict]) -> list[dict]:
    """
    Bulk create video records for a dataset.
    
    Args:
        dataset_id: The dataset to add videos to
        videos: List of dicts with keys: filename, r2_path, duration_seconds, 
                frame_count, fps, width, height, thumbnail_path
    
    Returns:
        List of created video records
    """
    if not videos:
        return []
    
    supabase = get_supabase()
    
    records = []
    for vid in videos:
        records.append({
            "dataset_id": dataset_id,
            "filename": vid.get("filename", ""),
            "r2_path": vid.get("r2_path", ""),
            "duration_seconds": vid.get("duration_seconds"),
            "frame_count": vid.get("frame_count"),
            "fps": vid.get("fps"),
            "width": vid.get("width"),
            "height": vid.get("height"),
            "thumbnail_path": vid.get("thumbnail_path"),
        })
    
    result = supabase.table("videos").insert(records).execute()
    return result.data or []


def bulk_create_keyframes(keyframes: list[dict]) -> list[dict]:
    """
    Bulk create keyframe records.
    
    Args:
        keyframes: List of dicts with keys: video_id, frame_number, timestamp,
                   thumbnail_path, annotations, annotation_count
    
    Returns:
        List of created keyframe records
    """
    if not keyframes:
        return []
    
    supabase = get_supabase()
    
    records = []
    for kf in keyframes:
        records.append({
            "video_id": kf.get("video_id"),
            "frame_number": kf.get("frame_number"),
            "timestamp": kf.get("timestamp"),
            "thumbnail_path": kf.get("thumbnail_path"),
            "annotations": kf.get("annotations"),
            "annotation_count": kf.get("annotation_count", 0),
        })
    
    result = supabase.table("keyframes").insert(records).execute()
    return result.data or []


# =============================================================================
# KEYFRAME OPERATIONS (for video labeling)
# =============================================================================


def create_keyframe(
    video_id: str,
    frame_number: int,
    timestamp: float,
    thumbnail_path: str = None
) -> dict | None:
    """Create a new keyframe record for a video."""
    supabase = get_supabase()
    data = {
        "video_id": video_id,
        "frame_number": frame_number,
        "timestamp": timestamp,
    }
    if thumbnail_path is not None:
        data["thumbnail_path"] = thumbnail_path
    
    result = supabase.table("keyframes").insert(data).execute()
    return result.data[0] if result.data else None


def get_video_keyframes(video_id: str) -> list[dict]:
    """Get all keyframes for a video, ordered by frame number."""
    supabase = get_supabase()
    result = (
        supabase.table("keyframes")
        .select("*")
        .eq("video_id", video_id)
        .order("frame_number", desc=False)
        .execute()
    )
    return result.data or []


def get_keyframe(keyframe_id: str) -> dict | None:
    """Get a single keyframe by ID."""
    supabase = get_supabase()
    result = supabase.table("keyframes").select("*").eq("id", keyframe_id).single().execute()
    return result.data if result.data else None


def update_keyframe(keyframe_id: str, **updates) -> dict | None:
    """Update a keyframe's fields (e.g., annotation_count)."""
    supabase = get_supabase()
    result = supabase.table("keyframes").update(updates).eq("id", keyframe_id).execute()
    return result.data[0] if result.data else None


def delete_keyframe(keyframe_id: str) -> bool:
    """Delete a keyframe record by ID."""
    supabase = get_supabase()
    result = supabase.table("keyframes").delete().eq("id", keyframe_id).execute()
    return len(result.data) > 0 if result.data else False


def get_video_keyframe_count(video_id: str) -> int:
    """Get the count of keyframes for a video."""
    supabase = get_supabase()
    result = supabase.table("keyframes").select("id", count="exact").eq("video_id", video_id).execute()
    return result.count or 0


def get_dataset_unlabeled_keyframes_count(dataset_id: str) -> int:
    """Get the count of unlabeled keyframes across all videos in a dataset.
    
    Args:
        dataset_id: UUID of the dataset
        
    Returns:
        Count of keyframes with annotation_count = 0
    """
    supabase = get_supabase()
    # Join keyframes with videos to filter by dataset_id
    # Count keyframes where annotation_count is 0
    result = (
        supabase.table("keyframes")
        .select("id", count="exact")
        .eq("videos.dataset_id", dataset_id)  
        .eq("annotation_count", 0)
        .execute()
    )
    return result.count or 0


def get_unlabeled_keyframes_for_dataset(dataset_id: str) -> list[dict]:
    """Get all unlabeled keyframes for all videos in a dataset.
    
    This fetches keyframes with annotation_count = 0 from all videos
    in the specified dataset. Useful for autolabeling workflows.
    
    Args:
        dataset_id: UUID of the dataset
        
    Returns:
        List of keyframe records with video info joined
    """
    supabase = get_supabase()
    # Get all videos in this dataset first
    videos = get_dataset_videos(dataset_id)
    if not videos:
        return []
    
    video_ids = [v["id"] for v in videos]
    
    # Get all unlabeled keyframes for these videos
    # Note: We use 'in_' filter for video_id and filter by annotation_count
    result = (
        supabase.table("keyframes")
        .select("*")
        .in_("video_id", video_ids)
        .eq("annotation_count", 0)
        .order("video_id", desc=False)
        .order("frame_number", desc=False)
        .execute()
    )
    
    return result.data or []



def delete_video_keyframes(video_id: str) -> list[dict]:
    """Delete all keyframes for a video and return them for R2 cleanup."""
    supabase = get_supabase()
    # First get all keyframes to return them for R2 cleanup
    keyframes = get_video_keyframes(video_id)
    
    # Delete all keyframes for this video
    if keyframes:
        supabase.table("keyframes").delete().eq("video_id", video_id).execute()
    
    return keyframes


def get_keyframe_annotations(keyframe_id: str) -> list | None:
    """Retrieve annotations for a specific keyframe from Supabase JSONB column.
    
    Args:
        keyframe_id: UUID of the keyframe
        
    Returns:
        - List of annotation dicts if found in Supabase
        - None if annotations column is NULL (fallback to R2)
        - Empty list if keyframe has no annotations
    """
    try:
        supabase = get_supabase()
        result = (
            supabase.table("keyframes")
            .select("annotations")
            .eq("id", keyframe_id)
            .single()
            .execute()
        )
        
        if result.data:
            return result.data.get("annotations")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to fetch annotations from Supabase for keyframe {keyframe_id}: {e}")
        return None


def get_video_keyframe_annotations(video_id: str) -> dict[str, list]:
    """Load all annotations for all keyframes in a video (batch load).
    
    This is much faster than loading annotations one by one - single query
    instead of N queries for N keyframes.
    
    Args:
        video_id: UUID of the video
        
    Returns:
        Dict mapping keyframe_id -> annotations list
        Only includes keyframes that have non-NULL annotations in Supabase.
    """
    try:
        supabase = get_supabase()
        result = (
            supabase.table("keyframes")
            .select("id, annotations")
            .eq("video_id", video_id)
            .execute()
        )
        
        # Only return keyframes with non-NULL annotations
        return {
            kf["id"]: kf["annotations"] 
            for kf in (result.data or [])
            if kf.get("annotations") is not None
        }
    except Exception as e:
        print(f"[ERROR] Failed to batch load annotations for video {video_id}: {e}")
        return {}


def get_dataset_class_counts_from_keyframes(
    dataset_id: str,
    project_classes: list[str] = None
) -> dict[str, int]:
    """
    Compute class counts from keyframes.annotations for all videos in a dataset.
    
    Uses efficient batch queries:
    1. One query: Get all video_ids for this dataset
    2. One query: Fetch ALL keyframes with annotations at once using .in_()
    3. Python: Count class occurrences
    
    Args:
        dataset_id: UUID of the dataset
        project_classes: Optional. If provided, resolves class_name from class_id
                        when annotations don't have class_name stored (post-migration).
        
    Returns:
        Dict mapping class_name -> count
    """
    try:
        supabase = get_supabase()
        
        # Query 1: Get all video IDs for this dataset
        videos_result = (
            supabase.table("videos")
            .select("id")
            .eq("dataset_id", dataset_id)
            .execute()
        )
        video_ids = [v["id"] for v in (videos_result.data or [])]
        
        if not video_ids:
            return {}
        
        # Query 2: Batch fetch ALL keyframes with annotations in ONE call
        keyframes_result = (
            supabase.table("keyframes")
            .select("annotations")
            .in_("video_id", video_ids)
            .execute()
        )
        
        # Count class occurrences in Python
        class_counts: dict[str, int] = {}
        for kf in (keyframes_result.data or []):
            annotations = kf.get("annotations") or []
            for ann in annotations:
                # Try class_name first (legacy annotations)
                class_name = ann.get("class_name")
                
                # If no class_name, resolve from class_id using project_classes
                if not class_name and project_classes:
                    class_id = ann.get("class_id", 0)
                    if 0 <= class_id < len(project_classes):
                        class_name = project_classes[class_id]
                    else:
                        class_name = "Unknown"
                elif not class_name:
                    class_name = "Unknown"
                
                class_counts[class_name] = class_counts.get(class_name, 0) + 1
        
        return class_counts
        
    except Exception as e:
        print(f"[ERROR] Failed to get class counts from keyframes for dataset {dataset_id}: {e}")
        return {}


# =============================================================================
# TRAINING RUNS OPERATIONS
# =============================================================================

def create_training_run(
    project_id: str,
    dataset_ids: list[str],
    user_id: str,
    config: dict,
    target: str = "cloud",
    dataset_names: list[str] | None = None,
    classes_snapshot: list[str] | None = None,
    model_type: str = "detection",
    parent_run_id: str | None = None,
) -> dict | None:
    """Create a new training run with status='pending' at project level.
    
    Args:
        project_id: UUID of the project
        dataset_ids: List of dataset UUIDs to train on
        user_id: UUID of the user
        config: Training configuration dict (epochs, batch_size, etc.)
        target: 'cloud' or 'local'
        dataset_names: Optional list of dataset names for display
        classes_snapshot: Optional snapshot of class names at time of training
        model_type: 'detection', 'classification', or 'sam3_finetune' (default: 'detection')
        parent_run_id: Optional parent run ID for continue training
    """
    supabase = get_supabase()
    
    data = {
        "project_id": project_id,
        "dataset_ids": dataset_ids,
        "user_id": user_id,
        "config": config,
        "target": target,
        "status": "pending",
        "model_type": model_type,
    }
    
    # Add optional snapshot fields if provided
    if dataset_names is not None:
        data["dataset_names"] = dataset_names
    if classes_snapshot is not None:
        data["classes_snapshot"] = classes_snapshot
    if parent_run_id is not None:
        data["parent_run_id"] = parent_run_id
    
    result = supabase.table("training_runs").insert(data).execute()
    return result.data[0] if result.data else None


def get_training_run(run_id: str) -> dict | None:
    """Get a single training run by ID."""
    supabase = get_supabase()
    result = supabase.table("training_runs").select("*").eq("id", run_id).single().execute()
    return result.data if result.data else None


def get_project_training_runs(project_id: str) -> list[dict]:
    """Get all training runs for a project, ordered by creation date (newest first)."""
    supabase = get_supabase()
    result = (
        supabase.table("training_runs")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_dataset_training_runs(dataset_id: str) -> list[dict]:
    """Get all training runs that include a dataset (legacy/compatibility)."""
    supabase = get_supabase()
    result = (
        supabase.table("training_runs")
        .select("*")
        .contains("dataset_ids", [dataset_id])
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def update_training_run(run_id: str, **updates) -> dict | None:
    """Update a training run's fields (status, metrics, timestamps, etc.)."""
    supabase = get_supabase()
    result = supabase.table("training_runs").update(updates).eq("id", run_id).execute()
    return result.data[0] if result.data else None


def get_pending_local_runs(user_id: str) -> list[dict]:
    """Get all pending local training runs for a user (for bare metal polling client)."""
    supabase = get_supabase()
    result = (
        supabase.table("training_runs")
        .select("*")
        .eq("user_id", user_id)
        .eq("target", "local")
        .eq("status", "pending")
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


def claim_training_run(run_id: str, machine_id: str) -> dict | None:
    """
    Atomically claim a pending training run for a machine.
    Sets claimed_by and status='queued'. Returns None if already claimed.
    """
    supabase = get_supabase()
    # Only claim if still pending
    result = (
        supabase.table("training_runs")
        .update({"claimed_by": machine_id, "status": "queued"})
        .eq("id", run_id)
        .eq("status", "pending")
        .execute()
    )
    return result.data[0] if result.data else None


def delete_training_run(run_id: str) -> dict | None:
    """
    Delete a training run by ID and return the deleted run data.
    Returns the deleted run record (for R2 cleanup) or None if not found.
    """
    supabase = get_supabase()
    # First get the run data (for artifacts_r2_prefix cleanup)
    run = get_training_run(run_id)
    if not run:
        return None
    
    # Delete the run
    result = supabase.table("training_runs").delete().eq("id", run_id).execute()
    if result.data:
        return run  # Return original run data for R2 cleanup
    return None


# =============================================================================
# MODELS OPERATIONS
# =============================================================================

def create_model(
    training_run_id: str,
    dataset_id: str,
    user_id: str,
    name: str,
    weights_path: str,
    volume_path: str = None,
    metrics: dict = None,
    model_type: str = "detection",
    top1_accuracy: float = None,
    top5_accuracy: float = None,
) -> dict | None:
    """Create a new model record with optional Modal volume path.
    
    Args:
        training_run_id: UUID of the training run that created this model
        dataset_id: UUID of the primary dataset used for training
        user_id: UUID of the user
        name: Display name for the model
        weights_path: R2 path to the model weights file
        volume_path: Optional Modal volume path
        metrics: Optional dict of training metrics
        model_type: 'detection' or 'classification' (default: 'detection')
        top1_accuracy: Top-1 accuracy for classification models
        top5_accuracy: Top-5 accuracy for classification models
    """
    supabase = get_supabase()
    
    # Auto-resolve project_id from dataset_id for team model sharing
    project_id = None
    if dataset_id:
        ds = supabase.table("datasets").select("project_id").eq("id", dataset_id).single().execute()
        if ds.data:
            project_id = ds.data["project_id"]
    
    data = {
        "training_run_id": training_run_id,
        "dataset_id": dataset_id,
        "user_id": user_id,
        "name": name,
        "weights_path": weights_path,
        "model_type": model_type,
    }
    if project_id is not None:
        data["project_id"] = project_id
    if volume_path is not None:
        data["volume_path"] = volume_path
    if metrics is not None:
        data["metrics"] = metrics
    if top1_accuracy is not None:
        data["top1_accuracy"] = top1_accuracy
    if top5_accuracy is not None:
        data["top5_accuracy"] = top5_accuracy
    
    result = supabase.table("models").insert(data).execute()
    return result.data[0] if result.data else None


def get_model(model_id: str) -> dict | None:
    """Get a single model by ID."""
    supabase = get_supabase()
    result = supabase.table("models").select("*").eq("id", model_id).single().execute()
    return result.data if result.data else None


def get_dataset_models(dataset_id: str) -> list[dict]:
    """Get all models for a dataset, ordered by creation date (newest first)."""
    supabase = get_supabase()
    result = (
        supabase.table("models")
        .select("*")
        .eq("dataset_id", dataset_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def set_active_model(model_id: str) -> dict | None:
    """
    Set a model as the active model for its dataset.
    Deactivates all other models in the same dataset first.
    """
    supabase = get_supabase()
    
    # First, get the model to find its dataset_id
    model = get_model(model_id)
    if not model:
        return None
    
    dataset_id = model["dataset_id"]
    
    # Deactivate all models in this dataset
    supabase.table("models").update({"is_active": False}).eq("dataset_id", dataset_id).execute()
    
    # Activate the target model
    result = supabase.table("models").update({"is_active": True}).eq("id", model_id).execute()
    return result.data[0] if result.data else None


def get_active_model(dataset_id: str) -> dict | None:
    """Get the active model for a dataset (if any)."""
    supabase = get_supabase()
    result = (
        supabase.table("models")
        .select("*")
        .eq("dataset_id", dataset_id)
        .eq("is_active", True)
        .single()
        .execute()
    )
    return result.data if result.data else None

def append_training_log(run_id: str, new_logs: str) -> bool:
    """
    Append new logs to the training run's logs column.
    Uses a fetch-update approach to simulate appending.
    """
    if not new_logs:
        return True
        
    supabase = get_supabase()
    
    try:
        # 1. Fetch current logs
        result = supabase.table("training_runs").select("logs").eq("id", run_id).single().execute()
        current_logs = result.data.get("logs", "") or ""
        
        # 2. Append and update
        updated_logs = current_logs + new_logs
        result = supabase.table("training_runs").update({"logs": updated_logs}).eq("id", run_id).execute()
        
        return bool(result.data)
    except Exception as e:
        print(f"[ERROR] Failed to append logs for run {run_id}: {e}")
        return False


# =============================================================================
# CLASS COUNT DYNAMIC COMPUTATION (from annotations)
# =============================================================================

def get_image_class_counts_from_annotations(
    dataset_id: str,
    project_classes: list[str] = None
) -> dict[str, int]:
    """
    Compute class counts from images.annotations for all images in a dataset.
    
    This is the image equivalent of get_dataset_class_counts_from_keyframes().
    
    Args:
        dataset_id: UUID of the dataset
        project_classes: Optional. If provided, resolves class_name from class_id
                        when annotations don't have class_name stored (post-migration).
        
    Returns:
        Dict mapping class_name -> count
        
    Note:
        Now delegates to annotation_service for unified annotation access.
    """
    from backend.annotation_service import get_dataset_annotations, compute_class_counts
    
    annotations_map = get_dataset_annotations(dataset_id, dataset_type="image")
    return compute_class_counts(annotations_map, project_classes=project_classes)


def get_combined_class_counts_for_datasets(
    dataset_ids: list[str],
    dataset_types: dict[str, str],
    project_classes: list[str] = None
) -> dict[str, int]:
    """
    Compute combined class counts across multiple datasets in batched queries.
    
    Args:
        dataset_ids: List of dataset UUIDs to aggregate
        dataset_types: Dict mapping dataset_id -> type ("image" or "video")
        project_classes: Optional. If provided, resolves class_name from
                        class_id when annotations don't have class_name stored.
    
    Returns:
        Dict mapping class_name -> total annotation count across all datasets
        
    Note:
        Now delegates to annotation_service for unified annotation access.
    """
    from backend.annotation_service import compute_class_counts_for_datasets as _compute
    
    return _compute(dataset_ids, dataset_types, project_classes=project_classes)


def rename_class_in_annotations(
    project_id: str,
    old_name: str,
    new_name: str,
    old_idx: int = None,
    new_idx: int = None,
    is_merge: bool = False,
):
    """
    Rename a class in all annotations across all datasets in a project.
    Updates both class_name AND class_id fields in JSONB columns.
    
    This is a GENERATOR that yields (updated_count, total) tuples for progress feedback.
    
    Args:
        project_id: UUID of the project
        old_name: Current class name
        new_name: New class name
        old_idx: Index of the old class (optional, for merge operations)
        new_idx: Index of the target class (optional, for merge operations)
        is_merge: If True, shifts class_ids down after removing old_idx
    
    Yields:
        Tuple of (items_updated_so_far, total_items_to_update)
    """
    supabase = get_supabase()
    
    try:
        # Get all datasets for this project
        datasets = get_project_datasets(project_id)
        
        # First pass: collect all items that need updating
        items_to_update = []  # List of (table_name, record_id, updated_annotations)
        
        for dataset in datasets:
            dataset_id = dataset["id"]
            dataset_type = dataset.get("type", "image")
            
            if dataset_type == "video":
                # Get all videos for this dataset
                videos_result = supabase.table("videos").select("id").eq("dataset_id", dataset_id).execute()
                video_ids = [v["id"] for v in (videos_result.data or [])]
                
                if not video_ids:
                    continue
                
                # Get all keyframes with annotations
                keyframes_result = (
                    supabase.table("keyframes")
                    .select("id, annotations")
                    .in_("video_id", video_ids)
                    .execute()
                )
                
                for kf in (keyframes_result.data or []):
                    annotations = kf.get("annotations", []) or []
                    modified = False
                    
                    for ann in annotations:
                        if ann.get("class_name") == old_name:
                            ann["class_name"] = new_name
                            # Update class_id to target index if provided
                            if new_idx is not None:
                                ann["class_id"] = new_idx
                            modified = True
                        elif is_merge and old_idx is not None:
                            # Shift class_ids down for classes after the removed one
                            c_id = ann.get("class_id", 0)
                            if c_id > old_idx:
                                ann["class_id"] = c_id - 1
                                modified = True
                    
                    if modified:
                        items_to_update.append(("keyframes", kf["id"], annotations))
            
            else:  # image dataset
                # Get all images with annotations for this dataset
                images_result = (
                    supabase.table("images")
                    .select("id, annotations")
                    .eq("dataset_id", dataset_id)
                    .execute()
                )
                
                for img in (images_result.data or []):
                    annotations = img.get("annotations", []) or []
                    modified = False
                    
                    for ann in annotations:
                        if ann.get("class_name") == old_name:
                            ann["class_name"] = new_name
                            # Update class_id to target index if provided
                            if new_idx is not None:
                                ann["class_id"] = new_idx
                            modified = True
                        elif is_merge and old_idx is not None:
                            # Shift class_ids down for classes after the removed one
                            c_id = ann.get("class_id", 0)
                            if c_id > old_idx:
                                ann["class_id"] = c_id - 1
                                modified = True
                    
                    if modified:
                        items_to_update.append(("images", img["id"], annotations))
        
        total = len(items_to_update)
        
        # Yield initial progress (0 of N)
        if total > 0:
            yield (0, total)
        
        # Second pass: update items and yield progress
        for i, (table_name, record_id, annotations) in enumerate(items_to_update):
            supabase.table(table_name).update({"annotations": annotations}).eq("id", record_id).execute()
            
            # Yield progress every 25 items or on last item
            if (i + 1) % 25 == 0 or (i + 1) == total:
                yield (i + 1, total)
        
        print(f"[DEBUG] Renamed class '{old_name}' to '{new_name}' in {total} items (merge={is_merge})")
        
    except Exception as e:
        print(f"[ERROR] Failed to rename class in annotations: {e}")
        import traceback
        traceback.print_exc()


def delete_class_from_annotations(project_id: str, class_name: str, class_idx: int, new_classes: list[str]) -> int:
    """
    Delete annotations with a specific class from all keyframes in a project.
    Also shifts class_id and updates class_name for remaining annotations.
    Updates both database (keyframes.annotations) and R2 label files.
    
    Args:
        project_id: UUID of the project
        class_name: Name of the class to delete
        class_idx: Index of the class being deleted (for shifting)
        new_classes: Updated classes list (after deletion)
    
    Returns:
        Number of keyframes updated
    """
    from backend.r2_storage import R2Client
    
    supabase = get_supabase()
    updated_count = 0
    
    try:
        r2 = R2Client()
        
        # Get all datasets for this project
        datasets = get_project_datasets(project_id)
        
        for dataset in datasets:
            dataset_id = dataset["id"]
            dataset_type = dataset.get("type", "image")
            
            if dataset_type == "video":
                # Get all videos for this dataset
                videos_result = supabase.table("videos").select("id").eq("dataset_id", dataset_id).execute()
                videos = videos_result.data or []
                
                if not videos:
                    continue
                
                video_ids = [v["id"] for v in videos]
                
                # Get all keyframes with annotations
                keyframes_result = (
                    supabase.table("keyframes")
                    .select("id, video_id, frame_number, annotations, annotation_count")
                    .in_("video_id", video_ids)
                    .execute()
                )
                
                for kf in (keyframes_result.data or []):
                    annotations = kf.get("annotations", []) or []
                    if not annotations:
                        continue
                    
                    # Filter out annotations with deleted class and shift remaining
                    new_annotations = []
                    modified = False
                    
                    for ann in annotations:
                        if ann.get("class_name") == class_name:
                            # Skip this annotation (delete it)
                            modified = True
                            continue
                        
                        # Shift class_id if needed
                        c_id = ann.get("class_id", 0)
                        if c_id > class_idx:
                            ann["class_id"] = c_id - 1
                            # Update class_name based on new index
                            if c_id - 1 < len(new_classes):
                                ann["class_name"] = new_classes[c_id - 1]
                            modified = True
                        
                        new_annotations.append(ann)
                    
                    if modified:
                        # Update database
                        supabase.table("keyframes").update({
                            "annotations": new_annotations,
                            "annotation_count": len(new_annotations)
                        }).eq("id", kf["id"]).execute()
                        
                        # Update R2 label file
                        video_id = kf.get("video_id")
                        frame_number = kf.get("frame_number", 0)
                        label_path = f"datasets/{dataset_id}/labels/{video_id}_f{frame_number}.txt"
                        
                        try:
                            # Build YOLO format content from updated annotations
                            yolo_lines = []
                            for ann in new_annotations:
                                c_id = ann.get("class_id", 0)
                                x = ann.get("x", 0)
                                y = ann.get("y", 0)
                                w = ann.get("width", 0)
                                h = ann.get("height", 0)
                                # Convert to YOLO format (center x, center y, width, height)
                                x_center = x + w / 2
                                y_center = y + h / 2
                                yolo_lines.append(f"{c_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}")
                            
                            new_content = "\n".join(yolo_lines)
                            r2.upload_file(
                                file_bytes=new_content.encode('utf-8'),
                                path=label_path,
                                content_type='text/plain'
                            )
                        except Exception as r2_err:
                            print(f"[WARN] Failed to update R2 label file {label_path}: {r2_err}")
                        
                        updated_count += 1
            
            # TODO: Image annotations are also in R2, would need similar handling
        
        print(f"[DEBUG] Deleted class '{class_name}' and updated {updated_count} keyframes (database + R2)")
        return updated_count
        
    except Exception as e:
        print(f"[ERROR] Failed to delete class from annotations: {e}")
        import traceback
        traceback.print_exc()
        return updated_count


# =============================================================================
# DASHBOARD AGGREGATE QUERIES
# =============================================================================

def get_user_stats(user_id: str) -> dict:
    """
    Get aggregate stats for a user's dashboard hub.
    Counts both images (from image datasets) and keyframes (from video datasets).
    
    Returns:
        dict with: project_count, dataset_count, image_count, labeled_count
    """
    supabase = get_supabase()
    
    # Get project count
    projects_result = (
        supabase.table("projects")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    project_count = projects_result.count or 0
    
    # Get project IDs for further queries
    project_ids = [p["id"] for p in (projects_result.data or [])]
    
    if not project_ids:
        return {
            "project_count": 0,
            "dataset_count": 0,
            "image_count": 0,
            "labeled_count": 0,
        }
    
    # Get datasets with their types
    datasets_result = (
        supabase.table("datasets")
        .select("id, type")
        .in_("project_id", project_ids)
        .execute()
    )
    datasets = datasets_result.data or []
    dataset_count = len(datasets)
    
    if not datasets:
        return {
            "project_count": project_count,
            "dataset_count": 0,
            "image_count": 0,
            "labeled_count": 0,
        }
    
    # Separate image and video datasets
    image_dataset_ids = [d["id"] for d in datasets if d.get("type") != "video"]
    video_dataset_ids = [d["id"] for d in datasets if d.get("type") == "video"]
    
    total_count = 0
    labeled_count = 0
    
    # Count images from image datasets
    if image_dataset_ids:
        images_result = (
            supabase.table("images")
            .select("id", count="exact")
            .in_("dataset_id", image_dataset_ids)
            .execute()
        )
        total_count += images_result.count or 0
        
        labeled_images_result = (
            supabase.table("images")
            .select("id", count="exact")
            .in_("dataset_id", image_dataset_ids)
            .eq("labeled", True)
            .execute()
        )
        labeled_count += labeled_images_result.count or 0
    
    # Count keyframes from video datasets
    if video_dataset_ids:
        # First get all video IDs for these datasets
        videos_result = (
            supabase.table("videos")
            .select("id")
            .in_("dataset_id", video_dataset_ids)
            .execute()
        )
        video_ids = [v["id"] for v in (videos_result.data or [])]
        
        if video_ids:
            # Count total keyframes
            keyframes_result = (
                supabase.table("keyframes")
                .select("id, annotation_count")
                .in_("video_id", video_ids)
                .execute()
            )
            keyframes = keyframes_result.data or []
            total_count += len(keyframes)
            
            # Count labeled keyframes (annotation_count > 0)
            labeled_count += sum(1 for kf in keyframes if (kf.get("annotation_count") or 0) > 0)
    
    return {
        "project_count": project_count,
        "dataset_count": dataset_count,
        "image_count": total_count,
        "labeled_count": labeled_count,
    }


def get_project_annotation_stats(project_id: str) -> dict:
    """
    Get aggregated annotation statistics for all datasets in a project.
    Uses denormalized annotation_count fields for performance.
    
    Args:
        project_id: The project ID to get stats for
    
    Returns:
        dict with:
            - total_images: int
            - labeled_images: int
            - total_videos: int
            - total_keyframes: int
            - labeled_keyframes: int
            - total_annotations: int (sum of all annotation_count fields)
            - class_distribution: dict {class_name: count} (estimated from datasets)
            - dataset_breakdown: list of dicts with per-dataset stats
    """
    supabase = get_supabase()
    
    # Get all datasets for this project
    datasets = get_project_datasets(project_id)
    
    # Get project classes for resolving class_id to class_name (post-migration)
    project = get_project(project_id)
    project_classes = project.get("classes", []) if project else []
    
    if not datasets:
        return {
            "total_images": 0,
            "labeled_images": 0,
            "total_videos": 0,
            "total_keyframes": 0,
            "labeled_keyframes": 0,
            "total_annotations": 0,
            "class_distribution": {},
            "dataset_breakdown": []
        }
    
    # Initialize counters
    total_images = 0
    labeled_images = 0
    total_videos = 0
    total_keyframes = 0
    labeled_keyframes = 0
    total_annotations = 0
    class_distribution = {}
    dataset_breakdown = []
    
    # Process each dataset
    for dataset in datasets:
        dataset_id = dataset["id"]
        dataset_name = dataset["name"]
        dataset_type = dataset["type"]
        # Note: classes are project-level, not dataset-level
        
        # Initialize dataset stats
        ds_total = 0
        ds_labeled = 0
        ds_annotations = 0
        
        if dataset_type == "image":
            # Get image statistics with annotations for on-the-fly class counting
            images_result = (
                supabase.table("images")
                .select("labeled, annotation_count, annotations")
                .eq("dataset_id", dataset_id)
                .execute()
            )
            
            images = images_result.data or []
            ds_total = len(images)
            ds_labeled = sum(1 for img in images if img.get("labeled", False))
            ds_annotations = sum(img.get("annotation_count", 0) for img in images)
            
            total_images += ds_total
            labeled_images += ds_labeled
            total_annotations += ds_annotations
            
            # Count class occurrences on-the-fly from images.annotations
            for img in images:
                annotations = img.get("annotations") or []
                for ann in annotations:
                    # Try class_name first (legacy annotations)
                    class_name = ann.get("class_name")
                    # If no class_name, resolve from class_id using project_classes
                    if not class_name and project_classes:
                        class_id = ann.get("class_id", 0)
                        if 0 <= class_id < len(project_classes):
                            class_name = project_classes[class_id]
                        else:
                            class_name = "Unknown"
                    elif not class_name:
                        class_name = "Unknown"
                    class_distribution[class_name] = class_distribution.get(class_name, 0) + 1
            
        elif dataset_type == "video":
            # Get video count
            videos_result = (
                supabase.table("videos")
                .select("id", count="exact")
                .eq("dataset_id", dataset_id)
                .execute()
            )
            total_videos += videos_result.count or 0
            
            # Get keyframe statistics with annotations for on-the-fly class counting
            # For videos, we need to join keyframes with their videos
            video_ids_result = (
                supabase.table("videos")
                .select("id")
                .eq("dataset_id", dataset_id)
                .execute()
            )
            video_ids = [v["id"] for v in (video_ids_result.data or [])]
            
            if video_ids:
                # Select annotations JSONB to count classes on-the-fly
                keyframes_result = (
                    supabase.table("keyframes")
                    .select("annotation_count, annotations")
                    .in_("video_id", video_ids)
                    .execute()
                )
                
                keyframes = keyframes_result.data or []
                ds_total = len(keyframes)
                ds_labeled = sum(1 for kf in keyframes if (kf.get("annotation_count", 0) > 0))
                ds_annotations = sum(kf.get("annotation_count", 0) for kf in keyframes)
                
                total_keyframes += ds_total
                labeled_keyframes += ds_labeled
                total_annotations += ds_annotations
                
                # Count class occurrences on-the-fly from keyframes.annotations
                for kf in keyframes:
                    annotations = kf.get("annotations") or []
                    for ann in annotations:
                        # Try class_name first (legacy annotations)
                        class_name = ann.get("class_name")
                        # If no class_name, resolve from class_id using project_classes
                        if not class_name and project_classes:
                            class_id = ann.get("class_id", 0)
                            if 0 <= class_id < len(project_classes):
                                class_name = project_classes[class_id]
                            else:
                                class_name = "Unknown"
                        elif not class_name:
                            class_name = "Unknown"
                        class_distribution[class_name] = class_distribution.get(class_name, 0) + 1
        
        # Add to dataset breakdown
        progress_pct = (ds_labeled / ds_total * 100) if ds_total > 0 else 0
        dataset_breakdown.append({
            "dataset_id": dataset_id,
            "dataset_name": dataset_name,
            "type": dataset_type,
            "total_items": ds_total,
            "labeled_items": ds_labeled,
            "annotation_count": ds_annotations,
            "progress_pct": round(progress_pct),
        })
    
    return {
        "total_images": total_images,
        "labeled_images": labeled_images,
        "total_videos": total_videos,
        "total_keyframes": total_keyframes,
        "labeled_keyframes": labeled_keyframes,
        "total_annotations": total_annotations,
        "class_distribution": class_distribution,
        "dataset_breakdown": dataset_breakdown
    }



def get_user_recent_training_runs(user_id: str, limit: int = 5) -> list[dict]:
    """
    Get recent training runs across all projects for a user.
    
    Returns list of dicts with: id, status, project_id, config, metrics, created_at
    """
    supabase = get_supabase()
    
    result = (
        supabase.table("training_runs")
        .select("id, status, project_id, config, metrics, created_at, completed_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# =============================================================================
# INFERENCE RESULTS OPERATIONS (Phase 3.4)
# =============================================================================

def create_inference_result(
    user_id: str,
    model_id: str | None,
    model_name: str,
    input_type: str,
    input_filename: str,
    input_r2_path: str,
    predictions_json: dict,
    confidence_threshold: float,
    labels_r2_path: str | None = None,
    video_start_time: float | None = None,
    video_end_time: float | None = None,
    video_fps: float | None = None,
    video_total_frames: int | None = None,
    inference_duration_ms: int | None = None,
    detection_count: int | None = None,
    batch_images: list[dict] | None = None,  # For batch inference
    inference_settings: dict | None = None,  # Settings used for this run
) -> dict | None:
    """
    Create new inference result record.
    
    Args:
        user_id: UUID of the user
        model_id: UUID of model (None for built-in models like yolo11s.pt)
        model_name: Name of model used (e.g., "yolo11s.pt")
        input_type: "image", "video", or "batch"
        input_filename: Original filename (or count for batch, e.g., "7 images")
        input_r2_path: Path to input file in R2 (first image for batch)
        predictions_json: JSONB predictions data (array of per-image results for batch)
        confidence_threshold: Confidence threshold used
        labels_r2_path: Path to labels file in R2
        video_start_time: Start time for video clips (None for images)
        video_end_time: End time for video clips (None for images)
        video_fps: FPS for videos (None for images)
        video_total_frames: Total frames processed (None for images)
        inference_duration_ms: How long inference took
        detection_count: Total detections across all frames/images
        batch_images: List of image metadata for batch inference
        inference_settings: Settings snapshot (species_conf, sam3_conf, resize_px, sam3_px)
    
    Returns:
        Created inference result record
    """
    supabase = get_supabase()
    data = {
        "user_id": user_id,
        "model_id": model_id,
        "model_name": model_name,
        "input_type": input_type,
        "input_filename": input_filename,
        "input_r2_path": input_r2_path,
        "predictions_json": predictions_json,
        "confidence_threshold": confidence_threshold,
    }
    
    if labels_r2_path is not None:
        data["labels_r2_path"] = labels_r2_path
    if video_start_time is not None:
        data["video_start_time"] = video_start_time
    if video_end_time is not None:
        data["video_end_time"] = video_end_time
    if video_fps is not None:
        data["video_fps"] = video_fps
    if video_total_frames is not None:
        data["video_total_frames"] = video_total_frames
    if inference_duration_ms is not None:
        data["inference_duration_ms"] = inference_duration_ms
    if detection_count is not None:
        data["detection_count"] = detection_count
    if batch_images is not None:
        data["batch_images"] = batch_images
    if inference_settings is not None:
        data["inference_settings"] = inference_settings
    
    result = supabase.table("inference_results").insert(data).execute()
    return result.data[0] if result.data else None


def get_user_inference_results(user_id: str, limit: int = 50) -> list[dict]:
    """Get user's inference results, most recent first."""
    supabase = get_supabase()
    result = (
        supabase.table("inference_results")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_inference_result(result_id: str) -> dict | None:
    """Get single inference result by ID."""
    supabase = get_supabase()
    result = supabase.table("inference_results").select("*").eq("id", result_id).single().execute()
    return result.data if result.data else None


def get_inference_results_by_model(model_id: str) -> list[dict]:
    """Get all inference results for a specific model."""
    supabase = get_supabase()
    result = (
        supabase.table("inference_results")
        .select("*")
        .eq("model_id", model_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_inference_results_by_type(user_id: str, input_type: str) -> list[dict]:
    """
    Get inference results filtered by type (image/video).
    
    Args:
        user_id: User ID
        input_type: "image" or "video"
    """
    supabase = get_supabase()
    result = (
        supabase.table("inference_results")
        .select("*")
        .eq("user_id", user_id)
        .eq("input_type", input_type)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def delete_inference_result(result_id: str) -> dict | None:
    """
    Delete inference result and return it for R2 cleanup.
    
    Returns the deleted record so caller can clean up:
    - input_r2_path (input file)
    - labels_r2_path (labels file)
    """
    supabase = get_supabase()
    
    # First fetch the record to get R2 paths
    result = get_inference_result(result_id)
    if not result:
        return None
    
    # Delete from database
    supabase.table("inference_results").delete().eq("id", result_id).execute()
    
    # Return the record for R2 cleanup
    return result


def get_inference_stats(user_id: str) -> dict:
    """
    Get inference statistics for a user.
    
    Returns:
        dict with: total_results, image_count, video_count, total_detections
    """
    supabase = get_supabase()
    
    # Get all results
    all_results = get_user_inference_results(user_id, limit=1000)
    
    total_results = len(all_results)
    image_count = sum(1 for r in all_results if r["input_type"] == "image")
    video_count = sum(1 for r in all_results if r["input_type"] == "video")
    total_detections = sum(r.get("detection_count", 0) or 0 for r in all_results)
    
    return {
        "total_results": total_results,
        "image_count": image_count,
        "video_count": video_count,
        "total_detections": total_detections,
    }


# =============================================================================
# ENHANCED MODEL MANAGEMENT (Phase 3.4)
# =============================================================================

def get_accessible_project_ids(user_id: str) -> list[str]:
    """Get IDs of all projects the user can access (owned + member + admin-company)."""
    projects = _get_accessible_projects(user_id)
    return [p["id"] for p in projects]


def get_user_models(project_ids: list[str]) -> list[dict]:
    """Get playground models across accessible projects (excludes autolabel models with volume_path)."""
    if not project_ids:
        return []
    supabase = get_supabase()
    result = (
        supabase.table("models")
        .select("*")
        .in_("project_id", project_ids)
        .is_("volume_path", "null")  # Exclude autolabel models (they have volume_path set)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_user_models_by_type(project_ids: list[str], model_type: str) -> list[dict]:
    """Get all saved models across accessible projects filtered by model type.
    
    Args:
        project_ids: List of accessible project UUIDs
        model_type: 'detection' or 'classification'
        
    Returns:
        List of model records matching the specified type
    """
    if not project_ids:
        return []
    supabase = get_supabase()
    result = (
        supabase.table("models")
        .select("*")
        .in_("project_id", project_ids)
        .eq("model_type", model_type)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []

def get_models_grouped_by_project(project_ids: list[str]) -> dict:
    """
    Get models grouped by project name for the inference playground.
    Returns models across all accessible projects (team model sharing).
    
    Returns: {
        "projects": [
            {
                "project_id": "...",
                "project_name": "Project A",
                "models": [
                    {
                        "id": "...",
                        "name": "my_detector",
                        "dataset_name": "Faces",
                        "mAP": 0.85,
                        "created_at": "2025-12-15T..."
                    }
                ]
            }
        ]
    }
    """
    supabase = get_supabase()
    
    # Get all models across accessible projects
    models = get_user_models(project_ids)
    if not models:
        return {"projects": []}
    
    # DEDUPLICATE: Remove duplicate models (same training_run_id + weights_path)
    # Keep only the first occurrence (most recent by created_at desc from get_user_models)
    seen_keys = set()
    unique_models = []
    for model in models:
        key = (model.get("training_run_id"), model.get("weights_path"))
        if key not in seen_keys:
            seen_keys.add(key)
            unique_models.append(model)
    models = unique_models
    
    # Get dataset IDs to fetch dataset info
    dataset_ids = list(set(m["dataset_id"] for m in models if m.get("dataset_id")))
    if not dataset_ids:
        return {"projects": []}
    
    # Get training run IDs to fetch aliases
    training_run_ids = list(set(m["training_run_id"] for m in models if m.get("training_run_id")))
    
    # Fetch training runs to get aliases, model_type, config (for backbone), and metrics
    training_runs_by_id = {}
    if training_run_ids:
        training_runs_result = (
            supabase.table("training_runs")
            .select("id, alias, model_type, config, metrics")
            .in_("id", training_run_ids)
            .execute()
        )
        training_runs_by_id = {tr["id"]: tr for tr in (training_runs_result.data or [])}
    
    # Fetch datasets with project info
    datasets_result = (
        supabase.table("datasets")
        .select("id, name, project_id")
        .in_("id", dataset_ids)
        .execute()
    )
    datasets_by_id = {d["id"]: d for d in (datasets_result.data or [])}
    
    # Get project IDs
    project_ids = list(set(d["project_id"] for d in datasets_by_id.values() if d.get("project_id")))
    if not project_ids:
        return {"projects": []}
    
    # Fetch projects
    projects_result = (
        supabase.table("projects")
        .select("id, name")
        .in_("id", project_ids)
        .execute()
    )
    projects_by_id = {p["id"]: p for p in (projects_result.data or [])}
    
    # Group models by project
    project_models = {}  # project_id -> list of model dicts
    
    for model in models:
        dataset = datasets_by_id.get(model.get("dataset_id"))
        if not dataset:
            continue
        
        project = projects_by_id.get(dataset.get("project_id"))
        if not project:
            continue
        
        project_id = project["id"]
        if project_id not in project_models:
            project_models[project_id] = {
                "project_id": project_id,
                "project_name": project["name"],
                "models": []
            }
        
        # Extract mAP from metrics if available (for detection models)
        metrics = model.get("metrics", {}) or {}
        mAP = metrics.get("mAP50-95") or metrics.get("mAP50") or None
        
        # Get alias, model_type, config, and metrics from training run if available
        training_run = training_runs_by_id.get(model.get("training_run_id"))
        run_alias = training_run.get("alias") if training_run else None
        run_model_type = training_run.get("model_type", "detection") if training_run else "detection"
        run_config = (training_run.get("config") or {}) if training_run else {}
        run_metrics = (training_run.get("metrics") or {}) if training_run else {}
        
        # Extract backbone from training run config (for classification models)
        # Default to "yolo" if not specified
        backbone = run_config.get("classifier_backbone", "yolo") if run_model_type == "classification" else None
        
        # Determine the appropriate metric based on model type
        # Classification: top1_accuracy, Detection: mAP50-95
        if run_model_type == "classification":
            metric_value = run_metrics.get("top1_accuracy")
            metric_type = "acc"  # Will display as "Acc: 0.85"
        else:
            metric_value = mAP
            metric_type = "mAP"  # Will display as "mAP: 0.85"
        
        # Determine weights type from original name (best.pt or last.pt)
        original_name = model["name"]
        weights_type = None
        if "best" in original_name.lower():
            weights_type = "best"
        elif "last" in original_name.lower():
            weights_type = "last"
        
        # Display name: use training run alias if set, otherwise model's own name
        # Add weights_type suffix if alias is used and weights_type is known
        if run_alias:
            if weights_type:
                display_name = f"{run_alias} ({weights_type})"
            else:
                display_name = run_alias
        else:
            display_name = original_name
        
        project_models[project_id]["models"].append({
            "id": model["id"],
            "name": display_name,  # Use alias with weights_type suffix
            "original_name": original_name,  # Keep original for reference
            "training_run_id": model.get("training_run_id"),  # For classifier detection in playground
            "training_run_alias": run_alias,  # For UI to know if alias is used
            "weights_type": weights_type,  # "best", "last", or None for UI badge
            "run_model_type": run_model_type,  # "detection" or "classification" for UI badge
            "backbone": backbone,  # "convnext", "yolo", or None for detection models
            "metric_value": round(metric_value, 3) if metric_value else None,  # Accuracy or mAP value
            "metric_type": metric_type,  # "acc" or "mAP" for display
            "dataset_name": dataset["name"],
            "dataset_id": dataset["id"],
            "mAP": round(mAP, 3) if mAP else None,  # Keep for backward compat
            "created_at": model.get("created_at", ""),
            "is_active": model.get("is_active", False),
        })
    
    # Convert to list and sort by project name
    result = list(project_models.values())
    result.sort(key=lambda x: x["project_name"].lower())
    
    return {"projects": result}


def delete_model(model_id: str) -> dict | None:
    """
    Delete model and return it for R2 cleanup.
    
    Returns the deleted record so caller can clean up weights_path.
    Training run is preserved.
    """
    supabase = get_supabase()
    
    # First fetch the record to get R2 path
    model = get_model(model_id)
    if not model:
        return None
    
    # Delete from database
    supabase.table("models").delete().eq("id", model_id).execute()
    
    # Return the record for R2 cleanup
    return model


def get_models_by_training_run(training_run_id: str) -> list[dict]:
    """Get all models associated with a training run (for cleanup on deletion)."""
    supabase = get_supabase()
    result = (
        supabase.table("models")
        .select("*")
        .eq("training_run_id", training_run_id)
        .execute()
    )
    return result.data or []


def update_model_volume_path(model_id: str, volume_path: str) -> dict | None:
    """Update the Modal volume path for a model after upload."""
    supabase = get_supabase()
    result = (
        supabase.table("models")
        .update({"volume_path": volume_path})
        .eq("id", model_id)
        .execute()
    )
    return result.data[0] if result.data else None


def get_autolabel_models(project_ids: list[str]) -> list[dict]:
    """
    Get models that have volume_path set (available for autolabeling).
    Returns models across all accessible projects (team model sharing).
    
    Returns models with their associated dataset, project info, and training run alias for display.
    """
    if not project_ids:
        return []
    supabase = get_supabase()
    result = (
        supabase.table("models")
        .select("*, datasets!models_dataset_id_fkey(name, project_id, projects(name)), training_runs!models_training_run_id_fkey(alias)")
        .in_("project_id", project_ids)
        .not_.is_("volume_path", "null")
        .order("created_at", desc=True)
        .execute()
    )
    
    # DEDUPLICATE: Remove duplicate models (same training_run_id + weights_path)
    # Keep only the first occurrence (most recent by created_at desc)
    seen_keys = set()
    unique_models = []
    for model in (result.data or []):
        key = (model.get("training_run_id"), model.get("weights_path"))
        if key not in seen_keys:
            seen_keys.add(key)
            unique_models.append(model)
    models = unique_models
    
    # Process results to include training_run_alias at top level for easy access
    for model in models:
        training_run = model.get("training_runs", {}) or {}
        alias = training_run.get("alias")
        original_name = model.get("name", "")
        
        # Determine model type from original name (best.pt or last.pt)
        model_type = None
        if "best" in original_name.lower():
            model_type = "best"
        elif "last" in original_name.lower():
            model_type = "last"
        
        model["model_type"] = model_type  # For UI badge display
        
        if alias:
            # Override model name with alias for display, with model_type suffix
            if model_type:
                model["display_name"] = f"{alias} ({model_type})"
            else:
                model["display_name"] = alias
        else:
            model["display_name"] = original_name
    
    return models


# =============================================================================
# AUTO-LABELING JOB OPERATIONS
# =============================================================================

def create_autolabel_job(
    dataset_id: str,
    user_id: str,
    prompt_type: str,
    prompt_value: str,
    target_count: int,
    class_id: int,
    confidence: float = 0.25,
    model_id: str = None,
    selected_video_ids: list[str] = None
) -> dict | None:
    """
    Create a new auto-labeling job.
    
    Args:
        dataset_id: UUID of the dataset
        user_id: UUID of the user
        prompt_type: Type of prompt ("text", "bbox", "point", "yolo")
        prompt_value: Prompt content (text string or JSON)
        target_count: Number of images/keyframes to process
        class_id: Class ID to assign to detections (only for SAM3 mode)
        confidence: Detection confidence threshold
        model_id: UUID of YOLO model for yolo mode (optional)
        selected_video_ids: List of video IDs for dataset-wide video autolabel (optional)
    
    Returns:
        Created job record
    """
    supabase = get_supabase()
    data = {
        "dataset_id": dataset_id,
        "user_id": user_id,
        "status": "pending",
        "prompt_type": prompt_type,
        "prompt_value": prompt_value,
        "target_count": target_count,
        "class_id": class_id,
        "confidence": confidence,
    }
    if model_id is not None:
        data["model_id"] = model_id
    if selected_video_ids is not None:
        data["selected_video_ids"] = selected_video_ids
    
    result = supabase.table("autolabel_jobs").insert(data).execute()
    return result.data[0] if result.data else None


def get_autolabel_job(job_id: str) -> dict | None:
    """Get auto-label job by ID."""
    supabase = get_supabase()
    result = supabase.table("autolabel_jobs").select("*").eq("id", job_id).single().execute()
    return result.data if result.data else None


def update_autolabel_job(job_id: str, **updates) -> dict | None:
    """Update auto-label job fields."""
    supabase = get_supabase()
    result = supabase.table("autolabel_jobs").update(updates).eq("id", job_id).execute()
    return result.data[0] if result.data else None


def append_autolabel_log(job_id: str, new_logs: str) -> bool:
    """
    Append logs to auto-label job (similar to training logs).
    Uses a fetch-update approach to simulate appending.
    """
    if not new_logs:
        return True
        
    supabase = get_supabase()
    
    try:
        # 1. Fetch current logs
        result = supabase.table("autolabel_jobs").select("logs").eq("id", job_id).single().execute()
        current_logs = result.data.get("logs", "") or ""
        
        # 2. Append and update
        updated_logs = current_logs + new_logs
        result = supabase.table("autolabel_jobs").update({"logs": updated_logs}).eq("id", job_id).execute()
        
        return bool(result.data)
    except Exception as e:
        print(f"[ERROR] Failed to append logs for autolabel job {job_id}: {e}")
        return False


def get_dataset_autolabel_jobs(dataset_id: str) -> list[dict]:
    """Get all auto-label jobs for a dataset, ordered by creation date (newest first)."""
    supabase = get_supabase()
    result = (
        supabase.table("autolabel_jobs")
        .select("*")
        .eq("dataset_id", dataset_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def delete_autolabel_job(job_id: str) -> dict | None:
    """
    Delete an auto-label job by ID and return the deleted job data.
    Returns the deleted job record or None if not found.
    """
    supabase = get_supabase()
    # First get the job data
    job = get_autolabel_job(job_id)
    if not job:
        return None
    
    # Delete the job
    result = supabase.table("autolabel_jobs").delete().eq("id", job_id).execute()
    if result.data:
        return job
    return None


def create_pending_inference_result(
    user_id: str,
    model_id: str | None,
    model_name: str,
    input_type: str,
    input_filename: str,
    input_r2_path: str,
    confidence_threshold: float,
    video_start_time: float | None = None,
    video_end_time: float | None = None,
    inference_settings: dict | None = None,
) -> dict | None:
    """
    Create a pending inference result record for tracking progress.
    """
    supabase = get_supabase()
    data = {
        "user_id": user_id,
        "model_id": model_id,
        "model_name": model_name,
        "input_type": input_type,
        "input_filename": input_filename,
        "input_r2_path": input_r2_path,
        "confidence_threshold": confidence_threshold,
        "inference_status": "processing",
        "progress_current": 0,
        "progress_total": 100,  # Estimated or unknown
        "predictions_json": {}, # Empty for now
    }
    
    if video_start_time is not None:
        data["video_start_time"] = video_start_time
    if video_end_time is not None:
        data["video_end_time"] = video_end_time
    if inference_settings is not None:
        data["inference_settings"] = inference_settings
        
    result = supabase.table("inference_results").insert(data).execute()
    return result.data[0] if result.data else None


def update_inference_progress(
    result_id: str,
    current: int,
    total: int,
    status: str = "processing"
):
    """Update progress of an inference job."""
    supabase = get_supabase()
    supabase.table("inference_results").update({
        "progress_current": current,
        "progress_total": total,
        "progress_status": status,
        "inference_status": status if status in ("processing", "completed", "failed") else "processing",
    }).eq("id", result_id).execute()


def get_inference_progress(result_id: str) -> dict | None:
    """Get current progress of an inference job for polling.
    
    Returns:
        {"inference_status": str, "progress_current": int, "progress_total": int, "progress_status": str}
        or None if not found
    """
    supabase = get_supabase()
    result = (
        supabase.table("inference_results")
        .select("inference_status, progress_current, progress_total, progress_status, predictions_json, labels_r2_path, video_fps, video_total_frames, detection_count")
        .eq("id", result_id)
        .single()
        .execute()
    )
    return result.data if result.data else None


def complete_inference_result(
    result_id: str,
    predictions_json: dict,
    labels_r2_path: str | None = None,
    video_fps: float | None = None,
    video_total_frames: int | None = None,
    inference_duration_ms: int | None = None,
    detection_count: int | None = None,
    error_message: str | None = None,
):
    """Mark multiple inference result as completed (or failed)."""
    supabase = get_supabase()
    
    if error_message:
        data = {
            "inference_status": "failed",
            # "error_message": error_message,  # Assuming this column exists or we add it
        }
    else:
        data = {
            "inference_status": "completed",
            "predictions_json": predictions_json,
            "progress_current": video_total_frames or 100,
            "progress_total": video_total_frames or 100,
        }
        
        if labels_r2_path is not None:
            data["labels_r2_path"] = labels_r2_path
        if video_fps is not None:
            data["video_fps"] = video_fps
        if video_total_frames is not None:
            data["video_total_frames"] = video_total_frames
        if inference_duration_ms is not None:
            data["inference_duration_ms"] = inference_duration_ms
        if detection_count is not None:
            data["detection_count"] = detection_count
            
    supabase.table("inference_results").update(data).eq("id", result_id).execute()


# =============================================================================
# API INFRASTRUCTURE (Phase A1+A2)
# =============================================================================

def promote_model_to_api(
    training_run_id: str,
    slug: str,
    display_name: str,
    description: str = ""
) -> dict | None:
    """
    Promote a completed training run to the API registry.
    
    Creates an api_models record with a snapshot of the model's metadata.
    
    Args:
        training_run_id: UUID of the completed training run
        slug: Unique URL-friendly identifier (e.g., "lynx-detector-v2")
        display_name: Human-readable name for the model
        description: Optional description
        
    Returns:
        Created api_model record, or None on error
        
    Raises:
        ValueError: If training run not found, not completed, or slug already exists
    """
    supabase = get_supabase()
    
    # 1. Fetch training run and validate
    run = get_training_run(training_run_id)
    if not run:
        raise ValueError(f"Training run {training_run_id} not found")
    
    if run.get("status") != "completed":
        raise ValueError(f"Training run must be completed (current: {run.get('status')})")
    
    # 2. Check slug uniqueness
    existing = supabase.table("api_models").select("id").eq("slug", slug).execute()
    if existing.data:
        raise ValueError(f"Slug '{slug}' is already in use")
    
    # 3. Get the best model weights from models table
    models = get_models_by_training_run(training_run_id)
    best_model = next((m for m in models if "best" in m.get("name", "").lower()), None)
    if not best_model:
        # Fallback to first model if no "best" found
        best_model = models[0] if models else None
    
    if not best_model or not best_model.get("weights_path"):
        raise ValueError("No model weights found for this training run")
    
    # 4. Extract classes from run config
    config = run.get("config", {}) or {}
    classes = config.get("classes", [])
    model_type = run.get("model_type", "detection")
    
    # Extract backbone from config (classification uses classifier_backbone, detection defaults to yolo)
    if model_type == "classification":
        backbone = config.get("classifier_backbone", "yolo")
    else:
        backbone = "yolo"  # Detection models always use YOLO backbone
    
    # 5. Determine correct weights path with extension fix for ConvNeXt
    weights_path = best_model["weights_path"]
    
    # ConvNeXt models use .pth extension, YOLO uses .pt
    # If backbone is convnext but path ends with .pt, fix the extension
    if backbone == "convnext" and weights_path.endswith(".pt"):
        weights_path = weights_path[:-3] + ".pth"
    
    # 6. Create api_models record
    data = {
        "training_run_id": training_run_id,
        "project_id": run["project_id"],
        "user_id": run["user_id"],
        "slug": slug,
        "display_name": display_name,
        "description": description or None,
        "model_type": model_type,
        "backbone": backbone,
        "classes_snapshot": classes,
        "weights_r2_path": weights_path,
    }
    
    result = supabase.table("api_models").insert(data).execute()
    return result.data[0] if result.data else None


def get_project_api_models(project_id: str) -> list[dict]:
    """
    Get all API models for a project.
    
    Args:
        project_id: UUID of the project
        
    Returns:
        List of api_model records, newest first
    """
    supabase = get_supabase()
    result = (
        supabase.table("api_models")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_api_model_by_slug(slug: str) -> dict | None:
    """
    Lookup an API model by its unique slug.
    
    Used by the inference endpoint to route requests.
    
    Args:
        slug: Unique slug identifier (e.g., "lynx-detector-v2")
        
    Returns:
        api_model record or None if not found
    """
    supabase = get_supabase()
    result = (
        supabase.table("api_models")
        .select("*")
        .eq("slug", slug)
        .eq("is_active", True)
        .single()
        .execute()
    )
    return result.data if result.data else None


def get_api_model(api_model_id: str) -> dict | None:
    """Get a single API model by ID."""
    supabase = get_supabase()
    result = (
        supabase.table("api_models")
        .select("*")
        .eq("id", api_model_id)
        .single()
        .execute()
    )
    return result.data if result.data else None


def update_api_model(api_model_id: str, **updates) -> dict | None:
    """Update an API model's fields."""
    supabase = get_supabase()
    result = (
        supabase.table("api_models")
        .update(updates)
        .eq("id", api_model_id)
        .execute()
    )
    return result.data[0] if result.data else None


def deactivate_api_model(api_model_id: str) -> bool:
    """
    Soft-delete an API model by setting is_active = False.
    
    Args:
        api_model_id: UUID of the api_model to deactivate
        
    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase()
    result = (
        supabase.table("api_models")
        .update({"is_active": False})
        .eq("id", api_model_id)
        .execute()
    )
    return bool(result.data)


def increment_api_model_usage(api_model_id: str) -> None:
    """
    Increment the total_requests counter and update last_used_at.
    Called after each successful inference request.
    """
    supabase = get_supabase()
    
    # Fetch current count
    model = get_api_model(api_model_id)
    if not model:
        return
    
    current_count = model.get("total_requests", 0) or 0
    
    supabase.table("api_models").update({
        "total_requests": current_count + 1,
        "last_used_at": "now()",
    }).eq("id", api_model_id).execute()


# =============================================================================
# API KEY MANAGEMENT (Phase A2)
# =============================================================================


def _generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    
    Returns:
        Tuple of (raw_key, key_hash, key_prefix)
        - raw_key: Full key to give to user ONCE (e.g., "safari_abc123...")
        - key_hash: SHA256 hash for storage
        - key_prefix: First 12 chars for display (e.g., "safari_abc1...")
    """
    # Generate 32 random bytes = 64 hex chars
    random_part = secrets.token_hex(32)
    raw_key = f"safari_{random_part}"
    
    # Hash for storage
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    # Prefix for display (safari_ + first 4 chars of random part + ...)
    key_prefix = f"safari_{random_part[:4]}..."
    
    return raw_key, key_hash, key_prefix


def create_api_key(
    user_id: str,
    name: str,
    project_id: str | None = None,
    rate_limit_rpm: int = 60,
    monthly_quota: int | None = None,
) -> tuple[str, dict] | None:
    """
    Create a new API key for a user.
    
    IMPORTANT: The raw key is only returned ONCE. Store it securely.
    
    Args:
        user_id: UUID of the user
        name: User-given name for the key (e.g., "Production Key")
        project_id: Optional project scope (None = user-wide)
        rate_limit_rpm: Requests per minute limit
        monthly_quota: Monthly request limit (None = unlimited)
        
    Returns:
        Tuple of (raw_key, key_record) or None on error
    """
    supabase = get_supabase()
    
    raw_key, key_hash, key_prefix = _generate_api_key()
    
    data = {
        "user_id": user_id,
        "project_id": project_id,
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "name": name,
        "rate_limit_rpm": rate_limit_rpm,
        "monthly_quota": monthly_quota,
    }
    
    result = supabase.table("api_keys").insert(data).execute()
    
    if result.data:
        return raw_key, result.data[0]
    return None


def validate_api_key(raw_key: str) -> dict | None:
    """
    Validate an API key and return the key record.
    
    Used by the API middleware to authenticate requests.
    
    Args:
        raw_key: The full API key from Authorization header
        
    Returns:
        api_key record if valid, None otherwise
    """
    supabase = get_supabase()
    
    # Hash the incoming key
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    # Lookup by hash
    result = (
        supabase.table("api_keys")
        .select("*")
        .eq("key_hash", key_hash)
        .eq("is_active", True)
        .execute()
    )
    
    if not result.data:
        return None
    
    key_record = result.data[0]
    
    # Check expiration
    expires_at = key_record.get("expires_at")
    if expires_at:
        from datetime import datetime, timezone
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expiry < datetime.now(timezone.utc):
            return None
    
    # Update last_used_at
    supabase.table("api_keys").update({
        "last_used_at": "now()"
    }).eq("id", key_record["id"]).execute()
    
    return key_record


def revoke_api_key(key_id: str) -> bool:
    """
    Revoke an API key by setting is_active = False.
    
    Args:
        key_id: UUID of the key to revoke
        
    Returns:
        True if successful, False otherwise
    """
    supabase = get_supabase()
    result = (
        supabase.table("api_keys")
        .update({"is_active": False})
        .eq("id", key_id)
        .execute()
    )
    return bool(result.data)


def get_user_api_keys(user_id: str, project_id: str | None = None) -> list[dict]:
    """
    Get all API keys for a user, optionally filtered by project.
    
    Args:
        user_id: UUID of the user
        project_id: Optional project filter
        
    Returns:
        List of api_key records (without key_hash for security)
    """
    supabase = get_supabase()
    
    query = (
        supabase.table("api_keys")
        .select("id, user_id, project_id, key_prefix, name, scopes, "
                "rate_limit_rpm, monthly_quota, requests_this_month, "
                "is_active, last_used_at, expires_at, created_at")
        .eq("user_id", user_id)
    )
    
    if project_id:
        query = query.eq("project_id", project_id)
    
    result = query.order("created_at", desc=True).execute()
    return result.data or []


def delete_api_key(key_id: str) -> bool:
    """
    Permanently delete an API key.
    
    Use revoke_api_key for soft-delete instead.
    """
    supabase = get_supabase()
    result = supabase.table("api_keys").delete().eq("id", key_id).execute()
    return bool(result.data)


# =============================================================================
# API USAGE LOGGING (Phase A3)
# =============================================================================

def log_api_usage(
    api_key_id: str,
    api_model_id: str,
    request_type: str,
    status_code: int,
    file_size_bytes: int | None = None,
    inference_time_ms: int | None = None,
    prediction_count: int | None = None,
    error_message: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> dict | None:
    """
    Log an API request for analytics and billing.
    
    Args:
        api_key_id: UUID of the API key used
        api_model_id: UUID of the model used
        request_type: "image" or "video"
        status_code: HTTP status code of the response
        file_size_bytes: Size of input file
        inference_time_ms: Duration of inference
        prediction_count: Number of predictions returned
        error_message: Error message if request failed
        client_ip: Client IP address
        user_agent: Client user agent
        
    Returns:
        Created log record
    """
    supabase = get_supabase()
    
    data = {
        "api_key_id": api_key_id,
        "api_model_id": api_model_id,
        "request_type": request_type,
        "status_code": status_code,
    }
    
    if file_size_bytes is not None:
        data["file_size_bytes"] = file_size_bytes
    if inference_time_ms is not None:
        data["inference_time_ms"] = inference_time_ms
    if prediction_count is not None:
        data["prediction_count"] = prediction_count
    if error_message is not None:
        data["error_message"] = error_message
    if client_ip is not None:
        data["client_ip"] = client_ip
    if user_agent is not None:
        data["user_agent"] = user_agent
    
    result = supabase.table("api_usage_logs").insert(data).execute()
    return result.data[0] if result.data else None


def get_api_usage_stats(
    user_id: str,
    project_id: str | None = None,
    days: int = 30
) -> dict:
    """
    Get API usage statistics for a user over a time period.
    
    Args:
        user_id: UUID of the user
        project_id: Optional project filter
        days: Number of days to look back
        
    Returns:
        Dict with usage stats: total_requests, successful, failed, by_model, etc.
    """
    supabase = get_supabase()
    
    # Get user's API keys
    keys = get_user_api_keys(user_id, project_id)
    if not keys:
        return {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "by_model": {},
            "by_day": [],
        }
    
    key_ids = [k["id"] for k in keys]
    
    # Query usage logs
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    result = (
        supabase.table("api_usage_logs")
        .select("*")
        .in_("api_key_id", key_ids)
        .gte("created_at", since)
        .order("created_at", desc=True)
        .execute()
    )
    
    logs = result.data or []
    
    # Aggregate stats
    total = len(logs)
    successful = sum(1 for l in logs if 200 <= l.get("status_code", 0) < 300)
    failed = total - successful
    
    # Group by model
    by_model = {}
    for log in logs:
        model_id = log.get("api_model_id")
        if model_id not in by_model:
            by_model[model_id] = 0
        by_model[model_id] += 1
    
    return {
        "total_requests": total,
        "successful_requests": successful,
        "failed_requests": failed,
        "by_model": by_model,
    }


# =============================================================================
# MODEL EVALUATION
# =============================================================================


def create_evaluation_run(
    project_id: str,
    user_id: str,
    model_id: str,
    model_name: str,
    dataset_id: str,
    dataset_name: str,
    classes_snapshot: list[str],
    confidence_threshold: float = 0.25,
    iou_threshold: float = 0.5,
    total_images: int = 0,
) -> dict | None:
    """Create a new evaluation run record."""
    supabase = get_supabase()
    data = {
        "project_id": project_id,
        "user_id": user_id,
        "model_id": model_id,
        "model_name": model_name,
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "classes_snapshot": classes_snapshot,
        "confidence_threshold": confidence_threshold,
        "iou_threshold": iou_threshold,
        "total_images": total_images,
        "status": "pending",
    }
    result = supabase.table("evaluation_runs").insert(data).execute()
    return result.data[0] if result.data else None


def update_evaluation_run(run_id: str, **updates) -> dict | None:
    """Update an evaluation run's fields (status, metrics, progress, etc.)."""
    supabase = get_supabase()
    result = (
        supabase.table("evaluation_runs")
        .update(updates)
        .eq("id", run_id)
        .execute()
    )
    return result.data[0] if result.data else None


def get_evaluation_runs(project_id: str) -> list[dict]:
    """Get all evaluation runs for a project, newest first."""
    supabase = get_supabase()
    result = (
        supabase.table("evaluation_runs")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_evaluation_run(run_id: str) -> dict | None:
    """Get a single evaluation run with all metrics."""
    supabase = get_supabase()
    result = (
        supabase.table("evaluation_runs")
        .select("*")
        .eq("id", run_id)
        .single()
        .execute()
    )
    return result.data if result.data else None


def delete_evaluation_run(run_id: str) -> bool:
    """Delete an evaluation run (cascade deletes predictions)."""
    supabase = get_supabase()
    result = (
        supabase.table("evaluation_runs")
        .delete()
        .eq("id", run_id)
        .execute()
    )
    return bool(result.data)


def create_evaluation_predictions_batch(predictions: list[dict]) -> int:
    """
    Batch insert evaluation prediction records.

    Args:
        predictions: List of dicts with keys:
            evaluation_run_id, image_id, image_filename, image_r2_path,
            ground_truth, predictions, matches, tp_count, fp_count, fn_count

    Returns:
        Number of records inserted.
    """
    if not predictions:
        return 0
    supabase = get_supabase()
    result = supabase.table("evaluation_predictions").insert(predictions).execute()
    return len(result.data) if result.data else 0


def get_evaluation_predictions(
    run_id: str,
    page: int = 0,
    page_size: int = 50,
    match_type: str | None = None,
) -> list[dict]:
    """
    Get paginated evaluation predictions for a run.

    Args:
        run_id: Evaluation run UUID
        page: Page number (0-indexed)
        page_size: Items per page
        match_type: Optional 'fp', 'fn', or 'tp' — filters images with that match type > 0

    Returns:
        List of prediction records
    """
    supabase = get_supabase()
    start = page * page_size
    end = start + page_size - 1

    query = (
        supabase.table("evaluation_predictions")
        .select("*")
        .eq("evaluation_run_id", run_id)
    )

    if match_type == "fp":
        query = query.gt("fp_count", 0)
    elif match_type == "fn":
        query = query.gt("fn_count", 0)
    elif match_type == "tp":
        query = query.gt("tp_count", 0)

    result = (
        query
        .order("fn_count", desc=True)  # Show worst images first
        .range(start, end)
        .execute()
    )
    return result.data or []


def get_evaluation_prediction_detail(prediction_id: str) -> dict | None:
    """Get a single evaluation prediction with full match data."""
    supabase = get_supabase()
    result = (
        supabase.table("evaluation_predictions")
        .select("*")
        .eq("id", prediction_id)
        .single()
        .execute()
    )
    return result.data if result.data else None
