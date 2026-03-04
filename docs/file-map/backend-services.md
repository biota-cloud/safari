# Backend Services — Function Reference

> Every important function in the backend service files, grouped by domain.

---

## `supabase_client.py` — Database Operations (3,589 lines, ~154 functions)

The single largest file in the project. All Supabase queries live here.

### Client Initialization
| Function | Description |
|----------|-------------|
| `get_supabase()` | Singleton Supabase client for DATA ops (service role, bypasses RLS) |
| `get_supabase_auth()` | Singleton Supabase client for AUTH ops (anon key, user sessions) |

> [!WARNING]
> **Dual-client split**: Never call `.auth` methods on `get_supabase()` — it would override the service role identity. Use `get_supabase_auth()` for auth operations.

### Profile & Preferences
| Function | Description |
|----------|-------------|
| `get_user_profile(user_id)` | Get user profile by ID |
| `get_user_preferences(user_id)` | Get user preferences dict |
| `update_user_preferences(user_id, section, updates)` | Merge-update a preferences section |
| `get_user_local_machines(user_id)` | Get configured local GPU machines |
| `add_local_machine(user_id, config)` | Add a local GPU machine |
| `remove_local_machine(user_id, name)` | Remove a local GPU machine |
| `test_ssh_connection(host, port, user)` | Test SSH + return GPU info |

### Multi-User / Project Sharing
| Function | Description |
|----------|-------------|
| `get_user_role(user_id)` | Get role ('admin' or 'user'), defaults to 'user' |
| `get_all_users()` | Get all user profiles (admin function) |
| `set_user_role(user_id, role)` | Set a user's role ('admin' or 'user') |
| `promote_to_team_project(project_id)` | Mark project as team-shared |
| `demote_from_team_project(project_id)` | Remove team-shared status |
| `get_project_members(project_id)` | Get all project members with profile info |
| `add_project_member(project_id, user_id, role)` | Add user as project member |
| `remove_project_member(project_id, user_id)` | Remove user from project |
| `_get_accessible_projects(user_id)` | Internal: get all projects user can access (owned + member + admin-company) |

### Project Operations
| Function | Description |
|----------|-------------|
| `get_user_projects(user_id)` | All accessible projects sorted by last accessed |
| `get_user_projects_with_stats(user_id)` | Projects with dataset/class counts (optimized 3-query batch) |
| `create_project(user_id, name, ...)` | Create project container |
| `get_project(project_id)` | Get project by ID |
| `update_project(project_id, **updates)` | Update project fields |
| `delete_project(project_id)` | Delete project (cascades) |
| `touch_project_accessed(project_id)` | Update last_accessed_at timestamp |
| `get_project_processing_target(project_id)` | Get 'cloud' or 'local' |
| `update_project_processing_target(...)` | Change cloud/local target |
| `can_change_processing_target(project_id)` | Check if target can change (no datasets) |
| `get_project_dataset_count(project_id)` | Count datasets in project |

### Dataset Operations
| Function | Description |
|----------|-------------|
| `get_project_datasets(project_id)` | All datasets in project |
| `get_user_datasets(user_id)` | All datasets across all projects |
| `create_dataset(project_id, name, type, ...)` | Create dataset (image or video) |
| `get_dataset(dataset_id)` | Get by ID |
| `update_dataset(dataset_id, **updates)` | Update fields |
| `delete_dataset(dataset_id)` | Delete dataset |
| `touch_dataset_accessed(dataset_id)` | Update last_accessed_at |
| `get_project_datasets_by_tag(project_id, tag)` | Filter by train/validation |

