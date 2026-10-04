import json
import os

# Define paths
main_json_path = os.path.join("tailored_applications", "processed_jobs.json")
old_root_path = "processed_jobs.json"
admin_json_path = os.path.join("tailored_applications_admin", "processed_jobs.json")

def clean_text(text):
    return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()

def get_job_signature(title, employer):
    return f"{clean_text(title)}_{clean_text(employer)}"

all_records = {}

# 1. Load from the main centralized sink first
if os.path.exists(main_json_path):
    try:
        with open(main_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "title" in item and "company" in item:
                        sig = get_job_signature(item["title"], item["company"])
                        all_records[sig] = item
            elif isinstance(data, dict):
                for sig, item in data.items():
                    all_records[sig] = item
        print(f"Loaded {len(all_records)} records from main centralized sink.")
    except Exception as e:
        print(f"Error loading main JSON: {e}")

# Helper function to merge an external file source (using os.path.abspath correctly)
def merge_source_file(path_to_merge, label):
    if os.path.exists(path_to_merge) and os.path.abspath(path_to_merge) != os.path.abspath(main_json_path):
        try:
            with open(path_to_merge, "r", encoding="utf-8") as f:
                content = json.load(f)
                added_count = 0
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and "title" in item and "company" in item:
                            sig = get_job_signature(item["title"], item["company"])
                            if sig not in all_records:
                                all_records[sig] = item
                                added_count += 1
                elif isinstance(content, dict):
                    for sig, item in content.items():
                        if sig not in all_records:
                            all_records[sig] = item
                            added_count += 1
            print(f"Merged {added_count} unique records from {label} ({path_to_merge}).")
        except Exception as e:
            print(f"Error loading {label} JSON: {e}")

# 2. Merge from root-level file if it exists
merge_source_file(old_root_path, "Root-level file")

# 3. Merge from the old admin folder file if it exists
merge_source_file(admin_json_path, "Admin folder file")

# 4. Save the unified clean list back to tailored_applications/processed_jobs.json
os.makedirs("tailored_applications", exist_ok=True)
final_list = list(all_records.values())
with open(main_json_path, "w", encoding="utf-8") as f:
    json.dump(final_list, f, indent=4)

print(f"\nSuccessfully unified {len(final_list)} total unique applications into {main_json_path}!")