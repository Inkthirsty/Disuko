import torch
import torch.nn as nn

from .module_pixel_effect import PixelEffectModule
from .module_edge_detector import EdgeDetectorModule


class Photo2PixelModel(nn.Module):
    def __init__(self):
        super(Photo2PixelModel, self).__init__()
        self.module_pixel_effect = PixelEffectModule()
        self.module_edge_detect = EdgeDetectorModule()

    def forward(self, rgb,
                param_kernel_size=10,
                param_pixel_size=16,
                param_edge_thresh=112):

        # Ensure RGBA input
        if rgb.shape[1] == 3:
            alpha_channel = torch.ones_like(rgb[:, :1, :, :]) * 255.0
            rgb = torch.cat([rgb, alpha_channel], dim=1)

        rgb = self.module_pixel_effect(rgb,
                                       param_num_bins=4,
                                       param_kernel_size=param_kernel_size,
                                       param_pixel_size=param_pixel_size)

        # Optional edge detection
        # edge_mask = self.module_edge_detect(rgb[:, :3, :, :], param_edge_thresh, param_edge_dilate=3)
        # rgb[:, :3, :, :] = torch.where(edge_mask > 0.5, torch.zeros_like(rgb[:, :3, :, :]), rgb[:, :3, :, :])

        return rgb
