import shutil

from os import PathLike
from pathlib import Path
from typing import Union

from steinbock import utils

_data_dir = Path(__file__).parent / "data"
_segmentation_pipeline_file_template = _data_dir / "cell_segmentation.cppipe"


def create_and_save_segmentation_pipeline(
    segmentation_pipeline_file: Union[str, PathLike],
):
    shutil.copyfile(
        _segmentation_pipeline_file_template,
        segmentation_pipeline_file,
    )


def run_object_segmentation(
    cellprofiler_binary: Union[str, PathLike],
    segmentation_pipeline_file: Union[str, PathLike],
    probabilities_dir: Union[str, PathLike],
    mask_dir: Union[str, PathLike],
    cellprofiler_plugin_dir: Union[str, PathLike, None] = None,
):
    args = [
        str(cellprofiler_binary),
        "-c",
        "-r",
        "-p",
        str(segmentation_pipeline_file),
        "-i",
        str(probabilities_dir),
        "-o",
        str(mask_dir),
    ]
    if cellprofiler_plugin_dir is not None:
        args.append("--plugins-directory")
        args.append(str(cellprofiler_plugin_dir))
    return utils.run_captured(args)
