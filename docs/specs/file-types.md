# File types

## Panel

File extension: `.csv`

User-provided list of channels present in the images (in order)

Comma-separated values (CSV) file with column headers and no index

| Column | Description | Type | Required? |
| --- | --- | --- | --- |
| `name` | Channel name (e.g., antibody target) | Text | yes |
| `ilastik` | Use this channel for pixel classification using Ilastik | Boolean (0/1) | no |

## Images

File extension: `.tiff`

Multi-channel images, where each channel corresponds to a panel entry

Tag Image File Format (TIFF) images of any data type in CYX dimension order

!!! note "Image data type"
    Unless explicitly mentioned, images are converted to 32-bit floating point upon loading (without rescaling).

## Probabilities

File extension: `.tiff`

Color images, with one color per class encoding the probability of pixels belonging to that class

16-bit unsigned integer TIFF images in YXC dimension order, same YX shape as source image

## Cell masks

File extension: `.tiff`

Grayscale image, with one value per cell ("cell ID", 0 for background)

16-bit unsigned integer TIFF images in YX dimension order, same YX shape as source image

## Single-cell data

File extension: `.csv`

Cell measurements of the same type (e.g., mean intensities, morphological features)

CSV file (one per image) with feature/channel name as column and cell IDs as index

!!! note "Combined single-cell data"
    For data containing measurements from multiple images, a combined index of image name and cell ID is used.

## Cell-cell distances

File extension: `.csv`

Cell-cell pixel distances of the same type (e.g., Euclidean centroid distances)

Symmetric CSV file (one per image) with cell IDs as both column and index

## Spatial cell graphs

File extension: `.csv`

List of directed edges defining a spatial cell neighborhood graph

CSV file (one per image) with two columns (`Cell1`, `Cell2`) and no index

Each row defines an edge from cell with ID `Cell1` to cell with ID `Cell2`

!!! note "Undirected graphs"
    For undirected graphs, each edge appears twice (one edge per direction)