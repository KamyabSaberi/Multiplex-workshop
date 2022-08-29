# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.14.0
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from matplotlib.colors import ListedColormap
from pathlib import Path
from skimage import color, exposure
from skimage.segmentation import expand_labels

from steinbock import io
from steinbock.segmentation import deepcell

# %% [markdown]
# # Cell segmentation
#
# This notebook is the second in the image preprocessing pipeline and should by run after the `preprocessing` notebook.
#
# Here, we will generate single cell masks with the DeepCell application Mesmer ([Greenwald et al. Nat Biotechnol 40, 555–565 (2022)](https://doi.org/10.1038/s41587-021-01094-0)).
#
# The first step is to generate segmentation stacks where the first channel corresponds to nuclear markers and the second channel corresponds to membrane and cytoplasmic markers. These stacks are then used by Mesmer to predict cell segmentation masks.
#
# Before running your own script please check the [steinbock documentation](https://bodenmillergroup.github.io/steinbock).
#
#
# ## Settings
#
# ### Input and output directories
# Use the same working directory as in the `preprocessing` notebook (by default, the `examples` folder).
#
# Folder structure:

# %% [raw]
# steinbock data/working directory  
# ├── raw   
# |    └──── *.zip (raw data)
# ├── panel.csv (user-provided, when starting from raw data) 
# ├── img (created by this script)  
# ├── segstacks (created by this script)  
# ├── masks (created by this script)  
# ├── intensities (created by this script)  
# ├── regionprops (created by this script)  
# └── neighbors (created by this script)  

# %%
working_dir = Path(".")

# Output directories
img_dir = working_dir / "img"
masks_dir = working_dir / "masks"
segstack_dir = working_dir / "segstacks"

# Create directories (if they do not already exist)
img_dir.mkdir(exist_ok=True)
masks_dir.mkdir(exist_ok=True)
segstack_dir.mkdir(exist_ok=True)

# %% [markdown]
# ### Import the antibody panel

# %%
panel_file = working_dir / "panel.csv"
panel = io.read_panel(panel_file)
panel.head()

# %% [markdown]
# ## Cell segmentation
#
# Documentation: https://bodenmillergroup.github.io/steinbock/latest/cli/segmentation/#deepcell  

# %% [markdown]
# ### Prepare segmentation stacks
#
# Segmentation stacks are generated by aggregating the channels selcted in `panel.csv` in the column `deepcell`. 
# Cell segmentation requires to construct as 2-channel images with the following structure:
# + Channel 1 = nuclear channels
# + Channel 2 = cytoplasmic/membranous channels.
#
# For channel-wise normalization, zscore and min-max methods are available.  
# In addition, different functions can be used to aggregate channels. Default: `np.mean`, for other options, see https://numpy.org/doc/stable/reference/routines.statistics.html#averages-and-variances.

# %%
# Define image preprocessing options
channelwise_minmax = False
channelwise_zscore = True
aggr_func = np.mean

# Define channels to use for segmentation (from the panel file)
channel_groups = panel["deepcell"].values
channel_groups = np.where(channel_groups == 0, np.nan, channel_groups) # make sure unselected chanels are set to nan

# %% [markdown]
# #### Generate segmentation stacks

# %%
for img_path in io.list_image_files(img_dir):
    segstack = deepcell.create_segmentation_stack(
        img = io.read_image(img_path),
        channelwise_minmax = channelwise_minmax,
        channelwise_zscore = channelwise_zscore,
        channel_groups = channel_groups,
        aggr_func = aggr_func
    )
    segstack_file = segstack_dir / f"{img_path.name}"
    io.write_image(segstack, segstack_file)

# %% [markdown]
# #### Check segmentation stacks
# If the images are over-/under-exposed, adjust the `vmax` variable.

# %%
# List segmentation stacks
segstacks = io.list_image_files(segstack_dir)

# Select a random image
rng = np.random.default_rng()
ix = rng.choice(len(segstacks))

# Display nuclear and membrane/cytoplasm images
fig, ax = plt.subplots(1, 2, figsize=(30, 30))

img = io.read_image(segstacks[ix])
ax[0].imshow(img[0,:,:], vmin=0, vmax=5) # adjust vmax if needed (lower value = higher intensity)
ax[0].set_title(segstacks[ix].stem + ": nuclei")

img = io.read_image(segstacks[ix])
ax[1].imshow(img[1,:,:], vmin=0, vmax=5) # adjust vmax if needed (lower value = higher intensity)
ax[1].set_title(segstacks[ix].stem + ": membrane")

