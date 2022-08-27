import logging
import re
from os import PathLike
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Sequence, Tuple, Union
from zipfile import ZipFile

import numpy as np
import pandas as pd
from scipy.ndimage import maximum_filter

from .. import io
from ._preprocessing import SteinbockPreprocessingException

try:
    from readimc import MCDFile, TXTFile
    from readimc.data import Acquisition, AcquisitionBase

    imc_available = True
except:
    imc_available = False


logger = logging.getLogger(__name__)


class SteinbockIMCPreprocessingException(SteinbockPreprocessingException):
    pass


def _extract_zips(
    path: Union[str, PathLike], suffix: str, dest: Union[str, PathLike]
) -> List[Path]:
    extracted_files = []
    for zip_file_path in Path(path).rglob("[!.]*.zip"):
        with ZipFile(zip_file_path) as zip_file:
            zip_infos = sorted(zip_file.infolist(), key=lambda x: x.filename)
            for zip_info in zip_infos:
                if not zip_info.is_dir() and zip_info.filename.endswith(suffix):
                    extracted_file = zip_file.extract(zip_info, path=dest)
                    extracted_files.append(Path(extracted_file))
    return extracted_files


def list_mcd_files(mcd_dir: Union[str, PathLike], unzip_dir: bool = None) -> List[Path]:
    mcd_files = sorted(Path(mcd_dir).rglob("[!.]*.mcd"))
    if unzip_dir is not None:
        mcd_files += _extract_zips(mcd_dir, ".mcd", unzip_dir)
    return mcd_files


def list_txt_files(txt_dir: Union[str, PathLike], unzip_dir: bool = None) -> List[Path]:
    txt_files = sorted(Path(txt_dir).rglob("[!.]*.txt"))
    if unzip_dir is not None:
        txt_files += _extract_zips(txt_dir, ".txt", unzip_dir)
    return txt_files


def create_panel_from_imc_panel(
    imc_panel_file: Union[str, PathLike],
    imc_panel_channel_col: str = "Metal Tag",
    imc_panel_name_col: str = "Target",
    imc_panel_keep_col: str = "full",
    imc_panel_ilastik_col: str = "ilastik",
) -> pd.DataFrame:
    imc_panel = pd.read_csv(
        imc_panel_file,
        sep=",|;",
        dtype={
            imc_panel_channel_col: pd.StringDtype(),
            imc_panel_name_col: pd.StringDtype(),
            imc_panel_keep_col: pd.BooleanDtype(),
            imc_panel_ilastik_col: pd.BooleanDtype(),
        },
        engine="python",
        true_values=["1"],
        false_values=["0"],
    )
    for required_col in (imc_panel_channel_col, imc_panel_name_col):
        if required_col not in imc_panel:
            raise SteinbockIMCPreprocessingException(
                f"Missing '{required_col}' column in IMC panel"
            )
    for notnan_col in (
        imc_panel_channel_col,
        imc_panel_keep_col,
        imc_panel_ilastik_col,
    ):
        if notnan_col in imc_panel and imc_panel[notnan_col].isna().any():
            raise SteinbockIMCPreprocessingException(
                f"Missing values for '{notnan_col}' in IMC panel"
            )
    rename_columns = {
        imc_panel_channel_col: "channel",
        imc_panel_name_col: "name",
        imc_panel_keep_col: "keep",
        imc_panel_ilastik_col: "ilastik",
    }
    drop_columns = [
        panel_col
        for imc_panel_col, panel_col in rename_columns.items()
        if panel_col in imc_panel.columns and panel_col != imc_panel_col
    ]
    panel = imc_panel.drop(columns=drop_columns).rename(columns=rename_columns)
    for _, g in panel.groupby("channel"):
        panel.loc[g.index, "name"] = " / ".join(g["name"].dropna().unique())
        if "keep" in panel:
            panel.loc[g.index, "keep"] = g["keep"].any()
        if "ilastik" in panel:
            panel.loc[g.index, "ilastik"] = g["ilastik"].any()
    panel = panel.groupby(panel["channel"].values).aggregate("first")
    panel = _clean_panel(panel)  # ilastik column may be nullable uint8 now
    ilastik_mask = panel["ilastik"].fillna(False).astype(bool)
    panel["ilastik"] = pd.Series(dtype=pd.UInt8Dtype())
    panel.loc[ilastik_mask, "ilastik"] = range(1, ilastik_mask.sum() + 1)
    return panel


