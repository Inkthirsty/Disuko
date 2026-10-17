import torch
import numpy as np
from PIL import Image


def convert_image_to_tensor(img):
    # Preserve alpha if image has it
    if img.mode == "RGBA":
        img_np = np.array(img).astype(np.float32)
        img_np = np.transpose(img_np, axes=[2, 0, 1])[np.newaxis, :, :, :]
        img_pt = torch.from_numpy(img_np)
    else:
        img = img.convert("RGB")
        img_np = np.array(img).astype(np.float32)
        img_np = np.transpose(img_np, axes=[2, 0, 1])[np.newaxis, :, :, :]
        img_pt = torch.from_numpy(img_np)
    return img_pt


def convert_tensor_to_image(img_pt):
    img_pt = img_pt[0, ...].permute(1, 2, 0)
    img_np = img_pt.cpu().numpy()
    
    # Decide mode by channels
    if img_np.shape[2] == 4:
        result = Image.fromarray(img_np.astype(np.uint8), mode="RGBA")
    else:
        result = Image.fromarray(img_np.astype(np.uint8), mode="RGB")
    return result