### Image Operations
| Function | Description |
|----------|-------------|
| `create_image(dataset_id, filename, r2_path, ...)` | Create image record |
| `get_dataset_images(dataset_id)` | All images for dataset |
| `get_image(image_id)` | Get by ID |
| `update_image(image_id, **updates)` | Update fields |
| `delete_image(image_id)` | Delete image record |
| `get_dataset_image_count(dataset_id, labeled_only)` | Count images |
| `bulk_create_images(dataset_id, images)` | Bulk insert images |
| `bulk_delete_images(image_ids)` | Bulk delete images |
| `get_image_annotations(image_id)` | Get JSONB annotations |
| `get_dataset_image_annotations(dataset_id)` | Batch load all image annotations |
| `update_image_annotations(image_id, annotations)` | Save JSONB annotations |

### Video Operations
| Function | Description |
|----------|-------------|
| `create_video(dataset_id, filename, ...)` | Create video record |
| `get_dataset_videos(dataset_id)` | All videos for dataset |
| `get_video(video_id)` | Get by ID |
| `update_video(video_id, **updates)` | Update fields |
| `delete_video(video_id)` | Delete video |
| `get_dataset_video_count(dataset_id)` | Count videos |
| `bulk_create_videos(dataset_id, videos)` | Bulk insert videos |
| `bulk_delete_videos(video_ids)` | Bulk delete (+ keyframes) |
| `bulk_create_keyframes(keyframes)` | Bulk insert keyframes |

### Keyframe Operations (Video Labeling)
| Function | Description |
|----------|-------------|
| `create_keyframe(video_id, frame_number, ...)` | Create keyframe record |
| `get_video_keyframes(video_id)` | All keyframes for video |
| `get_keyframe(keyframe_id)` | Get by ID |
| `update_keyframe(keyframe_id, **updates)` | Update fields |
| `delete_keyframe(keyframe_id)` | Delete keyframe |
| `get_video_keyframe_count(video_id)` | Count keyframes |
| `get_dataset_unlabeled_keyframes_count(dataset_id)` | Count unlabeled keyframes |
| `get_unlabeled_keyframes_for_dataset(dataset_id)` | Get all unlabeled keyframes (for autolabel) |
| `delete_video_keyframes(video_id)` | Delete all keyframes for a video |
| `get_keyframe_annotations(keyframe_id)` | Get JSONB annotations |
| `get_video_keyframe_annotations(video_id)` | Batch load all keyframe annotations |
| `get_dataset_class_counts_from_keyframes(dataset_id, ...)` | Class counts from video keyframe annotations |

### Training Run Operations
| Function | Description |
|----------|-------------|
| `create_training_run(project_id, dataset_ids, ...)` | Create training run |
| `get_training_run(run_id)` | Get by ID |
| `get_project_training_runs(project_id)` | All runs for project |
| `get_dataset_training_runs(dataset_id)` | Runs that include a dataset |
| `update_training_run(run_id, **updates)` | Update status/metrics |
| `delete_training_run(run_id)` | Delete run (returns data for R2 cleanup) |
| `get_pending_local_runs(user_id)` | Pending local runs for polling client |
| `claim_training_run(run_id, machine_id)` | Atomically claim a pending run |
| `append_training_log(run_id, new_logs)` | Append logs |

### Model Operations
| Function | Description |
|----------|-------------|
| `create_model(training_run_id, ...)` | Create model record |
| `get_model(model_id)` | Get by ID |
| `get_dataset_models(dataset_id)` | Models for dataset |
| `set_active_model(model_id)` | Set active model (deactivates others) |
| `get_active_model(dataset_id)` | Get active model |
| `delete_model(model_id)` | Delete model (returns for R2 cleanup) |
| `get_models_by_training_run(run_id)` | Models from a training run |
| `update_model_volume_path(model_id, path)` | Set Modal volume path |
| `get_autolabel_models(user_id)` | Models available for autolabeling |
| `get_user_models(user_id)` | All user models |
| `get_user_models_by_type(user_id, type)` | Models filtered by type |
| `get_models_grouped_by_project(user_id)` | Models grouped for playground selector |