def create_panel_from_mcd_files(
    mcd_files: Sequence[Union[str, PathLike]]
) -> pd.DataFrame:
    panels = []
    for mcd_file in mcd_files:
        with MCDFile(mcd_file) as f:
            for slide in f.slides:
                for acquisition in slide.acquisitions:
                    panel = pd.DataFrame(
                        data={
                            "channel": pd.Series(
                                data=acquisition.channel_names,
                                dtype=pd.StringDtype(),
                            ),
                            "name": pd.Series(
                                data=acquisition.channel_labels,
                                dtype=pd.StringDtype(),
                            ),
                        },
                    )
                    panels.append(panel)
    panel = pd.concat(panels, ignore_index=True, copy=False)
    panel.drop_duplicates(inplace=True, ignore_index=True)
    return _clean_panel(panel)


def create_panel_from_txt_files(
    txt_files: Sequence[Union[str, PathLike]]
) -> pd.DataFrame:
    panels = []
    for txt_file in txt_files:
        with TXTFile(txt_file) as f:
            panel = pd.DataFrame(
                data={
                    "channel": pd.Series(data=f.channel_names, dtype=pd.StringDtype()),
                    "name": pd.Series(data=f.channel_labels, dtype=pd.StringDtype()),
                },
            )
            panels.append(panel)
    panel = pd.concat(panels, ignore_index=True, copy=False)
    panel.drop_duplicates(inplace=True, ignore_index=True)
    return _clean_panel(panel)


def create_image_info(
    mcd_txt_file: Union[str, PathLike],
    acquisition: Optional[Acquisition],
    img: np.ndarray,
    recovery_file: Union[str, PathLike, None],
    recovered: bool,
    img_file: Union[str, PathLike],
) -> Dict[str, Any]:
    recovery_file_name = None
    if recovery_file is not None:
        recovery_file_name = Path(recovery_file).name
    image_info_row = {
        "image": Path(img_file).name,
        "width_px": img.shape[2],
        "height_px": img.shape[1],
        "num_channels": img.shape[0],
        "source_file": Path(mcd_txt_file).name,
        "recovery_file": recovery_file_name,
        "recovered": recovered,
    }
    if acquisition is not None:
        image_info_row.update(
            {
                "acquisition_id": acquisition.id,
                "acquisition_description": acquisition.description,
                "acquisition_start_x_um": (acquisition.roi_points_um[0][0]),
                "acquisition_start_y_um": (acquisition.roi_points_um[0][1]),
                "acquisition_end_x_um": (acquisition.roi_points_um[2][0]),
                "acquisition_end_y_um": (acquisition.roi_points_um[2][1]),
                "acquisition_width_um": acquisition.width_um,
                "acquisition_height_um": acquisition.height_um,
            }
        )
    return image_info_row


def filter_hot_pixels(img: np.ndarray, thres: float) -> np.ndarray:
    kernel = np.ones((1, 3, 3), dtype=bool)
    kernel[0, 1, 1] = False
    max_neighbor_img = maximum_filter(img, footprint=kernel, mode="mirror")
    return np.where(img - max_neighbor_img > thres, max_neighbor_img, img)


def preprocess_image(img: np.ndarray, hpf: Optional[float] = None) -> np.ndarray:
    img = img.astype(np.float32)
    if hpf is not None:
        img = filter_hot_pixels(img, hpf)
    return io._to_dtype(img, io.img_dtype)


