"""
Debug Modal job to inspect environment and test Supabase connectivity.
Deploy: modal run debug_modal.py
"""
import modal
import os

app = modal.App("debug-env-check")

@app.function(
    image=modal.Image.debian_slim().pip_install("supabase"),
    secrets=[modal.Secret.from_name("supabase-credentials")],
    timeout=60,
)
def check_env():
    """Print masked env vars and test Supabase connection."""
    
    # 1. Show env vars (masked)
    print("=== Environment Variables ===")
    for key in ["SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_ROLE"]:
        val = os.environ.get(key, "(NOT SET)")
        if val and len(val) > 10:
            masked = val[:15] + "..." + val[-6:]
        else:
            masked = val
        print(f"  {key}: {masked}")
    
    # 2. Test Supabase connection
    from supabase import create_client
    
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    
    print(f"\n=== Testing Supabase Connection ===")
    print(f"  URL: {supabase_url}")
    
    try:
        sb = create_client(supabase_url, supabase_key)
        
        # Try to count autolabel jobs
        jobs = sb.table("autolabel_jobs").select("id,status").execute()
        print(f"  autolabel_jobs visible: {len(jobs.data)}")
        for j in jobs.data:
            print(f"    {j['id'][:12]}... status={j['status']}")
        
        # Try images
        imgs = sb.table("images").select("id").limit(3).execute()
        print(f"  images visible: {len(imgs.data)}")
        
        # Try keyframes
        kfs = sb.table("keyframes").select("id").execute()
        print(f"  keyframes visible: {len(kfs.data)}")
        
        # Test .single() query (reproducing LogCapture's exact query)
        test_job_id = jobs.data[0]["id"] if jobs.data else None
        if test_job_id:
            print(f"\n=== Testing .single() for job {test_job_id[:12]}... ===")
            try:
                res = sb.table("autolabel_jobs").select("logs").eq("id", test_job_id).single().execute()
                print(f"  .single() OK: logs={len(res.data.get('logs','') or '')} chars")
            except Exception as e:
                print(f"  .single() FAILED: {e}")
            
            # Test update
            try:
                res = sb.table("autolabel_jobs").update({"status": "running"}).eq("id", test_job_id).execute()
                print(f"  update result: {len(res.data)} rows returned")
                # Revert
                sb.table("autolabel_jobs").update({"status": "pending"}).eq("id", test_job_id).execute()
            except Exception as e:
                print(f"  update FAILED: {e}")
        
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("\n=== Done ===")
    return "OK"