### Class Count Computation
| Function | Description |
|----------|-------------|
| `get_image_class_counts_from_annotations(dataset_id)` | Class counts from image annotations |
| `get_combined_class_counts_for_datasets(dataset_ids, ...)` | Combined counts across datasets |
| `rename_class_in_annotations(project_id, old, new, ...)` | Rename/merge class in all annotations |
| `delete_class_from_annotations(project_id, name, idx, ...)` | Delete class from all annotations |

### Dashboard Aggregates
| Function | Description |
|----------|-------------|
| `get_user_stats(user_id)` | Dashboard hub aggregate stats |
| `get_project_annotation_stats(project_id)` | Project-level annotation stats |

### Auto-Labeling Jobs
| Function | Description |
|----------|-------------|
| `create_autolabel_job(dataset_id, ...)` | Create autolabel job |
| `get_autolabel_job(job_id)` | Get by ID |
| `update_autolabel_job(job_id, **updates)` | Update job fields |
| `append_autolabel_log(job_id, logs)` | Append logs |
| `get_dataset_autolabel_jobs(dataset_id)` | All jobs for dataset |
| `delete_autolabel_job(job_id)` | Delete job |

### Inference Results
| Function | Description |
|----------|-------------|
| `create_pending_inference_result(user_id, ...)` | Create pending result for progress tracking |
| `update_inference_progress(result_id, current, total)` | Update progress |
| `get_inference_progress(result_id)` | Poll progress |
| `complete_inference_result(result_id, predictions, ...)` | Mark result complete |

### API Infrastructure (Public REST API)
| Function | Description |
|----------|-------------|
| `promote_model_to_api(run_id, slug, name, ...)` | Promote model to API registry |
| `get_project_api_models(project_id)` | API models for project |
| `get_api_model_by_slug(slug)` | Lookup by slug (for routing) |
| `get_api_model(id)` | Get by ID |
| `update_api_model(id, **updates)` | Update API model |
| `deactivate_api_model(id)` | Soft-delete API model |
| `increment_api_model_usage(id)` | Increment request counter |

### API Key Management
| Function | Description |
|----------|-------------|
| `create_api_key(user_id, name, ...)` | Generate + store API key |
| `validate_api_key(raw_key)` | Validate key from Authorization header |
| `revoke_api_key(key_id)` | Soft-revoke key |
| `get_user_api_keys(user_id, project_id)` | List user's keys |
| `delete_api_key(key_id)` | Hard delete key |

### API Usage Logging
| Function | Description |
|----------|-------------|
| `log_api_usage(api_key_id, ...)` | Log API request for analytics |
| `get_api_usage_stats(user_id, project_id, days)` | Usage statistics |

---

## `annotation_service.py` — Annotation Access Layer (977 lines)

Unified read/write interface for image and keyframe annotations.

### Read Operations
| Function | Description |
|----------|-------------|
| `get_annotations(item_id, item_type, ...)` | Get annotations for one image/keyframe |
| `get_dataset_annotations(dataset_id, type, ...)` | Batch load all annotations for a dataset |
| `get_annotations_for_training(dataset_ids, types)` | Batch load across datasets for training |

### Aggregation
| Function | Description |
|----------|-------------|
| `compute_class_counts(annotations_map, ...)` | Count class occurrences |
| `compute_class_counts_for_datasets(ids, types, ...)` | Combined counts across datasets |

### Resolution & Validation
| Function | Description |
|----------|-------------|
| `resolve_class_names(annotations, classes)` | Resolve class_id → class_name |
| `strip_class_names(annotations)` | Remove class_name before storage |
| `validate_annotation_coordinates(annotation)` | Validate normalized 0-1 format |
| `validate_annotations_batch(annotations)` | Validate batch |

### Write Operations
| Function | Description |
|----------|-------------|
| `save_annotations(item_id, type, ...)` | Dual-write to Supabase + R2 |

### Class Management
| Function | Description |
|----------|-------------|
| `rename_class_in_project(project_id, old, new, ...)` | Rename/merge class across project |
| `delete_class_from_project(project_id, name, idx, ...)` | Delete class across project |

