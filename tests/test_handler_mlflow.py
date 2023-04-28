# Copyright (c) MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import glob
import os
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import numpy as np
from ignite.engine import Engine, Events
from parameterized import parameterized

from monai.handlers import MLFlowHandler
from monai.utils import path_to_uri


def get_event_filter(e):
    def event_filter(_, event):
        if event in e:
            return True
        return False

    return event_filter


def dummy_train(tracking_folder):
    tempdir = tempfile.mkdtemp()

    # set up engine
    def _train_func(engine, batch):
        return [batch + 1.0]

    engine = Engine(_train_func)

    # set up testing handler
    test_path = os.path.join(tempdir, tracking_folder)
    handler = MLFlowHandler(
        iteration_log=False,
        epoch_log=True,
        tracking_uri=path_to_uri(test_path),
        state_attributes=["test"],
        close_on_complete=True,
    )
    handler.attach(engine)
    engine.run(range(3), max_epochs=2)
    return test_path


class TestHandlerMLFlow(unittest.TestCase):
    def setUp(self):
        self.tmpdir_list = []

    def tearDown(self):
        for tmpdir in self.tmpdir_list:
            if tmpdir and os.path.exists(tmpdir):
                shutil.rmtree(tmpdir)

    def test_multi_run(self):
        with tempfile.TemporaryDirectory() as tempdir:
            # set up the train function for engine
            def _train_func(engine, batch):
                return [batch + 1.0]

            create_engine_times = 3
            for _ in range(create_engine_times):
                engine = Engine(_train_func)

                @engine.on(Events.EPOCH_COMPLETED)
                def _update_metric(engine):
                    current_metric = engine.state.metrics.get("acc", 0.1)
                    engine.state.metrics["acc"] = current_metric + 0.1
                    engine.state.test = current_metric

                # set up testing handler
                test_path = os.path.join(tempdir, "mlflow_test")
                handler = MLFlowHandler(
                    iteration_log=False,
                    epoch_log=True,
                    tracking_uri=path_to_uri(test_path),
                    state_attributes=["test"],
                    close_on_complete=True,
                )
                handler.attach(engine)
                engine.run(range(3), max_epochs=2)
                run_cnt = len(handler.client.search_runs(handler.experiment.experiment_id))
                handler.close()
            # the run count should equal to the times of creating engine
            self.assertEqual(create_engine_times, run_cnt)

    def test_metrics_track(self):
        experiment_param = {"backbone": "efficientnet_b0"}
        with tempfile.TemporaryDirectory() as tempdir:
            # set up engine
            def _train_func(engine, batch):
                return [batch + 1.0]

            engine = Engine(_train_func)

            # set up dummy metric
            @engine.on(Events.EPOCH_COMPLETED)
            def _update_metric(engine):
                current_metric = engine.state.metrics.get("acc", 0.1)
                engine.state.metrics["acc"] = current_metric + 0.1
                engine.state.test = current_metric

            # set up testing handler
            test_path = os.path.join(tempdir, "mlflow_test")
            artifact_path = os.path.join(tempdir, "artifacts")
            os.makedirs(artifact_path, exist_ok=True)
            dummy_numpy = np.zeros((64, 64, 3))
            dummy_path = os.path.join(artifact_path, "tmp.npy")
            np.save(dummy_path, dummy_numpy)
            handler = MLFlowHandler(
                iteration_log=False,
                epoch_log=True,
                tracking_uri=path_to_uri(test_path),
                state_attributes=["test"],
                experiment_param=experiment_param,
                artifacts=[artifact_path],
                close_on_complete=True,
            )
            handler.attach(engine)
            engine.run(range(3), max_epochs=2)
            handler.close()
            # check logging output
            self.assertTrue(len(glob.glob(test_path)) > 0)

    @parameterized.expand([[True], [get_event_filter([1, 2])]])
    def test_metrics_track_mock(self, epoch_log):
        experiment_param = {"backbone": "efficientnet_b0"}
        with tempfile.TemporaryDirectory() as tempdir:
            # set up engine
            def _train_func(engine, batch):
                return [batch + 1.0]

            engine = Engine(_train_func)

            # set up dummy metric
            @engine.on(Events.EPOCH_COMPLETED)
            def _update_metric(engine):
                current_metric = engine.state.metrics.get("acc", 0.1)
                engine.state.metrics["acc"] = current_metric + 0.1
                engine.state.test = current_metric

            # set up testing handler
            test_path = os.path.join(tempdir, "mlflow_test")
            handler = MLFlowHandler(
                iteration_log=False,
                epoch_log=epoch_log,
                tracking_uri=path_to_uri(test_path),
                state_attributes=["test"],
                experiment_param=experiment_param,
                close_on_complete=True,
            )
            handler._default_epoch_log = MagicMock()
            handler.attach(engine)

            max_epochs = 4
            engine.run(range(3), max_epochs=max_epochs)
            handler.close()
            # check logging output
            if epoch_log is True:
                self.assertEqual(handler._default_epoch_log.call_count, max_epochs)
            else:
                self.assertEqual(handler._default_epoch_log.call_count, 2)  # 2 = len([1, 2]) from event_filter

    @parameterized.expand([[True], [get_event_filter([1, 3])]])
    def test_metrics_track_iters_mock(self, iteration_log):
        experiment_param = {"backbone": "efficientnet_b0"}
        with tempfile.TemporaryDirectory() as tempdir:
            # set up engine
            def _train_func(engine, batch):
                return [batch + 1.0]

            engine = Engine(_train_func)

            # set up dummy metric
            @engine.on(Events.EPOCH_COMPLETED)
            def _update_metric(engine):
                current_metric = engine.state.metrics.get("acc", 0.1)
                engine.state.metrics["acc"] = current_metric + 0.1
                engine.state.test = current_metric

            # set up testing handler
            test_path = os.path.join(tempdir, "mlflow_test")
            handler = MLFlowHandler(
                iteration_log=iteration_log,
                epoch_log=False,
                tracking_uri=path_to_uri(test_path),
                state_attributes=["test"],
                experiment_param=experiment_param,
                close_on_complete=True,
            )
            handler._default_iteration_log = MagicMock()
            handler.attach(engine)

            num_iters = 3
            max_epochs = 2
            engine.run(range(num_iters), max_epochs=max_epochs)
            handler.close()
            # check logging output
            if iteration_log is True:
                self.assertEqual(handler._default_iteration_log.call_count, num_iters * max_epochs)
            else:
                self.assertEqual(handler._default_iteration_log.call_count, 2)  # 2 = len([1, 3]) from event_filter

    def test_multi_thread(self):
        test_uri_list = ["monai_mlflow_test1", "monai_mlflow_test2"]
        with ThreadPoolExecutor(2, "Training") as executor:
            futures = {}
            for t in test_uri_list:
                futures[t] = executor.submit(dummy_train, t)

            for _, future in futures.items():
                res = future.result()
                self.tmpdir_list.append(res)
                self.assertTrue(len(glob.glob(res)) > 0)


if __name__ == "__main__":
    unittest.main()
