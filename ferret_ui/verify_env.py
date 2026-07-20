import sys
import torch
import transformers

print("=== Ferret-UI Llama 8b Environment Check ===")
print(f"Python version: {sys.version.split()[0]}")
print(f"PyTorch version: {torch.__version__}")
print(f"Transformers version: {transformers.__version__}")

if torch.cuda.is_available():
    print(f"CUDA is available! GPU: {torch.cuda.get_device_name(0)}")
else:
    print("CUDA is NOT available. PyTorch will use CPU.")

try:
    print("\nAttempting to import local inference utilities...")
    from inference import inference_and_run
    print("Successfully imported inference_and_run from inference.py!")
    
    print("\nEnvironment is successfully set up!")
    print("You can run inference using the following template:")
    print("-" * 50)
    print("from inference import inference_and_run\n")
    print("image_path = 'your_image.jpg'")
    print("prompt = 'How do I navigate to the Games tab?'")
    print("model_path = 'jadechoghari/Ferret-UI-Llama8b'")
    print("task_type = 'conversation_interaction'\n")
    print("result = inference_and_run(image_path, prompt, task_type, model_path)")
    print("print(result)")
    print("-" * 50)
except Exception as e:
    print(f"\nWarning: Issue importing local scripts: {e}")