---

## `r2_storage.py` — Cloudflare R2 Client (216 lines)

| Method | Description |
|--------|-------------|
| `R2Client.upload_file(bytes, path, content_type)` | Upload file to R2 |
| `R2Client.download_file(path)` | Download file from R2 |
| `R2Client.list_files(prefix)` | List files by prefix |
| `R2Client.generate_presigned_url(path, expires)` | Generate temporary access URL |
| `R2Client.delete_file(path)` | Delete single file |
| `R2Client.file_exists(path)` | Check if file exists |
| `R2Client.delete_files_with_prefix(prefix)` | Delete all files under prefix |
| `R2Client.copy_files_with_prefix(src, dest, callback)` | Server-side copy |

---

## `model_registry.py` — Model Type Registry (213 lines)

| Item | Description |
|------|-------------|
| `ModelType` enum | `YOLO_DETECT`, `YOLO_CLASSIFY`, `CONVNEXT_CLASSIFY`, `SAM3_IMAGE`, `SAM3_VIDEO` |
| `ModelInfo` dataclass | Metadata: type, extension (.pt/.pth), package, loader name |
| `get_model_info(type)` | Look up model metadata |
| `detect_classifier_backbone(path)` | Auto-detect YOLO vs ConvNeXt from extension |
| `get_all_model_types()` | List all registered model type strings |
| `load_model(type, path, **kwargs)` | Load model with appropriate loader |

---

## `ssh_client.py` — SSH Remote Worker Client (671 lines)

`SSHWorkerClient` — context manager for remote GPU machines.

| Method | Description |
|--------|-------------|
| `connect()` | Establish SSH connection (key-based auth) |
| `close()` | Close connection |
| `sync_scripts(force)` | Upload worker scripts to remote `~/.safari/scripts/` |
| `sync_core_modules(force)` | Upload `backend/core/` to remote `~/.safari/backend/core/` |
| `sync_env(env_vars)` | Update remote `.env` with credentials |
| `execute_job(script, params, timeout)` | Run worker script synchronously |
| `execute_async(script, params)` | Run in background, return job ref |
| `check_async_job(job_ref)` | Poll job status + progress |
| `check_connection()` | Test connection + GPU info |

---

## `inference_router.py` — Unified Inference Entry Point (288 lines)

| Item | Description |
|------|-------------|
| `InferenceConfig` dataclass | Model type, input type, model ID, project ID, compute target |
| `dispatch_inference(config, **params)` | **Main entry point** — routes to correct executor |
| `_dispatch_yolo_image/batch/video(...)` | YOLO detection dispatch |
| `_dispatch_hybrid_image/batch/video(...)` | Hybrid SAM3+classifier dispatch |

---

## `job_router.py` — Job Dispatch to Modal or SSH (595 lines)

| Function | Description |
|----------|-------------|
| `get_job_target(project_id)` | Resolve 'cloud' or 'local' for project |
| `get_ssh_client_for_project(project_id)` | Get configured SSH client |
| `dispatch_training_job(...)` | Route detection training to Modal or SSH |
| `dispatch_classification_training_job(...)` | Route classification training to Modal or SSH |
| `dispatch_autolabel_job(...)` | Route autolabeling to Modal or SSH |
| `dispatch_hybrid_inference(...)` | Route single image hybrid inference |
| `dispatch_hybrid_inference_batch(...)` | Route batch hybrid inference |
| `dispatch_hybrid_inference_video(...)` | Route video hybrid inference |

---

## Other Backend Files

| File | Description |
|------|-------------|
| `frame_extractor.py` | `extract_and_store_full_frame()` — FFmpeg frame extraction from R2 videos |
| `zip_processor.py` | `extract_and_parse_zip()` — YOLO dataset import from ZIP files |
| `supabase_auth.py` | Auth retry decorator for expired JWT tokens |
