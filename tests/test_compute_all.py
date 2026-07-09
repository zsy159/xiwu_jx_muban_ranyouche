from __future__ import annotations

import argparse
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from salary_pipeline.main import PAYOUT_CHANNELS, cmd_compute_all


class ComputeAllTests(unittest.TestCase):
    def _args(self, *, reconcile: bool = False) -> argparse.Namespace:
        return argparse.Namespace(
            month="2026-05",
            reconcile=reconcile,
            golden=None,
            sheet=None,
            report_dir=None,
            verbose=False,
        )

    @patch("salary_pipeline.main.cmd_reconcile_payout", return_value=0)
    @patch("salary_pipeline.main.cmd_reconcile", return_value=0)
    @patch("salary_pipeline.main.ChannelPayoutPipeline")
    @patch("salary_pipeline.main.SalesPipeline")
    def test_runs_hub_and_all_payout_channels(
        self,
        mock_sales: MagicMock,
        mock_channel_pipeline: MagicMock,
        mock_reconcile: MagicMock,
        mock_reconcile_payout: MagicMock,
    ) -> None:
        hub_path = Path("/tmp/hub.xlsx")
        mock_sales.return_value.run.return_value = {
            "output_path": hub_path,
            "summary": pd.DataFrame({"姓名": ["a"]}),
        }

        def make_payout_result(channel: str) -> dict:
            return {
                "channel": channel,
                "output_path": Path(f"/tmp/{channel}.xlsx"),
                "summary": pd.DataFrame({"姓名": ["a"]}),
                "warnings": [],
            }

        pipelines: list[MagicMock] = []

        def make_pipeline(channel: str, config_dir: object, **kwargs: object) -> MagicMock:
            pipeline = MagicMock()
            pipeline.run.return_value = make_payout_result(channel)
            pipelines.append(pipeline)
            return pipeline

        mock_channel_pipeline.side_effect = make_pipeline

        rc = cmd_compute_all(self._args(reconcile=False))

        self.assertEqual(rc, 0)
        mock_sales.return_value.run.assert_called_once()
        self.assertEqual(mock_channel_pipeline.call_count, len(PAYOUT_CHANNELS))
        called_channels = [
            call.args[0] for call in mock_channel_pipeline.call_args_list
        ]
        self.assertEqual(called_channels, list(PAYOUT_CHANNELS))
        for pipeline in pipelines:
            pipeline.run.assert_called_once_with(
                context={"hub_path": hub_path, "use_computed_hub": True},
            )
        mock_reconcile.assert_not_called()
        mock_reconcile_payout.assert_not_called()

    @patch("salary_pipeline.main.cmd_reconcile_payout")
    @patch("salary_pipeline.main.cmd_reconcile", return_value=0)
    @patch("salary_pipeline.main.ChannelPayoutPipeline")
    @patch("salary_pipeline.main.SalesPipeline")
    def test_reconcile_all_stages(
        self,
        mock_sales: MagicMock,
        mock_channel_pipeline: MagicMock,
        mock_reconcile: MagicMock,
        mock_reconcile_payout: MagicMock,
    ) -> None:
        hub_path = Path("/tmp/hub.xlsx")
        mock_sales.return_value.run.return_value = {
            "output_path": hub_path,
            "summary": pd.DataFrame(),
        }

        payout_paths = {
            channel: Path(f"/tmp/{channel}.xlsx") for channel in PAYOUT_CHANNELS
        }

        def make_pipeline(channel: str, config_dir: object, **kwargs: object) -> MagicMock:
            pipeline = MagicMock()
            pipeline.run.return_value = {
                "channel": channel,
                "output_path": payout_paths[channel],
                "summary": pd.DataFrame(),
                "warnings": [],
            }
            return pipeline

        mock_channel_pipeline.side_effect = make_pipeline
        mock_reconcile_payout.return_value = 0

        rc = cmd_compute_all(self._args(reconcile=True))

        self.assertEqual(rc, 0)
        mock_reconcile.assert_called_once()
        self.assertEqual(mock_reconcile_payout.call_count, len(PAYOUT_CHANNELS))
        reconciled_channels = [
            call.args[0].channel for call in mock_reconcile_payout.call_args_list
        ]
        self.assertEqual(reconciled_channels, list(PAYOUT_CHANNELS))

    @patch("salary_pipeline.main.cmd_reconcile_payout", return_value=2)
    @patch("salary_pipeline.main.cmd_reconcile", return_value=0)
    @patch("salary_pipeline.main.ChannelPayoutPipeline")
    @patch("salary_pipeline.main.SalesPipeline")
    def test_reconcile_failure_returns_nonzero(
        self,
        mock_sales: MagicMock,
        mock_channel_pipeline: MagicMock,
        mock_reconcile: MagicMock,
        mock_reconcile_payout: MagicMock,
    ) -> None:
        mock_sales.return_value.run.return_value = {
            "output_path": Path("/tmp/hub.xlsx"),
            "summary": pd.DataFrame(),
        }
        mock_channel_pipeline.return_value.run.return_value = {
            "output_path": Path("/tmp/xw.xlsx"),
            "summary": pd.DataFrame(),
            "warnings": [],
        }

        rc = cmd_compute_all(self._args(reconcile=True))

        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
