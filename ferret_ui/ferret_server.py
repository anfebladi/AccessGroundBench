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
from mm_utils import get_anyres_image_grid_shape

# CLIP-ViT-L/14-336 (this model's mm_vision_tower) tokenizes a 336x336 tile
# into a 24x24 patch grid, i.e. 576 tokens per tile.
CLIP_336_PATCH_TOKENS = 576
CLIP_336_PATCH_SIZE = 336


class TokenBudgetExceeded(ValueError):
    pass


def estimate_image_tokens(image_size, model_config):
    """
    Estimate how many tokens the vision tower contributes for one image.

    For 'anyres' (this model's configured image_aspect_ratio), the image is
    split into a base tile plus a grid of sub-tiles chosen by
    get_anyres_image_grid_shape -- the same function process_images() uses to
    actually build the tensor, so this stays in sync with what really gets
    fed to the model. Other aspect-ratio modes fall back to a single tile;
    accurate for 'square_nocrop', an underestimate for any other mode, but no
    other mode is configured for this model.
    """
    aspect_ratio = getattr(model_config, "image_aspect_ratio", None)
    if aspect_ratio == "anyres":
        pinpoints = model_config.image_grid_pinpoints
        grid_w, grid_h = get_anyres_image_grid_shape(
            image_size, pinpoints, CLIP_336_PATCH_SIZE
        )
        tiles = grid_w * grid_h
        return CLIP_336_PATCH_TOKENS * (tiles + 1)
    return CLIP_336_PATCH_TOKENS


def check_token_budget(input_ids, image_size, model_config, max_new_tokens):
    """
    Raise TokenBudgetExceeded if this request would overflow the model's
    context window.

    input_ids contains exactly one IMAGE_TOKEN_INDEX placeholder standing in
    for the whole image (see tokenizer_image_token), so the real image
    expansion is added on top of the text tokens rather than counted twice.

    This exists so a tree too large for the context window fails loudly with
    a clear cause, instead of either being silently truncated (which would
    change the experimental condition being measured) or crashing deep inside
    generate() with an opaque CUDA/index error.
    """
    context_limit = getattr(model_config, "max_position_embeddings", None)
    if context_limit is None:
        return

    text_tokens = input_ids.shape[-1] - 1
    image_tokens = estimate_image_tokens(image_size, model_config)
    total = text_tokens + image_tokens + max_new_tokens

    if total > context_limit:
        raise TokenBudgetExceeded(
            f"Request would use ~{total} tokens (text={text_tokens}, "
            f"image={image_tokens}, max_new_tokens={max_new_tokens}), "
            f"exceeding the model's {context_limit}-token context window. "
            "Reduce max_new_tokens (the generation budget is usually the "
            "cheapest lever) or the size of the injected accessibility tree."
        )


class FerretServer(HTTPServer):
    # Requests are served strictly one at a time: one GPU-resident model, no
    # batching across connections. The stdlib default backlog of 5 means one
    # slow generation (a long target string gets echoed back before the box,
    # taking minutes) fills the queue and the OS starts refusing further
    # connects outright -- which a client reports as "server not running"
    # rather than "server busy". A deep backlog lets callers queue and wait.
    request_queue_size = 128


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

            try:
                check_token_budget(
                    input_ids, image_size, self.server.model.config,
                    self.server.max_new_tokens,
                )
            except TokenBudgetExceeded as e:
                print(f"[ERROR] {e}")
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                return

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
            
            response_data = {"text": outputs, "max_new_tokens": self.server.max_new_tokens}
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            
        except Exception as e:
            print(f"Error processing request: {e}")
            try:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            except Exception as inner_e:
                print(f"Failed to send error response (client may have disconnected): {inner_e}")

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
    httpd = FerretServer(server_address, FerretServerHandler)
    
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
