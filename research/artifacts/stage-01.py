import os
import re

JS_DIR = "./static_js"

doc_id_pattern = re.compile(r'e\.exports\s*=\s*["\'](\d{8,})["\']')
variables_pattern = re.compile(r'variables\s*=\s*{(.*?)}', re.DOTALL)

results = []

def extract_variables_nearby(lines, index):
  
    search_range = lines[max(0, index-20): index+20]
    combined = "\n".join(search_range)
    
    match = variables_pattern.search(combined)
    if match:
        raw_vars = match.group(1)
        keys = re.findall(r'["\']?([\w_]+)["\']?\s*:', raw_vars)
        return list(set(keys))
    return []

def analyze_file(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        doc_id_match = doc_id_pattern.search(line)
        if doc_id_match:
            doc_id = doc_id_match.group(1)
            vars_found = extract_variables_nearby(lines, i)
            results.append({
                "file": path,
                "doc_id": doc_id,
                "variables": vars_found
            })

def scan_directory(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".js"):
                analyze_file(os.path.join(root, file))

if __name__ == "__main__":
    scan_directory(JS_DIR)
    for entry in results:
        print(f"\nFile: {entry['file']}")
        print(f"doc_id: {entry['doc_id']}")
        print(f"variables: {entry['variables'] if entry['variables'] else 'No variables found'}")
