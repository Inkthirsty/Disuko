import torch
import torch.nn as nn
import torch.nn.functional as F

class PixelEffectModule(nn.Module):
    def __init__(self):
        super(PixelEffectModule, self).__init__()

    def create_mask_by_idx(self, idx_z, max_z):
        h, w = idx_z.shape
        idx_x = torch.arange(h, device=idx_z.device).view(h, 1).repeat(1, w)
        idx_y = torch.arange(w, device=idx_z.device).view(1, w).repeat(h, 1)
        mask = torch.zeros(h, w, max_z, device=idx_z.device, dtype=torch.float32)
        mask[idx_x, idx_y, idx_z] = 1
        return mask

    def select_by_idx(self, data, idx_z):
        h, w = idx_z.shape
        idx_x = torch.arange(h, device=data.device).view(h, 1).repeat(1, w)
        idx_y = torch.arange(w, device=data.device).view(1, w).repeat(h, 1)
        return data[idx_x, idx_y, idx_z]

    def forward(self, rgb, param_num_bins, param_kernel_size, param_pixel_size):
        print("[DEBUG] Input type:", type(rgb), "dtype:", rgb.dtype)
        print("[DEBUG] Input shape:", rgb.shape)

        if rgb.shape[1] == 4:
            rgb_rgb = rgb[:, :3, :, :]
            alpha = rgb[:, 3:, :, :]
            print("[DEBUG] Alpha detected. Shape:", alpha.shape)
        else:
            rgb_rgb = rgb
            alpha = None
            print("[DEBUG] No alpha channel detected.")

        print("[DEBUG] RGB min/max before processing:", rgb_rgb.min().item(), rgb_rgb.max().item())

        # Premultiply alpha early to avoid dark edges
        if alpha is not None:
            alpha_norm = alpha / 255.0
            rgb_rgb = rgb_rgb * alpha_norm
            print("[DEBUG] RGB after alpha premultiply min/max:", rgb_rgb.min().item(), rgb_rgb.max().item())

        r, g, b = rgb_rgb[:, 0:1, :, :], rgb_rgb[:, 1:2, :, :], rgb_rgb[:, 2:3, :, :]
        print("[DEBUG] R channel min/max before intensity:", r.min().item(), r.max().item())

        # Intensity indexing
        intensity_idx = torch.mean(rgb_rgb, dim=[0, 1]) / 256.0 * param_num_bins
        intensity_idx = intensity_idx.long()
        print("[DEBUG] Intensity idx min/max:", intensity_idx.min().item(), intensity_idx.max().item())

        intensity = self.create_mask_by_idx(intensity_idx, max_z=param_num_bins)
        intensity = intensity.permute(2, 0, 1).unsqueeze(0)
        print("[DEBUG] Intensity shape:", intensity.shape, "min/max:", intensity.min().item(), intensity.max().item())

        r, g, b = r * intensity, g * intensity, b * intensity

        kernel_conv = torch.ones([param_num_bins, 1, param_kernel_size, param_kernel_size], device=rgb.device)
        r = F.conv2d(r, kernel_conv, padding=(param_kernel_size-1)//2, stride=param_pixel_size, groups=param_num_bins)[0]
        g = F.conv2d(g, kernel_conv, padding=(param_kernel_size-1)//2, stride=param_pixel_size, groups=param_num_bins)[0]
        b = F.conv2d(b, kernel_conv, padding=(param_kernel_size-1)//2, stride=param_pixel_size, groups=param_num_bins)[0]
        intensity = F.conv2d(intensity, kernel_conv, padding=(param_kernel_size-1)//2, stride=param_pixel_size, groups=param_num_bins)[0]
        intensity_max, intensity_argmax = torch.max(intensity, dim=0)

        print("[DEBUG] R channel after conv min/max:", r.min().item(), r.max().item())
        print("[DEBUG] Intensity max min/max:", intensity_max.min().item(), intensity_max.max().item())

        r = r.permute(1,2,0)
        g = g.permute(1,2,0)
        b = b.permute(1,2,0)

        r = self.select_by_idx(r, intensity_argmax)
        g = self.select_by_idx(g, intensity_argmax)
        b = self.select_by_idx(b, intensity_argmax)

        intensity_max = intensity_max.clamp(min=1e-6)
        r, g, b = r / intensity_max, g / intensity_max, b / intensity_max

        result_rgb = torch.stack([r, g, b], dim=-1).permute(2,0,1).unsqueeze(0)
        result_rgb = F.interpolate(result_rgb, scale_factor=param_pixel_size)
        print("[DEBUG] result_rgb after interpolate min/max:", result_rgb.min().item(), result_rgb.max().item())

        # Final alpha masking to remove any outline artifacts
        if alpha is not None:
            alpha_up = F.interpolate(alpha, size=result_rgb.shape[2:], mode='nearest')
            mask_up = (alpha_up > 0).float()
            result_rgb[:, :3, :, :] *= mask_up
            result_rgb = torch.cat([result_rgb[:, :3, :, :], alpha_up], dim=1)
            print("[DEBUG] Final result shape:", result_rgb.shape)
            print("[DEBUG] Final RGB min/max:", result_rgb[:, :3, :, :].min().item(), result_rgb[:, :3, :, :].max().item())
            print("[DEBUG] Final Alpha min/max:", result_rgb[:, 3, :, :].min().item(), result_rgb[:, 3, :, :].max().item())

        return result_rgb
