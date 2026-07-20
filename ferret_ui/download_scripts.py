import os
from huggingface_hub import hf_hub_download

repo_id = "jadechoghari/Ferret-UI-Llama8b"
files_to_download = [
    "builder.py", "conversation.py", "inference.py", 
    "model_UI.py", "mm_utils.py", "clip_encoder.py", "constants.py"
]
local_dir = "."

for file in files_to_download:
    print(f"Downloading {file}...")
    hf_hub_download(repo_id=repo_id, filename=file, local_dir=local_dir)
print("Done!")