# %% [markdown]
# ### Segment cells
#
# `segmentation_type` should be either `whole-cell` or `nuclear`.
#
# The image resolution should also be specified (microns per pixel).
#
# Several post-processing arguments can be passed to the deepcell application. Defaults for nuclear and whole-cell segmentation are indicated in brackets.
# - `maxima_threshold`: set lower if cells are missing (default for nuclear segmentation=0.1, default for nuclear segmentation=0.075).
# - `maxima_smooth`: (default=0).
# - `interior_threshold`: set higher if you your nuclei are too large (default=0.2).
# - `interior_smooth`: larger values give rounder cells (default=2).
# - `small_objects_threshold`: depends on the image resolution (default=50).
# - `fill_holes_threshold`: (default=10).  
# - `radius`: (default=2).
#
# Cell labels can also be expanded by defining an `expansion_distance` (mostly useful for nuclear segmentation).

# %%
# Segmentation type ("nuclear" or "whole-cell")
segmentation_type = "nuclear"

# Image resolution (microns per pixel)
pixel_size_um = 1.0

# Post-processing arguments
postprocess_kwargs =  {
    'maxima_threshold': 0.1,
    'maxima_smooth': 0,
    'interior_threshold': 0.2,
    'interior_smooth': 2,
    'small_objects_threshold': 15,
    'fill_holes_threshold': 15,
    'radius': 2
}

# Mask pixel expansion (0 = no expansion)
expansion_distance = 0

# %%
# Define output directory for masks
masks_subdir = masks_dir / segmentation_type
masks_subdir.mkdir(exist_ok=True, parents=True)

# Segment cells
for img_path, mask in deepcell.try_segment_objects(
    img_files = io.list_image_files(segstack_dir),
    application = deepcell.Application.MESMER,
    pixel_size_um = pixel_size_um,
    segmentation_type = segmentation_type,
    postprocess_kwargs = postprocess_kwargs
):
    mask = expand_labels(mask, distance=float(expansion_distance))
    mask_file = masks_subdir / f"{img_path.stem}.tiff"
    io.write_mask(mask, mask_file)

# %% [markdown]
# #### Check segmentation
#
# Adjust the image intensity by modifiying the `max_intensity` variable and the mask transparency by adusting the `alpha_overlay` variable.  
# For higher magnification images, adjust the coordinates and dimension if needed.

# %%
# Choose either 'nuclear' or 'whole-cell' for downstream processing
segmentation_type = "nuclear"

# Image intensity and mask transarency
max_intensity = 20 # vmax: lower values = higher intensity
alpha_overlay = 0.3

# %%
# List masks
masks_subdir = masks_dir / segmentation_type
masks = io.list_mask_files(masks_subdir)

# Select a random image
ix = rng.choice(len(masks))
fig, ax = plt.subplots(2, 3, figsize=(15, 10))

# Display image, mask, and overlay
img = io.read_image(segstacks[ix])
ax[0,0].imshow(img[0,:,:], vmax=max_intensity)
ax[0,0].set_title(segstacks[ix].stem + ": nuclei")

mask = io.read_image(masks[ix])
cmap = ListedColormap(np.random.rand(10**3,3))
cmap.colors[0]=[1,1,1]
ax[0,1].imshow(mask[0,:,:], cmap=cmap)
ax[0,1].set_title(masks[ix].stem +": mask")

overlay = exposure.adjust_sigmoid(exposure.rescale_intensity(img, (0,1)), 0.1)
overlay = color.label2rgb(mask[0,:,:], overlay[0,:,:], alpha=alpha_overlay, bg_label=0)
ax[0,2].imshow(overlay)
ax[0,2].set_title("overlay")

## Higher magnification (change coordinates and dimensions if needed)
xstart = 100
ystart = 100
dim = 100

ax[1,0].imshow(img[0,:,:], vmin=0, vmax=max_intensity)
ax[1,0].set_xlim([xstart, xstart+dim])
ax[1,0].set_ylim([ystart, ystart+dim])

ax[1,1].imshow(mask[0,:,:], cmap=cmap)
ax[1,1].set_xlim([xstart, xstart+dim])
ax[1,1].set_ylim([ystart, ystart+dim])

ax[1,2].imshow(overlay)
ax[1,2].set_xlim([xstart, xstart+dim])
ax[1,2].set_ylim([ystart, ystart+dim])

# %%
# !conda list