def try_preprocess_images_from_disk(
    mcd_files: Sequence[Union[str, PathLike]],
    txt_files: Sequence[Union[str, PathLike]],
    channel_names: Optional[Sequence[str]] = None,
    hpf: Optional[float] = None,
) -> Generator[
    Tuple[Path, Optional["Acquisition"], np.ndarray, Optional[Path], bool],
    None,
    None,
]:
    unmatched_txt_files = list(txt_files)
    # process mcd files in descending order to avoid ambiguous txt file matching
    # see https://github.com/BodenmillerGroup/steinbock/issues/100
    for mcd_file in sorted(
        mcd_files, key=lambda mcd_file: Path(mcd_file).stem, reverse=True
    ):
        try:
            with MCDFile(mcd_file) as f_mcd:
                for slide in f_mcd.slides:
                    for acquisition in slide.acquisitions:
                        matched_txt_file = _match_txt_file(
                            mcd_file, acquisition, unmatched_txt_files
                        )
                        if matched_txt_file is not None:
                            unmatched_txt_files.remove(matched_txt_file)
                        channel_ind = None
                        if channel_names is not None:
                            channel_ind = _get_channel_indices(
                                acquisition, channel_names
                            )
                            if isinstance(channel_ind, str):
                                logger.warning(
                                    f"Channel {channel_ind} not found for "
                                    f"acquisition {acquisition.id} in file "
                                    "{mcd_file}; skipping acquisition"
                                )
                                continue
                        img = None
                        recovered = False
                        try:
                            img = f_mcd.read_acquisition(acquisition)
                        except IOError as e:
                            logger.warning(
                                f"Error reading acquisition {acquisition.id} "
                                f"from file {mcd_file}: {e}"
                            )
                            if matched_txt_file is not None:
                                logger.warning(
                                    f"Restoring from file {matched_txt_file}"
                                )
                                try:
                                    with TXTFile(matched_txt_file) as f_txt:
                                        img = f_txt.read_acquisition()
                                        if channel_names is not None:
                                            channel_ind = _get_channel_indices(
                                                f_txt, channel_names
                                            )
                                            if isinstance(channel_ind, str):
                                                logger.warning(
                                                    f"Channel {channel_ind} "
                                                    "not found in file "
                                                    f"{matched_txt_file}; "
                                                    "skipping acquisition"
                                                )
                                                continue
                                    recovered = True
                                except IOError as e2:
                                    logger.error(
                                        f"Error reading file {matched_txt_file}: {e2}"
                                    )
                        if img is not None:  # exceptions ...
                            if channel_ind is not None:
                                img = img[channel_ind, :, :]
                            img = preprocess_image(img, hpf=hpf)
                            yield (
                                Path(mcd_file),
                                acquisition,
                                img,
                                Path(matched_txt_file)
                                if matched_txt_file is not None
                                else None,
                                recovered,
                            )
                            del img
        except:
            logger.exception(f"Error reading file {mcd_file}")
    while len(unmatched_txt_files) > 0:
        txt_file = unmatched_txt_files.pop(0)
        try:
            channel_ind = None
            with TXTFile(txt_file) as f:
                if channel_names is not None:
                    channel_ind = _get_channel_indices(f, channel_names)
                    if isinstance(channel_ind, str):
                        logger.warning(
                            f"Channel {channel_ind} not found in file "
                            f"{txt_file}; skipping acquisition"
                        )
                        continue
                img = f.read_acquisition()
            if channel_ind is not None:
                img = img[channel_ind, :, :]
            img = preprocess_image(img, hpf=hpf)
            yield Path(txt_file), None, img, None, False
            del img
        except:
            logger.exception(f"Error reading file {txt_file}")


def _clean_panel(panel: pd.DataFrame) -> pd.DataFrame:
    panel.sort_values(
        "channel",
        key=lambda s: pd.to_numeric(s.str.replace("[^0-9]", "", regex=True)),
        inplace=True,
    )
    name_dupl_mask = panel["name"].duplicated(keep=False)
    name_suffixes = panel.groupby("name").cumcount().map(lambda i: f" {i + 1}")
    panel.loc[name_dupl_mask, "name"] += name_suffixes[name_dupl_mask]
    if "keep" not in panel:
        panel["keep"] = pd.Series(dtype=pd.BooleanDtype())
        panel.loc[:, "keep"] = True
    if "ilastik" not in panel:
        panel["ilastik"] = pd.Series(dtype=pd.UInt8Dtype())
        panel.loc[panel["keep"], "ilastik"] = range(1, panel["keep"].sum() + 1)
    if "deepcell" not in panel:
        panel["deepcell"] = pd.Series(dtype=pd.UInt8Dtype())
    next_column_index = 0
    for column in ("channel", "name", "keep", "ilastik", "deepcell"):
        if column in panel:
            column_data = panel[column]
            panel.drop(columns=[column], inplace=True)
            panel.insert(next_column_index, column, column_data)
            next_column_index += 1
    return panel


def _match_txt_file(
    mcd_file: Union[str, PathLike],
    acquisition: Acquisition,
    txt_files: Sequence[Union[str, PathLike]],
) -> Union[str, PathLike, None]:
    txt_file_name_pattern = re.compile(
        rf"{Path(mcd_file).stem}.*_0*{acquisition.id}.txt"
    )
    filtered_txt_files = [
        txt_file
        for txt_file in txt_files
        if txt_file_name_pattern.match(Path(txt_file).name)
    ]
    if len(filtered_txt_files) == 1:
        return filtered_txt_files[0]
    if len(filtered_txt_files) > 1:
        logger.warning(
            "Ambiguous txt file matching for %s: %s; continuing without a match",
            mcd_file,
            ", ".join(filtered_txt_files),
        )
    return None


def _get_channel_indices(
    acquisition: AcquisitionBase, channel_names: Sequence[str]
) -> Union[List[int], str]:
    channel_indices = []
    for channel_name in channel_names:
        if channel_name not in acquisition.channel_names:
            return channel_name
        channel_indices.append(acquisition.channel_names.index(channel_name))
    return channel_indices
