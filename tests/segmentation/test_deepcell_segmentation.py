import numpy as np
import pytest

from pathlib import Path

from steinbock import io
from steinbock._env import keras_models_dir
from steinbock.segmentation import deepcell
from steinbock.segmentation.deepcell import Application


class TestDeepcellSegmentation:
    @pytest.mark.skip(reason="test would take too long")
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_try_segment_objects_mesmer(
        self, imc_test_data_steinbock_path: Path
    ):
        from tensorflow.keras.models import load_model

        img_files = io.list_image_files(imc_test_data_steinbock_path / "img")
        model_path = Path(keras_models_dir) / "MultiplexSegmentation"
        model = load_model(model_path, compile=False)
        channel_groups = np.array([np.nan, 2, np.nan, np.nan, 1])
        deepcell.try_segment_objects(
            img_files,
            Application.MESMER,
            model,
            channelwise_minmax=True,
            channel_groups=channel_groups,
        )  # TODO
