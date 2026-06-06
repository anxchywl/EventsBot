import os
import re

directory = "app/web/static"
version_string = "20260607-cal-v4"

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Replace v=... with the new version string
    new_content = re.sub(r'\?v=[a-zA-Z0-9_-]+', f'?v={version_string}', content)
    
    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

for root, _, files in os.walk(directory):
    for file in files:
        if file.endswith('.js') or file.endswith('.html'):
            process_file(os.path.join(root, file))

