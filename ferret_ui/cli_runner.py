import argparse
import sys
import warnings

# Suppress warnings to keep stdout clean
warnings.filterwarnings("ignore")

from inference import inference_and_run

def main():
    parser = argparse.ArgumentParser(description="Run Ferret-UI Llama 8b inference")
    parser.add_argument("--image", required=True, help="Path to the image")
    parser.add_argument("--prompt", required=True, help="Prompt text")
    parser.add_argument("--model", default="jadechoghari/Ferret-UI-Llama8b", help="Model path")
    parser.add_argument("--task", default="conversation_interaction", help="Task type")
    
    args = parser.parse_args()
    
    try:
        # We redirect stdout so that intermediate prints from the model scripts don't pollute the final output
        # Wait, the inference script might print things out. We need to capture the exact result.
        # Actually, let's just print a special delimiter or just print the result at the end.
        result = inference_and_run(
            image_path=args.image,
            prompt=args.prompt,
            conv_mode="ferret_llama_3",
            model_path=args.model
        )
        
        if isinstance(result, list) and len(result) > 0:
            result_str = result[0]
        else:
            result_str = str(result)
        
        # We will use a delimiter so the caller can easily extract the final answer
        print(f"\n---FERRET_OUTPUT_START---\n{result_str}\n---FERRET_OUTPUT_END---")
    except Exception as e:
        print(f"\n---FERRET_OUTPUT_START---\nError: {e}\n---FERRET_OUTPUT_END---")
        sys.exit(1)

if __name__ == "__main__":
    main()
