import argparse
import json
import torch
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from functools import partial
from PIL import Image

from model_UI import (
    IMAGE_TOKEN_INDEX, DEFAULT_IMAGE_TOKEN, DEFAULT_IM_START_TOKEN, DEFAULT_IM_END_TOKEN,
    conv_templates, disable_torch_init, load_pretrained_model,
    tokenizer_image_token, process_images, get_model_name_from_path
)

class FerretServerHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            image_path = data.get("image_path")
            prompt_text = data.get("prompt")
            
            if not image_path or not prompt_text:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "Missing image_path or prompt"}')
                return
                
            print(f"\n[Request] Image: {image_path}")
            print(f"[Request] Prompt: {prompt_text}")
            
            # Load and preprocess image
            img = Image.open(image_path).convert('RGB')
            image_size = img.size
            
            # Prepare prompt
            qs = prompt_text
            if "<image>" in qs:
                qs = qs.split('\n')[1]
                
            if self.server.model.config.mm_use_im_start_end:
                qs = DEFAULT_IM_START_TOKEN + DEFAULT_IMAGE_TOKEN + DEFAULT_IM_END_TOKEN + '\n' + qs
            else:
                qs = DEFAULT_IMAGE_TOKEN + '\n' + qs
                
            conv = conv_templates[self.server.conv_mode].copy()
            conv.append_message(conv.roles[0], qs)
            conv.append_message(conv.roles[1], None)
            full_prompt = conv.get_prompt()
            
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            input_ids = tokenizer_image_token(full_prompt, self.server.tokenizer, IMAGE_TOKEN_INDEX, return_tensors='pt').unsqueeze(0).to(device)
            
            # Image tensor preparation
            if self.server.model.config.image_aspect_ratio == "square_nocrop":
                image_tensor = self.server.image_processor.preprocess(img, return_tensors='pt', do_resize=True, 
                                                      do_center_crop=False, size=[self.server.image_h, self.server.image_w])['pixel_values'][0]
            elif self.server.model.config.image_aspect_ratio == "anyres":
                image_process_func = partial(self.server.image_processor.preprocess, return_tensors='pt', do_resize=True, do_center_crop=False, size=[self.server.image_h, self.server.image_w])
                image_tensor = process_images([img], self.server.image_processor, self.server.model.config, image_process_func=image_process_func)[0]
            else:
                image_tensor = process_images([img], self.server.image_processor, self.server.model.config)[0]
                
            images = image_tensor.unsqueeze(0).to(self.server.data_type).to(device)
            
            # Run inference
            with torch.inference_mode():
                self.server.model.orig_forward = self.server.model.forward
                self.server.model.forward = partial(
                    self.server.model.orig_forward,
                    region_masks=None
                )
                output_ids = self.server.model.generate(
                    input_ids,
                    images=images,
                    region_masks=None,
                    image_sizes=[image_size],
                    do_sample=True if self.server.temperature > 0 else False,
                    temperature=self.server.temperature,
                    top_p=self.server.top_p,
                    num_beams=self.server.num_beams,
                    max_new_tokens=self.server.max_new_tokens,
                    use_cache=True)
                self.server.model.forward = self.server.model.orig_forward
                
            outputs = self.server.tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0]
            outputs = outputs.strip()
            
            print(f"[Response] {outputs}")
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            response_data = {"text": outputs}
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            
        except Exception as e:
            print(f"Error processing request: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", type=str, default="jadechoghari/Ferret-UI-Llama8b")
    parser.add_argument("--model_base", type=str, default=None)
    parser.add_argument("--conv_mode", type=str, default="ferret_llama_3")
    parser.add_argument("--image_w", type=int, default=336)
    parser.add_argument("--image_h", type=int, default=336)
    parser.add_argument("--temperature", type=float, default=0.001)
    parser.add_argument("--top_p", type=float, default=None)
    parser.add_argument("--num_beams", type=int, default=1)
    parser.add_argument("--max_new_tokens", type=int, default=1024)
    parser.add_argument("--data_type", type=str, default='fp16', choices=['fp16', 'bf16', 'fp32'])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.data_type == 'fp16':
        data_type = torch.float16
    elif args.data_type == 'bf16':
        data_type = torch.bfloat16
    else:
        data_type = torch.float32

    print(f"Loading model {args.model_path} into memory... This may take a moment.")
    disable_torch_init()
    model_path = os.path.expanduser(args.model_path)
    model_name = get_model_name_from_path(model_path)
    tokenizer, model, image_processor, context_len = \
        load_pretrained_model(model_path, args.model_base, model_name)
    print("Model loaded successfully!")

    # Set up server and attach state
    server_address = ('', args.port)
    httpd = HTTPServer(server_address, FerretServerHandler)
    
    httpd.model = model
    httpd.tokenizer = tokenizer
    httpd.image_processor = image_processor
    httpd.conv_mode = args.conv_mode
    httpd.image_w = args.image_w
    httpd.image_h = args.image_h
    httpd.temperature = args.temperature
    httpd.top_p = args.top_p
    httpd.num_beams = args.num_beams
    httpd.max_new_tokens = args.max_new_tokens
    httpd.data_type = data_type
    
    print(f"Ferret-UI inference server running on port {args.port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()

if __name__ == "__main__":
    main()
